# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saudi VAT Filing: what was actually entered on the ZATCA portal for an approved return, field by field."""

import frappe
from frappe import _
from frappe.model.document import Document

from sdce_vat.engine.money import D, q2


class SaudiVATFiling(Document):
	def validate(self):
		vat_return = frappe.get_doc("Saudi VAT Return", self.vat_return)
		if vat_return.docstatus != 1:
			frappe.throw(_("Only an approved VAT return can be filed"))
		vat_return.check_permission("read")
		other = frappe.db.get_value(
			"Saudi VAT Filing",
			{"vat_return": self.vat_return, "docstatus": ["<", 2], "name": ["!=", self.name or ""]},
			"name",
		)
		if other:
			frappe.throw(_("VAT return {0} already has filing {1}").format(self.vat_return, other))
		if self.is_new():
			self.filed_by = frappe.session.user
		self._sync_approved_values(vat_return)
		for row in self.fields:
			row.difference = q2(D(row.filed_vat) - D(row.approved_vat))

	def before_submit(self):
		missing = [
			str(row.box_no) for row in self.fields if _has_difference(row) and not (row.reason or "").strip()
		]
		if missing:
			frappe.throw(_("Give a reason for the difference in field(s) {0}").format(", ".join(missing)))

	def _sync_approved_values(self, vat_return):
		"""Approved values always come from the approved return; filed values are typed by the user."""
		approved = {line.box_id: line for line in vat_return.lines}
		existing = {row.box_id: row for row in self.fields}
		for box_id, line in approved.items():
			row = existing.get(box_id) or self.append(
				"fields",
				{
					"box_id": box_id,
					"filed_amount": line.amount,
					"filed_adjustment": line.adjustment,
					"filed_vat": line.vat,
				},
			)
			row.box_no, row.label = line.box_no, line.label
			row.approved_amount, row.approved_adjustment, row.approved_vat = (
				line.amount,
				line.adjustment,
				line.vat,
			)
		unknown = [row.box_id for row in self.fields if row.box_id not in approved]
		if unknown:
			frappe.throw(_("Unknown return field(s): {0}").format(", ".join(unknown)))


def _has_difference(row) -> bool:
	return any(
		q2(D(row.get(f"filed_{part}"))) != q2(D(row.get(f"approved_{part}")))
		for part in ("amount", "adjustment", "vat")
	)
