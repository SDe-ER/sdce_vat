# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saudi VAT Rule Set: one dated, versioned and referenced set of tax rules. Three different users prepare, verify
and publish it; a published set never changes. A later change is a new version; a correction of a published set is
a Corrective version with a documented basis. Approved returns are never changed by a rule set."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate, now_datetime

from sdce_vat.constants import (
	AMOUNT_RULE_KEYS,
	CORRECTION_LIMIT_BASES,
	CORRECTION_LIMIT_MEASURES,
	DECIMAL_RULE_KEYS,
	RULE_KEY_PREFIXES,
	RULE_KEYS,
	VAT_APPROVER,
	VAT_REVIEWER,
	VAT_RULE_MAINTAINER,
	WHOLE_NUMBER_RULE_KEYS,
)
from sdce_vat.engine import boxes
from sdce_vat.engine.model import Treatment
from sdce_vat.engine.rules import TAX_DATE_BASES, Rule, RuleBook, RuleSet

STATE_DRAFT = "Rule Draft"
STATE_VERIFIED = "Rule Verified"
STATE_PUBLISHED = "Rule Published"
STATE_CANCELLED = "Rule Cancelled"
NORMAL, CORRECTIVE = "Normal", "Corrective"
DONE_STATUSES = ("Verified", "Not applicable")
HEADER_FIELDS = (
	"rule_set_code",
	"version",
	"version_type",
	"return_form_version",
	"effective_from",
	"effective_to",
	"supersedes",
	"correction_basis",
	"description_en",
	"description_ar",
)
REFERENCE_FIELDS = (
	"ref_id",
	"source_type",
	"title",
	"url",
	"section",
	"publication_date",
	"effective_date",
	"accessed_on",
)
RULE_FIELDS = (
	"rule_key",
	"value",
	"reference",
	"verification_status",
	"description_en",
	"description_ar",
	"notes",
)
LABEL_FIELDS = ("field_id", "label_en", "label_ar", "reference")
# Set only by this controller; a form or API save cannot set them.
SYSTEM_FIELDS = (
	"verification_status",
	"content_hash",
	"prepared_by",
	"contributors",
	"verified_by",
	"verified_on",
	"published_by",
	"published_on",
)
RULE_STAMP_FIELDS = ("verified_by", "verified_on")
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,59}$")
REF_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")
KEY_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,59}$")
TREATMENTS = frozenset(t.value for t in Treatment)
# placement of these treatments is not a rule: non-deductible input follows Saudi VAT Settings, review lines are
# never placed
UNUSED_BOX_KEYS = (
	f"treatment_box:{Treatment.INPUT_NOT_DEDUCTIBLE}",
	f"treatment_box:{Treatment.NEEDS_REVIEW}",
)


def _text(value) -> str:
	return "" if value in (None, "") else str(value)


def _date(value) -> str:
	return str(getdate(value)) if value else ""


def is_valid_rule_key(key: str) -> bool:
	"""A key of the closed list: an exact key, or `<prefix>:<name>` with a known prefix."""
	if key in RULE_KEYS:
		return True
	prefix, sep, name = (key or "").partition(":")
	if not sep or prefix not in RULE_KEY_PREFIXES or not KEY_NAME_PATTERN.match(name):
		return False
	return prefix != "treatment_box" or name in TREATMENTS


