# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""KSA VAT Return Detail: the source lines behind one field of the KSA VAT Return, or the lines that need review.

The lines come from the same engine run as the return, so the total of a field's lines equals the field.
"""

import frappe
from frappe import _

from sdce_vat.engine import boxes
from sdce_vat.engine.model import Column
from sdce_vat.saudi_vat.vat_report import CUSTOM, field_lines, run


def execute(filters=None):
	filters = frappe._dict(filters or {})
	field = filters.get("field")
	if not field and not filters.get("exceptions_only"):
		frappe.throw(_("Choose a field or show the exceptions"))
	if field and field not in boxes.BOX_BY_ID:
		frappe.throw(_("Unknown field {0}").format(field))
	result, _start, _end = run(frappe._dict(filters, period_type=CUSTOM))
	return columns(), [row(line) for line in lines(result, field, filters.get("exceptions_only"))]


def lines(result, field, exceptions_only):
	return result.review_lines if exceptions_only else field_lines(result, field)


def row(line):
	box = boxes.BOX_BY_ID.get(line.box)
	return {
		"box_no": box.number if box else None,
		"voucher_type": line.voucher_type,
		"voucher_no": line.voucher_no,
		"posting_date": line.posting_date,
		"invoice_date": line.invoice_date,
		"tax_date": line.tax_date,
		"party_type": line.party_type,
		"party": line.party,
		"party_tax_id": line.party_tax_id,
		"bill_no": line.bill_no,
		"vat_account": line.vat_account,
		"column": column_label(line.column),
		"base": line.base,
		"vat": line.vat,
		"treatment": str(line.treatment) if line.treatment else None,
		"rule_set": line.rule_set,
		"issue": line.rule_issue or (line.reason if line.needs_review else None),
		"warnings": ", ".join(line.warnings),
	}


def column_label(column: Column | None) -> str | None:
	if not column:
		return None
	return _("Adjustment") if column == Column.ADJUSTMENT else _("Amount")


def columns():
	return [
		{"fieldname": "box_no", "label": _("Field"), "fieldtype": "Int", "width": 60},
		{
			"fieldname": "voucher_type",
			"label": _("Voucher Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 130,
		},
		{
			"fieldname": "voucher_no",
			"label": _("Voucher No"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 170,
		},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "invoice_date", "label": _("Invoice Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "tax_date", "label": _("Tax Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "party_type",
			"label": _("Party Type"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 90,
		},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 170,
		},
		{"fieldname": "party_tax_id", "label": _("Party VAT Number"), "fieldtype": "Data", "width": 140},
		{"fieldname": "bill_no", "label": _("Invoice No."), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "vat_account",
			"label": _("VAT Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 160,
		},
		{"fieldname": "column", "label": _("Column"), "fieldtype": "Data", "width": 90},
		{"fieldname": "base", "label": _("Amount (SAR)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "vat", "label": _("VAT Amount (SAR)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "treatment", "label": _("Treatment"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "rule_set",
			"label": _("Rule Set"),
			"fieldtype": "Link",
			"options": "Saudi VAT Rule Set",
			"width": 130,
		},
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Data", "width": 200},
		{"fieldname": "warnings", "label": _("Warnings"), "fieldtype": "Data", "width": 160},
	]
