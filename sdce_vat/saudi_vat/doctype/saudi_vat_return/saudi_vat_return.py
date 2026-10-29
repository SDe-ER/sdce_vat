# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saudi VAT Return: stores one engine calculation, carries it through preparation, review and approval, and
freezes it as a hashed snapshot. It never calculates by itself and never posts to the ledger."""

import hashlib
import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from sdce_vat.constants import VAT_PREPARER, VAT_REVIEWER
from sdce_vat.engine import boxes
from sdce_vat.engine.core import ENGINE_VERSION
from sdce_vat.engine.money import D, q2
from sdce_vat.engine.run import compute
from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import SaudiVATRuleSet
from sdce_vat.saudi_vat.doctype.saudi_vat_settings.saudi_vat_settings import get_settings

STATE_DRAFT = "VAT Draft"
STATE_PREPARED = "VAT Prepared"
STATE_REVIEWED = "VAT Reviewed"
INPUT_FIELDS = ("company", "from_date", "to_date", "corrections", "credit_carried")
CALCULATED_FIELDS = (
	"net_vat",
	"gl_reconciled",
	"review_count",
	"warning_count",
	"engine_version",
	"calculated_on",
	"calculated_by",
	"calculation_hash",
)
APPROVAL_FIELDS = ("prepared_by", "prepared_on", "reviewed_by", "reviewed_on", "approved_by", "approved_on")
SNAPSHOT_FIELDS = ("snapshot_hash", "snapshot_file")
CHILD_TABLES = ("lines", "sources", "proof", "rule_sets")
LEGACY_ENGINE = "0.1.0"  # returns calculated before rule books keep their original payload and snapshot


def _money(value) -> str:
	return str(q2(D(value)))


def _sha256(payload) -> str:
	return hashlib.sha256(
		json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
	).hexdigest()


class SaudiVATReturn(Document):
	# ---- lifecycle --------------------------------------------------------------------------------------
	def validate(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date must be on or before To Date"))
		if not frappe.has_permission("Company", "read", doc=self.company):
			frappe.throw(_("Not permitted for company {0}").format(self.company), frappe.PermissionError)
		self._check_overlap()
		before = self.get_doc_before_save()
		if not self.flags.from_calculation:
			self._protect_calculated_values(before)
		if before and any(self._same(f, self) != self._same(f, before) for f in INPUT_FIELDS):
			if (self.workflow_state or "") not in ("", "VAT Draft"):
				frappe.throw(_("Return the VAT return to the preparer before changing its period or inputs"))
			self._clear_calculation()
		self._record_workflow_step(before)

	def before_submit(self):
		# Frappe moves a submitted document to the approved state itself, so a direct submit (REST or form)
		# must be refused unless the return was reviewed: approval only from the reviewed state
		previous = self.get_doc_before_save()
		if not previous or previous.workflow_state != STATE_REVIEWED:
			frappe.throw(_("Only a reviewed VAT return can be approved"), frappe.PermissionError)
		if not self.calculation_hash:
			frappe.throw(_("Calculate the return before approval"))
		if self.engine_version != ENGINE_VERSION:
			frappe.throw(
				_("The return was calculated by engine {0}; recalculate it with engine {1}").format(
					self.engine_version, ENGINE_VERSION
				)
			)
		if self.review_count:
			frappe.throw(
				_("{0} sources still need review; approval is blocked").format(self.review_count),
				title=_("Unresolved sources"),
			)
		if not self.gl_reconciled:
			frappe.throw(_("The return does not reconcile with the general ledger; approval is blocked"))
		if not self.reviewed_by:
			frappe.throw(_("The return must be reviewed before approval"))
		approver = frappe.session.user
		if approver in (self.prepared_by, self.reviewed_by, self.calculated_by):
			frappe.throw(
				_("The approver must not be the user who calculated, prepared or reviewed the return"),
				frappe.PermissionError,
			)
		if _sha256(self._payload()) != self.calculation_hash:
			frappe.throw(_("Stored values were changed after calculation; recalculate the return"))
		live = self._live_payload()
		if live.get("rule_sets") != self._payload().get("rule_sets"):
			frappe.throw(_("The published rule sets changed since the calculation; recalculate the return"))
		if _sha256(live) != self.calculation_hash:
			frappe.throw(_("Documents in the period changed since the calculation; recalculate the return"))
		self.approved_by, self.approved_on = approver, now_datetime()
		self._write_snapshot()

	# ---- calculation --------------------------------------------------------------------------------------
	@frappe.whitelist(methods=["POST"])
	def calculate(self):
		"""Run the engine and store its result. VAT Preparer only, draft only."""
		self.check_permission("write")
		if VAT_PREPARER not in frappe.get_roles():
			frappe.throw(_("Only a VAT Preparer can calculate the return"), frappe.PermissionError)
		if self.docstatus != 0 or (self.workflow_state or "VAT Draft") != "VAT Draft":
			frappe.throw(_("Only a draft return can be calculated"))
		self._load(self._run_engine())
		self._clear_steps()  # a new calculation needs a new preparation and review
		self.calculated_by, self.calculated_on = frappe.session.user, now_datetime()
		self.calculation_hash = _sha256(self._payload())
		self.flags.from_calculation = True
		try:
			self.save()
		finally:
			self.flags.from_calculation = False  # later saves of this object are protected again
		return {"calculation_hash": self.calculation_hash, "review_count": self.review_count}

	@frappe.whitelist(methods=["GET"])
	def check_drift(self):
		"""Read-only: does a fresh calculation still give the stored values?"""
		self.check_permission("read")
		live = self._live_payload()
		stored = self._payload()
		changed = sorted(_source_keys(live) ^ _source_keys(stored))
		rule_sets = {tuple(r) for r in live.get("rule_sets", [])} ^ {
			tuple(r) for r in stored.get("rule_sets", [])
		}
		return {
			"unchanged": _sha256(live) == self.calculation_hash,
			"changed_sources": changed,
			"changed_rule_sets": sorted(list(r) for r in rule_sets),
		}

	@frappe.whitelist(methods=["GET"])
	def verify_snapshot(self):
		"""Read-only: the snapshot file and the stored tables both still match the approved hash."""
		self.check_permission("read")
		if not self.snapshot_hash:
			return {"approved": False}
		content = frappe.get_doc("File", {"file_url": self.snapshot_file}).get_content()
		if isinstance(content, bytes):
			content = content.decode()
		file_ok = hashlib.sha256(content.encode()).hexdigest() == self.snapshot_hash
		tables_ok = _sha256(self._snapshot_payload()) == self.snapshot_hash
		return {"approved": True, "file_ok": file_ok, "tables_ok": tables_ok}

	# ---- helpers --------------------------------------------------------------------------------------------
	def _run_engine(self):
		return compute(
			get_settings(self.company).to_config(),
			str(self.from_date),
			str(self.to_date),
			corrections=D(self.corrections or 0),
			credit_carried=D(self.credit_carried or 0),
		)

	def _live_payload(self) -> dict:
		copy = frappe.get_doc(self.as_dict())
		copy._load(self._run_engine())
		return copy._payload()

	def _load(self, result):
		for table in CHILD_TABLES:
			self.set(table, [])
		for box in boxes.BOXES:
			total = result.boxes[box.id]
			self.append(
				"lines",
				{
					"box_id": box.id,
					"box_no": box.number,
					"label": box.label_ar,
					"amount": total.amount,
					"adjustment": total.adjustment,
					"vat": total.vat,
					"line_count": len(total.lines),
				},
			)
		for line in result.lines:
			self.append(
				"sources",
				{
					"box_id": line.box,
					"treatment": str(line.treatment) if line.treatment else None,
					"reason": line.reason,
					"needs_review": int(line.needs_review),
					"column": str(line.column) if line.column else None,
					"voucher_type": line.voucher_type,
					"voucher_no": line.voucher_no,
					"posting_date": line.posting_date or None,
					"invoice_date": line.invoice_date,
					"tax_date": line.tax_date,
					"tax_date_basis": line.tax_date_basis,
					"rule_set": line.rule_set,
					"rule_issue": line.rule_issue or None,
					"party_type": line.party_type,
					"party": line.party,
					"party_tax_id": line.party_tax_id,
					"bill_no": line.bill_no,
					"vat_account": line.vat_account,
					"base": line.base,
					"vat": line.vat,
					"warnings": "\n".join(line.warnings),
					"source_rows": "\n".join(line.source_rows),
				},
			)
		for proof in result.proof:
			self.append(
				"proof",
				{
					"account": proof.account,
					"side": str(proof.side),
					"gl_vat": proof.gl_vat,
					"lines_vat": proof.lines_vat,
					"difference": proof.difference,
				},
			)
		for name, rule_set in result.rule_sets.items():
			tax_dates = sorted(line.tax_date for line in result.lines if line.rule_set == name)
			self.append(
				"rule_sets",
				{
					"rule_set": name,
					"version": rule_set.version,
					"content_hash": rule_set.content_hash,
					"line_count": len(tax_dates),
					"first_tax_date": tax_dates[0],
					"last_tax_date": tax_dates[-1],
				},
			)
		self.net_vat = result.boxes[boxes.NET_VAT].vat
		self.gl_reconciled = int(result.is_reconciled)
		self.review_count = len(result.review_lines)
		self.warning_count = len(result.warning_lines)
		self.engine_version = result.engine_version

	def _payload(self) -> dict:
		"""Canonical content of the calculation as stored in the tables (the basis of every hash)."""
		payload = self._legacy_payload()
		if self.engine_version == LEGACY_ENGINE:
			return payload
		# rule books: every source carries its tax date and rule set; the hash covers the (set, content hash) list
		payload["source_rules"] = sorted(
			[
				r.voucher_type,
				r.voucher_no,
				r.vat_account or "",
				str(r.invoice_date or ""),
				str(r.tax_date or ""),
				r.tax_date_basis or "",
				r.rule_set or "",
				r.rule_issue or "",
			]
			for r in self.sources
		)
		payload["rule_sets"] = sorted([r.rule_set, r.content_hash] for r in self.rule_sets)
		# the shown details of each rule set row are covered too, so no stored column can be edited unnoticed
		payload["rule_set_rows"] = sorted(
			[
				r.rule_set,
				int(r.version or 0),
				int(r.line_count or 0),
				str(r.first_tax_date),
				str(r.last_tax_date),
			]
			for r in self.rule_sets
		)
		return payload

	def _legacy_payload(self) -> dict:
		return {
			"header": [
				self.company,
				self.tax_id or "",
				str(self.from_date),
				str(self.to_date),
				_money(self.corrections),
				_money(self.credit_carried),
				self.engine_version or "",
			],
			"lines": [
				[r.box_id, _money(r.amount), _money(r.adjustment), _money(r.vat), int(r.line_count or 0)]
				for r in self.lines
			],
			"sources": sorted(
				[
					r.voucher_type,
					r.voucher_no,
					r.vat_account or "",
					r.box_id or "",
					r.treatment or "",
					r.reason or "",
					r.column or "",
					_money(r.base),
					_money(r.vat),
					r.warnings or "",
					r.party or "",
					r.party_tax_id or "",
					r.bill_no or "",
				]
				for r in self.sources
			),
			"proof": [[r.account, r.side, _money(r.gl_vat), _money(r.lines_vat)] for r in self.proof],
		}

	def _snapshot_payload(self) -> dict:
		settings = get_settings(self.company)
		payload = {
			"calculation": self._payload(),
			"calculation_hash": self.calculation_hash,
			"settings": {
				"accounts": sorted([r.account, r.family, str(r.rate)] for r in settings.accounts),
				"category_rules": sorted([r.category, r.treatment] for r in settings.category_rules),
				"non_deductible_placement": settings.non_deductible_placement or "",
			},
			"people": {
				"calculated_by": self.calculated_by,
				"calculated_on": str(self.calculated_on),
				"prepared_by": self.prepared_by,
				"prepared_on": str(self.prepared_on),
				"reviewed_by": self.reviewed_by,
				"reviewed_on": str(self.reviewed_on),
				"approved_by": self.approved_by,
				"approved_on": str(self.approved_on),
			},
		}
		if self.engine_version != LEGACY_ENGINE:
			# full copy of every rule set used: the approved return stays readable when rules change later
			payload["rule_sets"] = [
				{
					"name": r.rule_set,
					"content_hash": r.content_hash,
					"content": SaudiVATRuleSet.content_of(frappe.get_doc("Saudi VAT Rule Set", r.rule_set)),
				}
				for r in sorted(self.rule_sets, key=lambda r: r.rule_set)
			]
		return payload

	def _write_snapshot(self):
		payload = self._snapshot_payload()
		content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
		self.snapshot_hash = hashlib.sha256(content.encode()).hexdigest()
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{self.name}-snapshot.json",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"is_private": 1,
				"content": content,
			}
		).insert(ignore_permissions=True)  # the approver may lack File create rights; access is checked above
		self.snapshot_file = file.file_url

	def _clear_steps(self):
		for field in ("prepared_by", "prepared_on", "reviewed_by", "reviewed_on"):
			self.set(field, None)

	def _clear_calculation(self):
		for table in CHILD_TABLES:
			self.set(table, [])
		for field in CALCULATED_FIELDS:
			self.set(field, None)

	def _protect_calculated_values(self, before):
		"""Calculated values change only through `calculate()`; a form or API save cannot set them."""
		if not before:
			if self.calculation_hash or any(self.get(t) for t in CHILD_TABLES):
				self._clear_calculation()
			for field in APPROVAL_FIELDS + SNAPSHOT_FIELDS:
				self.set(field, None)
			return
		for field in CALCULATED_FIELDS + APPROVAL_FIELDS + SNAPSHOT_FIELDS:
			if self._same(field, self) != self._same(field, before):
				frappe.throw(
					_("{0} is set by the system and cannot be edited").format(_(self.meta.get_label(field)))
				)
		if _rows(self) != _rows(before):
			frappe.throw(_("Calculated tables are set by the system and cannot be edited"))

	def _same(self, fieldname, doc) -> str:
		"""Comparable form of a field: dates as ISO dates, money in cents, empty and zero alike."""
		value = doc.get(fieldname)
		if value in (None, ""):
			return ""
		fieldtype = self.meta.get_field(fieldname).fieldtype
		if fieldtype == "Date":
			return str(getdate(value))
		if fieldtype in ("Currency", "Float", "Int", "Check"):
			return "" if not value else str(q2(D(value)))
		return str(value)

	def _record_workflow_step(self, before):
		previous = before.workflow_state if before else None
		if self.workflow_state == previous:
			return
		user = frappe.session.user
		if self.workflow_state == STATE_DRAFT:
			self._clear_steps()  # returned or rejected: earlier preparation and review no longer count
		elif self.workflow_state == STATE_PREPARED:
			if not self.calculation_hash:
				frappe.throw(_("Calculate the return before marking it prepared"))
			_require_role(VAT_PREPARER)
			self.prepared_by, self.prepared_on = user, now_datetime()
		elif self.workflow_state == STATE_REVIEWED:
			_require_role(VAT_REVIEWER)
			if user in (self.prepared_by, self.calculated_by):
				frappe.throw(_("The reviewer must not be the preparer"), frappe.PermissionError)
			self.reviewed_by, self.reviewed_on = user, now_datetime()

	def _check_overlap(self):
		filters = {
			"company": self.company,
			"docstatus": ["<", 2],
			"name": ["!=", self.name or ""],
			"from_date": ["<=", self.to_date],
			"to_date": [">=", self.from_date],
		}
		other = frappe.db.get_value("Saudi VAT Return", filters, "name")
		if other:
			frappe.throw(_("VAT return {0} already covers part of this period").format(other))


def _source_keys(payload) -> set:
	# voucher type, voucher, VAT account, VAT
	return {(s[0], s[1], s[2], s[8]) for s in payload["sources"]}


def _rows(doc) -> list:
	return [[(r.as_dict(no_default_fields=True)) for r in doc.get(t) or []] for t in CHILD_TABLES]


def _require_role(role):
	if role not in frappe.get_roles():
		frappe.throw(_("This step needs the role {0}").format(role), frappe.PermissionError)
