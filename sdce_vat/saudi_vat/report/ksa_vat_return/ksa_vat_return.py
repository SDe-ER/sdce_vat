# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""KSA VAT Return: the fields of the ZATCA return for one company and period, read from ERPNext documents.

Generating the report writes nothing. A saved copy is made only on request (`save_snapshot`).
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt, getdate

from sdce_vat.constants import VAT_PREPARER
from sdce_vat.engine import boxes
from sdce_vat.saudi_vat.vat_report import ACCRUAL, box_label, period, run


def execute(filters=None):
	filters = frappe._dict(filters or {})
	result, start, end = run(filters)
	data = [
		{
			"box_id": box.id,
			"box_no": box.number,
			"label": box_label(box),
			"amount": result.boxes[box.id].amount,
			"adjustment": result.boxes[box.id].adjustment,
			"vat": result.boxes[box.id].vat,
			"line_count": len(result.boxes[box.id].lines),
			"is_total": int(box.is_total),
			"bold": int(box.is_total),
			# the resolved period, so the links to the details need no date logic in the browser
			"from_date": str(start),
			"to_date": str(end),
		}
		for box in boxes.BOXES
	]
	return columns(), data, message(result), None, summary(result, start, end)


def columns():
	return [
		{"fieldname": "box_no", "label": _("Field"), "fieldtype": "Int", "width": 70},
		{"fieldname": "label", "label": _("Description"), "fieldtype": "Data", "width": 420},
		{"fieldname": "amount", "label": _("Amount (SAR)"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "adjustment", "label": _("Adjustment (SAR)"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "vat", "label": _("VAT Amount (SAR)"), "fieldtype": "Currency", "width": 160},
		{"fieldname": "line_count", "label": _("Source Lines"), "fieldtype": "Int", "width": 110},
		{"fieldname": "box_id", "label": _("Field ID"), "fieldtype": "Data", "hidden": 1},
	]


def summary(result, start, end):
	ready = not result.review_lines and result.is_reconciled
	return [
		{
			"value": result.boxes[boxes.NET_VAT].vat,
			"label": _("Net VAT"),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"value": _("Yes") if result.is_reconciled else _("No"),
			"label": _("Reconciled with General Ledger"),
			"datatype": "Data",
			"indicator": "Green" if result.is_reconciled else "Red",
		},
		{
			"value": len(result.review_lines),
			"label": _("Sources Needing Review"),
			"datatype": "Int",
			"indicator": "Green" if not result.review_lines else "Red",
		},
		{
			"value": len(result.warning_lines),
			"label": _("Sources with Warnings"),
			"datatype": "Int",
			"indicator": "Green" if not result.warning_lines else "Orange",
		},
		{
			"value": _("Ready for review") if ready else _("Not approvable"),
			"label": _("Status"),
			"datatype": "Data",
			"indicator": "Green" if ready else "Red",
		},
		{
			"value": f"{start} → {end}",
			"label": _("Period"),
			"datatype": "Data",
			"indicator": "Grey",
		},
	]


def message(result):
	"""A clear notice when the figures cannot be approved as they are. Never a reason to hide them."""
	notes = []
	if result.review_lines:
		notes.append(
			# one literal per message: the translation extractor reads single strings
			_(
				"{0} source lines are not placed in any field (missing or unverified rules, unknown tax dates or unclassified documents). Open the details to review them."
			).format(len(result.review_lines))
		)
	if not result.is_reconciled:
		notes.append(_("The VAT accounts do not reconcile with the general ledger."))
	if not result.rule_sets and result.lines:
		notes.append(_("No published rule set was used; set the rule-set code in Saudi VAT Settings."))
	if not notes:
		return None
	items = "".join(f"<li>{escape_html(note)}</li>" for note in notes)
	return f"<div class='text-danger'><b>{escape_html(_('Not approvable'))}</b><ul>{items}</ul></div>"


@frappe.whitelist(methods=["POST"])
def save_snapshot(filters) -> str:
	"""Save the report of the filters as the draft Saudi VAT Return of that period and calculate it.

	A draft of exactly this period is recalculated; any other return touching the period is left alone and
	the save is refused. Saving is not approval: review, approval and filing stay on the return's workflow.
	"""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if not isinstance(filters, dict):
		frappe.throw(_("Invalid filters"))
	filters = frappe._dict(filters)
	if VAT_PREPARER not in frappe.get_roles():
		frappe.throw(_("Only a VAT Preparer can save a snapshot"), frappe.PermissionError)
	if not isinstance(filters.get("company"), str) or not filters.company:
		frappe.throw(_("Set a company"))
	if (filters.get("tax_basis") or ACCRUAL) != ACCRUAL:
		frappe.throw(_("Only the accrual basis is supported"))
	if not frappe.has_permission("Company", "read", doc=filters.company):
		frappe.throw(_("Not permitted for company {0}").format(filters.company), frappe.PermissionError)
	start, end = period(filters)
	inputs = {
		"corrections": flt(filters.get("corrections")),
		"credit_carried": flt(filters.get("credit_carried")),
	}

	others = frappe.get_all(
		"Saudi VAT Return",
		filters={
			"company": filters.company,
			"docstatus": ["<", 2],
			"from_date": ["<=", end],
			"to_date": [">=", start],
		},
		fields=["name", "from_date", "to_date", "docstatus"],
	)
	approved = [r.name for r in others if r.docstatus == 1]
	if approved:
		frappe.throw(
			_(
				"VAT return {0} is approved for this period; record a correction with a Saudi VAT Amendment instead"
			).format(approved[0])
		)
	same = [r for r in others if (getdate(r.from_date), getdate(r.to_date)) == (start, end)]
	if len(others) != len(same):
		frappe.throw(_("VAT return {0} already covers part of this period").format(others[0].name))

	if same:
		doc = frappe.get_doc("Saudi VAT Return", same[0].name)
		doc.check_permission("write")
		if any(flt(doc.get(field)) != value for field, value in inputs.items()):
			doc.update(inputs)
			doc.save()
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Saudi VAT Return",
				"company": filters.company,
				"from_date": start,
				"to_date": end,
				**inputs,
			}
		).insert()
	doc.calculate()
	return doc.name
