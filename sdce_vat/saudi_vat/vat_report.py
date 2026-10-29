# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared by the KSA VAT Return reports: the period from the report filters and a read-only engine run.

Generating a report never creates a record; `compute` proves that no database write happened.
"""

import calendar
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, getdate

from sdce_vat.engine import boxes
from sdce_vat.engine.model import VatResult
from sdce_vat.engine.money import D
from sdce_vat.engine.run import compute
from sdce_vat.saudi_vat.doctype.saudi_vat_settings.saudi_vat_settings import get_settings

MONTHLY, QUARTERLY, CUSTOM = "Monthly", "Quarterly", "Custom"
QUARTERS = ("Q1", "Q2", "Q3", "Q4")
ACCRUAL = "Accrual"  # the only tax basis supported for now

# the line fields whose lines make up each field of the return; corrections and credit carried have none
MEMBERS = {box_id: (box_id,) for box_id in boxes.LINE_BOXES}
MEMBERS[boxes.SALES_TOTAL] = boxes.SALES_LINE_BOXES
MEMBERS[boxes.PURCHASES_TOTAL] = boxes.PURCHASE_LINE_BOXES
MEMBERS[boxes.VAT_DUE] = boxes.LINE_BOXES
MEMBERS[boxes.NET_VAT] = boxes.LINE_BOXES


def period(filters) -> tuple[date, date]:
	"""First and last day of the period chosen in the filters."""
	kind = filters.get("period_type") or MONTHLY
	if kind == CUSTOM:
		if not filters.get("from_date") or not filters.get("to_date"):
			frappe.throw(_("Set From Date and To Date for a custom period"))
		start, end = getdate(filters.get("from_date")), getdate(filters.get("to_date"))
	else:
		year = cint(filters.get("year"))
		if not 2000 <= year <= 2100:
			frappe.throw(_("Set a valid year"))
		if kind == MONTHLY:
			month = cint(filters.get("month"))
			if not 1 <= month <= 12:
				frappe.throw(_("Set a month between 1 and 12"))
			first_month, last_month = month, month
		elif kind == QUARTERLY:
			if filters.get("quarter") not in QUARTERS:
				frappe.throw(_("Set a quarter"))
			first_month = QUARTERS.index(filters.get("quarter")) * 3 + 1
			last_month = first_month + 2
		else:
			frappe.throw(_("Unknown period type {0}").format(kind))
		start = date(year, first_month, 1)
		end = date(year, last_month, calendar.monthrange(year, last_month)[1])
	if start > end:
		frappe.throw(_("From Date must be on or before To Date"))
	return start, end


def run(filters) -> tuple[VatResult, date, date]:
	"""The engine result for the company and period of the filters. Read permission is checked here and in
	`compute` (general ledger, company, rule sets)."""
	company = filters.get("company")
	if not company or not isinstance(company, str):
		frappe.throw(_("Set a company"))
	if (filters.get("tax_basis") or ACCRUAL) != ACCRUAL:
		frappe.throw(_("Only the accrual basis is supported"))
	start, end = period(filters)
	settings = get_settings(company)
	settings.check_permission("read")
	result = compute(
		settings.to_config(),
		str(start),
		str(end),
		corrections=D(filters.get("corrections") or 0),
		credit_carried=D(filters.get("credit_carried") or 0),
	)
	return result, start, end


def box_label(box: boxes.Box) -> str:
	"""The ZATCA wording of a field in the user's language. Both texts are the official labels of the form
	(see `engine.boxes`), not translations, so they are taken as they are."""
	return box.label_ar if (frappe.local.lang or "").startswith("ar") else box.label_en


def field_lines(result: VatResult, field: str) -> list:
	"""The placed source lines that make up one field of the return."""
	return [line for line in result.lines if line.box in MEMBERS.get(field, ())]
