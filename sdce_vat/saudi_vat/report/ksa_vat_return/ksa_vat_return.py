# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""KSA VAT Return: the fields of the ZATCA return for one company and period, read from ERPNext documents.

Generating the report writes nothing.
"""

import frappe
from frappe import _
from frappe.utils import escape_html

from sdce_vat.engine import boxes
from sdce_vat.saudi_vat.vat_report import box_label, run


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

