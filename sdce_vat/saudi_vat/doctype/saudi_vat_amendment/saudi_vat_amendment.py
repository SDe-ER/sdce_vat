# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saudi VAT Amendment: a later correction of an approved return, linked to its sources.

A correction in a later return is limited by IR Art. 63. Three points decide the check, and each is a verified
rule of the published rule sets, never a value in code:
- `correction_limit`: the amount;
- `correction_limit_basis`: which date selects the rule set that gives the amount;
- `correction_limit_measure`: how the lines are compared with the amount.
While any of them is missing or not verified, the amendment can be saved as a draft but not submitted.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

from sdce_vat.constants import CORRECTION_LIMIT_BASES as LIMIT_BASES
from sdce_vat.constants import CORRECTION_LIMIT_MEASURES as LIMIT_MEASURES
from sdce_vat.engine.money import D, total
from sdce_vat.engine.rules import verified_value
from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import load_rule_book
from sdce_vat.saudi_vat.doctype.saudi_vat_settings.saudi_vat_settings import get_settings

KIND_LATER_RETURN = "Correction in a Later Return"
LIMIT_KEY = "correction_limit"
BASIS_KEY = "correction_limit_basis"
MEASURE_KEY = "correction_limit_measure"


class SaudiVATAmendment(Document):
	def validate(self):
		original = frappe.get_doc("Saudi VAT Return", self.original_return)
		if original.docstatus != 1:
			frappe.throw(_("Only an approved VAT return can be amended"))
		original.check_permission("read")
		self.total_vat_effect = total(row.vat_effect for row in self.lines)
		if self.kind == KIND_LATER_RETURN:
			if self.target_return:
				target = frappe.db.get_value(
					"Saudi VAT Return", self.target_return, ["company", "from_date"], as_dict=True
				)
				if self.target_return == self.original_return or target.company != original.company:
					frappe.throw(_("The later return must be another return of the same company"))
				if target.from_date <= original.to_date:
					frappe.throw(_("The later return must start after the original period"))
			problem = self.later_return_problem(original)
			if problem:
				# the draft may be saved; submission is refused in before_submit
				frappe.msgprint(
					problem, title=_("Correction in a later return not available"), indicator="orange"
				)
		elif self.target_return:
			frappe.throw(_("A self-amendment has no later return"))

	def before_submit(self):
		if self.kind != KIND_LATER_RETURN:
			return
		problem = self.later_return_problem(frappe.get_doc("Saudi VAT Return", self.original_return))
		if problem:
			frappe.throw(problem, title=_("Correction in a later return not available"))

	def later_return_problem(self, original) -> str | None:
		"""A readable reason why this correction cannot go into a later return, or None. The diagnostic code goes
		to the technical log."""
		code, values = check_later_return(self, original)
		if not code:
			return None
		frappe.logger("sdce_vat").info(
			{"doctype": self.doctype, "name": self.name, "diagnostic": code, "values": values}
		)
		reason = _reason(code, values)
		return _(
			"{0} This does not mean that a self-amendment is required or suitable; check IR Art. 63 with your tax adviser."
		).format(reason)


def check_later_return(amendment, original) -> tuple[str | None, dict]:
	"""(diagnostic code, values) when the Art. 63 check cannot pass, else (None, {})."""
	code = get_settings(original.company).rule_set_code
	book = load_rule_book(code)
	today = nowdate()
	current, issue = book.for_date(
		today
	)  # the procedure (basis and measure) is read from the rules in force now
	if issue:
		return issue, {"date": today}
	basis, issue = _allowed(current, BASIS_KEY, LIMIT_BASES)
	if issue:
		return issue, {}
	measure, issue = _allowed(current, MEASURE_KEY, LIMIT_MEASURES)
	if issue:
		return issue, {}
	day = limit_date(basis, amendment, original)
	if not day:
		return "target_return_missing", {}
	limit_set, issue = book.for_date(day)
	if issue:
		return issue, {"date": day}
	value, issue = verified_value(limit_set, LIMIT_KEY)
	if issue:
		return issue, {"date": day}
	effect = measured_effect(measure, [D(row.vat_effect) for row in amendment.lines])
	if effect > D(value):
		return "above_limit", {"effect": effect, "limit": D(value)}
	return None, {}


def limit_date(basis: str, amendment, original) -> str | None:
	"""The date whose rule set gives the limit, for one candidate reading of Art. 63."""
	if basis == "original_period_end":
		return str(original.to_date)
	if amendment.target_return:  # correcting_return_end
		return str(frappe.db.get_value("Saudi VAT Return", amendment.target_return, "to_date"))
	return None


def measured_effect(measure: str, effects: list) -> D:
	"""The VAT effect compared with the limit, for one candidate reading of Art. 63."""
	if measure == "per_line":
		return max((abs(e) for e in effects), default=D(0))
	if measure == "absolute_total":
		return total(abs(e) for e in effects)
	return abs(total(effects))  # net_total


def _allowed(rule_set, key, allowed) -> tuple[str | None, str | None]:
	value, issue = verified_value(rule_set, key)
	if not issue and value not in allowed:
		issue = f"rule_invalid:{key}"
	return value, issue


def _reason(code: str, values: dict) -> str:
	key = code.split(":", 1)[-1]
	if code.startswith(("rule_set_missing", "rule_set_not_configured", "rule_set_conflict")):
		return _("No single published rule set covers {0}.").format(values.get("date"))
	if code == "target_return_missing":
		return _("Choose the later return first: the limit depends on its period.")
	if code == "above_limit":
		return _("The VAT effect {0} is above the correction limit {1}.").format(
			values.get("effect"), values.get("limit")
		)
	if key == BASIS_KEY:
		return _("The date that decides the correction limit is not verified in the rule set.")
	if key == MEASURE_KEY:
		return _("How corrections are measured against the limit is not verified in the rule set.")
	return _("The correction limit is not verified in the rule set.")