class SaudiVATRuleSet(Document):
	# ---- lifecycle --------------------------------------------------------------------------------------
	def validate(self):
		before = self.get_doc_before_save()
		self._protect_system_fields(before)
		self._validate_content()
		if not before or self.content_hash_of(before) != self.content_hash_of(self):
			self._record_content_change()
		self._record_workflow_step(before)
		self.verification_status = "Verified" if self.verified_by else "Pending"

	def before_submit(self):
		# Frappe moves a submitted document to the published state itself, so a direct submit (REST or form)
		# must be refused unless the set was verified: publication only from the verified state
		previous = self.get_doc_before_save()
		if (
			not previous
			or previous.workflow_state != STATE_VERIFIED
			or self.workflow_state != STATE_PUBLISHED
		):
			frappe.throw(_("Only a verified rule set can be published"), frappe.PermissionError)
		_require_role(VAT_APPROVER)
		user = frappe.session.user
		if user in self._contributors() or user == self.verified_by:
			frappe.throw(
				_("The publisher must not be a user who prepared, changed or verified the rule set"),
				frappe.PermissionError,
			)
		self._require_rules_done()
		self._require_confirmed_dates()
		if not self.content_is_intact():
			frappe.throw(_("The rule set content changed after verification; return it to draft"))
		if self.version_type == CORRECTIVE:
			self._check_correction()
		else:
			self._check_normal_version()
		self.published_by, self.published_on = user, now_datetime()

	def before_update_after_submit(self):
		frappe.throw(_("A published rule set cannot be changed; publish a new version instead"))

	def before_cancel(self):
		if self.workflow_state != STATE_CANCELLED:
			frappe.throw(_("A rule set is cancelled only through its workflow"), frappe.PermissionError)
		corrected_by = frappe.db.get_value(
			"Saudi VAT Rule Set", {"supersedes": self.name, "docstatus": 1}, "name"
		)
		if corrected_by:
			frappe.throw(
				_("Rule set {0} is corrected by the published rule set {1}").format(self.name, corrected_by)
			)
		approved = self._approved_return_in(self.effective_from, self._end_date())
		if approved and _can_read_return(approved):
			frappe.throw(
				_(
					"Rule set {0} covers the period of the approved VAT return {1}; it cannot be cancelled"
				).format(self.name, approved)
			)
		if approved:
			frappe.throw(
				_("Rule set {0} covers the period of an approved VAT return; it cannot be cancelled").format(
					self.name
				)
			)

	# ---- integrity ----------------------------------------------------------------------------------------
	@staticmethod
	def content_of(doc) -> dict:
		"""Canonical content of a rule set (the basis of `content_hash`); stamps are not part of it."""
		header = []
		for field in HEADER_FIELDS:
			value = doc.get(field)
			header.append(_date(value) if field in ("effective_from", "effective_to") else _text(value))
		references = [
			[_date(r.get(f)) if f.endswith(("_date", "_on")) else _text(r.get(f)) for f in REFERENCE_FIELDS]
			for r in doc.get("references") or []
		]
		return {
			"header": header,
			"references": sorted(references),
			"rules": sorted([_text(r.get(f)) for f in RULE_FIELDS] for r in doc.get("rules") or []),
			"field_labels": sorted(
				[_text(r.get(f)) for f in LABEL_FIELDS] for r in doc.get("field_labels") or []
			),
		}

	@classmethod
	def content_hash_of(cls, doc) -> str:
		payload = json.dumps(cls.content_of(doc), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
		return hashlib.sha256(payload.encode()).hexdigest()

	def content_is_intact(self) -> bool:
		"""The stored content still has the hash recorded at verification."""
		return bool(self.content_hash) and self.content_hash == self.content_hash_of(self)

	# ---- validation ---------------------------------------------------------------------------------------
	def _validate_content(self):
		if not CODE_PATTERN.match(self.rule_set_code or ""):
			frappe.throw(_("Rule Set Code may contain only capital letters, digits, hyphens and underscores"))
		if (self.version or 0) < 1:
			frappe.throw(_("Version must be 1 or higher"))
		if self.effective_to and not self.effective_from:
			frappe.throw(_("Set Effective From before Effective To"))
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To must be on or after Effective From"))
		ref_ids = self._validate_references()
		self._validate_rules(ref_ids)
		self._validate_field_labels(ref_ids)
		if self.version_type == CORRECTIVE:
			if not self.supersedes or not self.correction_basis:
				frappe.throw(
					_("A corrective version needs the rule set it supersedes and a correction basis")
				)
			if self.supersedes == self.name:
				frappe.throw(_("A rule set cannot supersede itself"))
			if self.correction_basis not in ref_ids:
				frappe.throw(
					_("Correction basis {0} is not a reference of this rule set").format(
						self.correction_basis
					)
				)
		elif self.supersedes or self.correction_basis:
			frappe.throw(_("Only a corrective version can supersede a rule set or have a correction basis"))

	def _validate_references(self) -> set:
		ref_ids = set()
		for row in self.references:
			if not REF_ID_PATTERN.match(row.ref_id or ""):
				frappe.throw(_("Row {0}: Reference ID {1} is not valid").format(row.idx, row.ref_id))
			if row.ref_id in ref_ids:
				frappe.throw(_("Row {0}: Reference ID {1} is listed twice").format(row.idx, row.ref_id))
			if row.url and not row.url.startswith("https://"):
				frappe.throw(_("Row {0}: the reference URL must start with https://").format(row.idx))
			ref_ids.add(row.ref_id)
		return ref_ids

	def _validate_rules(self, ref_ids):
		keys = set()
		for row in self.rules:
			key = row.rule_key or ""
			if not is_valid_rule_key(key):
				frappe.throw(_("Row {0}: {1} is not a known rule key").format(row.idx, row.rule_key))
			if key in keys:
				frappe.throw(_("Row {0}: rule key {1} is listed twice").format(row.idx, key))
			if key in UNUSED_BOX_KEYS:
				frappe.throw(
					_(
						"Row {0}: {1} is not decided by a rule set (see Saudi VAT Settings and the review)"
					).format(row.idx, key)
				)
			keys.add(key)
			if row.reference not in ref_ids:
				frappe.throw(
					_("Row {0}: reference {1} is not in the references table").format(row.idx, row.reference)
				)
			_check_value(row, key)

	def _validate_field_labels(self, ref_ids):
		field_ids = set()
		for row in self.field_labels:
			if row.field_id not in boxes.BOX_BY_ID:
				frappe.throw(_("Row {0}: {1} is not a return field").format(row.idx, row.field_id))
			if row.field_id in field_ids:
				frappe.throw(_("Row {0}: return field {1} is listed twice").format(row.idx, row.field_id))
			if row.reference and row.reference not in ref_ids:
				frappe.throw(
					_("Row {0}: reference {1} is not in the references table").format(row.idx, row.reference)
				)
			field_ids.add(row.field_id)

	def _protect_system_fields(self, before):
		if not before:
			for field in SYSTEM_FIELDS:
				self.set(field, None)
			for row in self.rules:
				for field in RULE_STAMP_FIELDS:
					row.set(field, None)
			return
		for field in SYSTEM_FIELDS:
			if _text(self.get(field)) != _text(before.get(field)):
				frappe.throw(
					_("{0} is set by the system and cannot be edited").format(_(self.meta.get_label(field)))
				)
		stamps = {r.name: [_text(r.get(f)) for f in RULE_STAMP_FIELDS] for r in before.rules}
		for row in self.rules:
			if [_text(row.get(f)) for f in RULE_STAMP_FIELDS] != stamps.get(row.name, ["", ""]):
				frappe.throw(_("Row {0}: verification stamps are set by the system").format(row.idx))

	# ---- workflow -------------------------------------------------------------------------------------------
	def _record_content_change(self):
		if (self.workflow_state or STATE_DRAFT) != STATE_DRAFT:
			frappe.throw(_("Return the rule set to draft before changing it"))
		_require_role(VAT_RULE_MAINTAINER)
		user = frappe.session.user
		contributors = self._contributors()
		if user not in contributors:
			self.contributors = "\n".join([*contributors, user])
		self.prepared_by = user

	def _record_workflow_step(self, before):
		previous = before.workflow_state if before else None
		if self.workflow_state == previous:
			return
		if self.workflow_state == STATE_DRAFT:
			self._clear_verification()  # earlier verification no longer counts
		elif self.workflow_state == STATE_VERIFIED:
			self._verify(previous)
		elif self.workflow_state in (STATE_PUBLISHED, STATE_CANCELLED) and self.docstatus == 0:
			frappe.throw(
				_("A rule set is published or cancelled only through its workflow"), frappe.PermissionError
			)

	def _verify(self, previous):
		if previous != STATE_DRAFT:
			frappe.throw(_("Only a draft rule set can be verified"), frappe.PermissionError)
		_require_role(VAT_REVIEWER, VAT_RULE_MAINTAINER)
		user = frappe.session.user
		if user in self._contributors():
			frappe.throw(
				_("The verifier must not be a user who prepared or changed the rule set"),
				frappe.PermissionError,
			)
		self._require_rules_done()
		references = {r.ref_id: r for r in self.references}
		for row in self.rules:
			if row.verification_status == "Verified":
				_require_complete_reference(references[row.reference], row.idx)
		if self.version_type == CORRECTIVE:
			_require_complete_reference(references[self.correction_basis], None)
		self._require_confirmed_dates()
		now = now_datetime()
		for row in self.rules:
			row.verified_by, row.verified_on = user, now
		self.verified_by, self.verified_on = user, now
		self.content_hash = self.content_hash_of(self)

	def _clear_verification(self):
		for row in self.rules:
			for field in RULE_STAMP_FIELDS:
				row.set(field, None)
		self.verified_by = self.verified_on = self.content_hash = None

	def _require_rules_done(self):
		if not self.rules:
			frappe.throw(_("A rule set needs at least one rule"))
		pending = [str(r.idx) for r in self.rules if r.verification_status not in DONE_STATUSES]
		if pending:
			frappe.throw(_("Rules in rows {0} are still pending verification").format(", ".join(pending)))

	def _require_confirmed_dates(self):
		"""A set is verified and published only with a confirmed start date, and no verified rule may take effect
		after it. A rule's date is that of its reference (effective date, else publication date): rules of one set
		may come from different dates, but all of them must already apply on the first day of the set."""
		if not self.effective_from:
			frappe.throw(
				_("Effective From is not confirmed; enter the date the rules took effect before verification")
			)
		start = getdate(self.effective_from)
		references = {r.ref_id: r for r in self.references}
		for row in self.rules:
			if row.verification_status != "Verified":
				continue
			reference = references[row.reference]
			takes_effect = reference.effective_date or reference.publication_date
			if takes_effect and getdate(takes_effect) > start:
				frappe.throw(
					_("Row {0}: rule {1} takes effect on {2}, after the rule set starts on {3}").format(
						row.idx, row.rule_key, getdate(takes_effect), start
					)
				)

	def _contributors(self) -> list:
		return [u for u in (self.contributors or "").split("\n") if u]

	# ---- publication checks ---------------------------------------------------------------------------------
	def _published_versions(self) -> list:
		"""Other published sets of this code. The locking read on every set of the code makes two publications
		of the same code wait for each other, so each sees the other's result."""
		rows = frappe.db.get_values(
			"Saudi VAT Rule Set",
			{"rule_set_code": self.rule_set_code},
			["name", "docstatus", "version", "version_type", "effective_from", "effective_to", "supersedes"],
			as_dict=True,
			for_update=True,
		)
		return [r for r in rows if r.docstatus == 1 and r.name != self.name]

	def _check_version_order(self, published):
		highest = max((p.version for p in published), default=0)
		if self.version <= highest:
			frappe.throw(_("Version must be higher than the published version {0}").format(highest))

	def _check_normal_version(self):
		published = self._published_versions()
		self._check_version_order(published)
		start = getdate(self.effective_from)
		for other in (p for p in published if p.version_type == NORMAL):
			other_start = getdate(other.effective_from)
			if other_start == start:
				frappe.throw(_("Rule set {0} already starts on {1}").format(other.name, start))
			earlier, later_start = (other, start) if other_start < start else (self, other_start)
			if earlier.effective_to and getdate(earlier.effective_to) >= later_start:
				frappe.throw(_("The effective dates overlap with rule set {0}").format(other.name))
		approved = self._approved_return_in(self.effective_from, self._end_date(published))
		if approved and _can_read_return(approved):
			frappe.throw(
				_(
					"The approved VAT return {0} falls in the effective period; a normal version cannot change "
					"it. Use a corrective version with a documented basis."
				).format(approved)
			)
		if approved:
			frappe.throw(
				_(
					"An approved VAT return falls in the effective period; a normal version cannot change it. "
					"Use a corrective version with a documented basis."
				)
			)

	def _check_correction(self):
		published = self._published_versions()
		self._check_version_order(published)
		target = next((p for p in published if p.name == self.supersedes), None)
		if not target:
			frappe.throw(_("A corrective version can supersede only a published rule set with the same code"))
		correction = next((p.name for p in published if p.supersedes == target.name), None)
		if correction:
			# corrections form one chain: the next correction supersedes the latest one, never a second branch
			frappe.throw(
				_("Rule set {0} is already corrected by {1}; a further correction must supersede {1}").format(
					target.name, correction
				)
			)
		if getdate(self.effective_from) < getdate(target.effective_from):
			frappe.throw(_("A corrective version cannot start before the rule set it supersedes"))
		target_end = _last_day(target.effective_from, target.effective_to, published)
		if target_end and (not self.effective_to or getdate(self.effective_to) > target_end):
			frappe.throw(_("A corrective version cannot end after the rule set it supersedes"))

	def _end_date(self, published=None):
		if published is None:
			published = self._published_versions()
		return _last_day(self.effective_from, self.effective_to, published)

	@staticmethod
	def _approved_return_in(start, end):
		filters = {"docstatus": 1, "to_date": [">=", getdate(start)]}
		if end:
			filters["from_date"] = ["<=", getdate(end)]
		return frappe.db.get_value("Saudi VAT Return", filters, "name")


def _can_read_return(name) -> bool:
	"""Rule sets are national; an approved return of a company the user cannot read is not named."""
	return frappe.has_permission("Saudi VAT Return", "read", doc=name)


def _last_day(start, end, published):
	"""Last day a set applies: its Effective To, or the day before the next normal version starts (None = open)."""
	if end:
		return getdate(end)
	start = getdate(start)
	later = [getdate(p.effective_from) for p in published if p.version_type == NORMAL]
	later = [d for d in later if d > start]
	return add_days(min(later), -1) if later else None


def load_rule_book(code: str | None, from_date=None, to_date=None) -> RuleBook:
	"""The published sets of one code for the engine. Drafts, verified-only and cancelled sets are never used; a
	set whose stored content no longer has its published hash stops the calculation. With a period, only sets
	that can apply to a date inside it are read: a set starting after the period cannot cover it or end a set
	inside it, and a set ending before it cannot cover it."""
	if not code:
		return RuleBook(None, [])
	filters = [["rule_set_code", "=", code], ["docstatus", "=", 1]]
	if to_date:
		filters.append(["effective_from", "<=", to_date])
	sets = []
	rows = frappe.get_all("Saudi VAT Rule Set", filters=filters, fields=["name", "effective_to"])
	ended = [r.name for r in rows if from_date and r.effective_to and str(r.effective_to) < str(from_date)]
	for name in (r.name for r in rows if r.name not in ended):
		doc = frappe.get_doc("Saudi VAT Rule Set", name)
		if not doc.content_is_intact():
			frappe.throw(_("Rule set {0} no longer matches its published content hash").format(name))
		sets.append(
			RuleSet(
				name=doc.name,
				code=doc.rule_set_code,
				version=doc.version,
				version_type=doc.version_type,
				effective_from=str(getdate(doc.effective_from)),
				effective_to=str(getdate(doc.effective_to)) if doc.effective_to else None,
				content_hash=doc.content_hash,
				rules={r.rule_key: Rule(r.rule_key, r.value, r.verification_status) for r in doc.rules},
				supersedes=doc.supersedes,
			)
		)
	return RuleBook(code, sets)


def _check_value(row, key):
	value = row.value or ""
	if row.verification_status == "Verified":
		if key.startswith("treatment_box:") and value not in boxes.LINE_BOXES:
			frappe.throw(
				_("Row {0}: {1} must name a return field, for example S01 or P07").format(row.idx, key)
			)
		if key.startswith("tax_date_basis:") and value not in TAX_DATE_BASES:
			frappe.throw(
				_("Row {0}: {1} must be one of: {2}").format(row.idx, key, ", ".join(TAX_DATE_BASES))
			)
		for choice_key, choices in (
			("correction_limit_basis", CORRECTION_LIMIT_BASES),
			("correction_limit_measure", CORRECTION_LIMIT_MEASURES),
		):
			if key == choice_key and value not in choices:
				frappe.throw(_("Row {0}: {1} must be one of: {2}").format(row.idx, key, ", ".join(choices)))
		# an amount stays open (any text) until verified, so a disputed threshold is never forced into a number
		if key in AMOUNT_RULE_KEYS:
			try:
				amount = Decimal(value)
			except InvalidOperation:
				amount = None
			if amount is None or not amount.is_finite() or amount <= 0:
				frappe.throw(_("Row {0}: {1} must be an amount above 0").format(row.idx, key))
	if key in DECIMAL_RULE_KEYS:
		try:
			number = Decimal(value)
		except InvalidOperation:
			number = None
		if number is None or not number.is_finite() or not Decimal(0) < number <= Decimal(100):
			frappe.throw(_("Row {0}: {1} must be a number above 0 and up to 100").format(row.idx, key))
	elif key in WHOLE_NUMBER_RULE_KEYS and (not value.isdigit() or int(value) < 1):
		frappe.throw(_("Row {0}: {1} must be a whole number of 1 or more").format(row.idx, key))


def _require_complete_reference(reference, idx):
	"""A verified rule or a correction basis needs an official link, the section and the dates."""
	dated = reference.publication_date or reference.effective_date
	if reference.url and reference.section and dated and reference.accessed_on:
		return
	if idx:
		frappe.throw(
			_(
				"Row {0}: reference {1} needs a URL, a section, a publication or effective date and an access date"
			).format(idx, reference.ref_id)
		)
	frappe.throw(
		_(
			"Correction basis {0} needs a URL, a section, a publication or effective date and an access date"
		).format(reference.ref_id)
	)


def refuse_standalone_save():
	"""Rows of a rule set change only through the rule set, where duties and stamps are checked. Frappe saves
	a row on its own for `PUT /api/resource/<child>/<name>` and for `frappe.client.save` with a row; saving
	the rule set itself does not run the row's `validate`."""
	frappe.throw(_("Change the rows through the rule set"), frappe.PermissionError)


def _require_role(*roles):
	if not set(roles) & set(frappe.get_roles()):
		frappe.throw(
			_("This step needs one of the roles: {0}").format(", ".join(_(r) for r in roles)),
			frappe.PermissionError,
		)
