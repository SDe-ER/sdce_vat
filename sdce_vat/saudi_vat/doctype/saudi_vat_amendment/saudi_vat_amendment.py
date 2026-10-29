# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saudi VAT Amendment: a later correction of an approved return, linked to its sources."""

import frappe
from frappe import _
from frappe.model.document import Document

from sdce_vat.engine.money import D, total
from sdce_vat.engine.rules import verified_value
from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import load_rule_book
from sdce_vat.saudi_vat.doctype.saudi_vat_settings.saudi_vat_settings import get_settings

KIND_LATER_RETURN = "Correction in a Later Return"
LIMIT_KEY = "correction_limit"  # IR Art. 63: largest VAT effect a later return may correct


class SaudiVATAmendment(Document):
	def validate(self):
		original = frappe.get_doc("Saudi VAT Return", self.original_return)
		if original.docstatus != 1:
			frappe.throw(_("Only an approved VAT return can be amended"))
		original.check_permission("read")
		self.total_vat_effect = total(row.vat_effect for row in self.lines)
		if self.kind == KIND_LATER_RETURN:
			limit = correction_limit(original)
			if abs(D(self.total_vat_effect)) > limit:
				frappe.throw(
					_(
						"A VAT effect above {0} needs a self-amendment, not a correction in a later return"
					).format(limit)
				)
			if self.target_return:
				target = frappe.db.get_value(
					"Saudi VAT Return", self.target_return, ["company", "from_date"], as_dict=True
				)
				if self.target_return == self.original_return or target.company != original.company:
					frappe.throw(_("The later return must be another return of the same company"))
				if target.from_date <= original.to_date:
					frappe.throw(_("The later return must start after the original period"))
		elif self.target_return:
			frappe.throw(_("A self-amendment has no later return"))


def correction_limit(original) -> D:
	"""The verified correction limit of the published rule set in force on the last day of the original period.

	No limit is assumed: without a published set or with a missing or unverified rule, a correction in a later
	return is refused. Which date decides the limit (the original period, the discovery or the correcting return)
	is itself an Art. 63 point for the verifier; the original period is used until it is decided.
	"""
	last_day = str(original.to_date)
	code = get_settings(original.company).rule_set_code
	rule_set, issue = load_rule_book(code, last_day, last_day).for_date(last_day)
	if not issue:
		value, issue = verified_value(rule_set, LIMIT_KEY)
	if issue:
		frappe.throw(
			_(
				"The Art. 63 correction limit is not verified for the original period ({0}); a correction in a later return cannot be accepted"
			).format(issue),
			title=_("Correction rule not verified"),
		)
	return D(value)
