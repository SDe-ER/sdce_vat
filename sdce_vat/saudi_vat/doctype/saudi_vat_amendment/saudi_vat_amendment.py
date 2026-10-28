# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saudi VAT Amendment: a later correction of an approved return, linked to its sources."""

import frappe
from frappe import _
from frappe.model.document import Document

from sdce_vat.engine.money import D, total

CORRECTION_LIMIT = D("5000")  # ZATCA: corrections between ± SAR 5,000 go into a later return
KIND_LATER_RETURN = "Correction in a Later Return"


class SaudiVATAmendment(Document):
	def validate(self):
		original = frappe.get_doc("Saudi VAT Return", self.original_return)
		if original.docstatus != 1:
			frappe.throw(_("Only an approved VAT return can be amended"))
		original.check_permission("read")
		self.total_vat_effect = total(row.vat_effect for row in self.lines)
		if self.kind == KIND_LATER_RETURN:
			if abs(D(self.total_vat_effect)) > CORRECTION_LIMIT:
				frappe.throw(
					_(
						"A VAT effect above {0} needs a self-amendment, not a correction in a later return"
					).format(CORRECTION_LIMIT)
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
