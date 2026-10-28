# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Site entry point: read one company and period, calculate, and prove no database write happened."""

import frappe
from frappe import _

from sdce_vat.engine.config import VatConfig
from sdce_vat.engine.core import calculate
from sdce_vat.engine.model import VatResult
from sdce_vat.engine.sources import read_gl, read_lines


def compute(config: VatConfig, from_date: str, to_date: str, corrections=0, credit_carried=0) -> VatResult:
	if not frappe.has_permission("GL Entry", "read"):
		frappe.throw(_("Not permitted to read the general ledger"), frappe.PermissionError)
	if not frappe.has_permission("Company", "read", doc=config.company):
		frappe.throw(_("Not permitted for company {0}").format(config.company), frappe.PermissionError)

	writes_before = frappe.db.transaction_writes
	result = calculate(
		config,
		str(from_date),
		str(to_date),
		read_lines(config, from_date, to_date),
		read_gl(config, from_date, to_date),
		corrections=corrections,
		credit_carried=credit_carried,
	)
	if frappe.db.transaction_writes != writes_before:
		raise RuntimeError("The VAT engine must not write to the database")
	return result
