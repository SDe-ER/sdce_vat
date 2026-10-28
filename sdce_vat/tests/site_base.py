# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared site fixtures for integration tests."""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase

from sdce_vat.engine.config import VatConfig

COMPANY = "_Test VAT Co"
ABBR = "_TSV"
DATE = "2026-07-15"
FROM, TO = "2026-07-01", "2026-09-30"
SUPPLIER = "_Test VAT Supplier"
CUSTOMER = "_Test VAT Customer"
ITEM = "_Test VAT Item"


def _first(doctype, **filters):
	return frappe.get_all(doctype, filters=filters, pluck="name", limit=1)[0]


class VatSiteTestCase(IntegrationTestCase):
	"""A throw-away company with VAT accounts and a few submitted documents; rolled back after the class."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Company", COMPANY):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY,
					"abbr": ABBR,
					"country": "Saudi Arabia",
					"default_currency": "SAR",
					"create_chart_of_accounts_based_on": "Standard Template",
					"chart_of_accounts": "Standard",
				}
			).insert(ignore_permissions=True)
		taxes_group = frappe.db.get_value("Account", {"company": COMPANY, "account_name": "Duties and Taxes"})
		cls.vat_out = cls._account("VAT Output", taxes_group)
		cls.vat_in = cls._account("VAT Input", taxes_group)
		cls.expense = frappe.db.get_value("Company", COMPANY, "default_expense_account")
		cls.creditors = frappe.db.get_value("Company", COMPANY, "default_payable_account")
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": SUPPLIER,
					"supplier_group": _first("Supplier Group", is_group=0),
					"tax_id": "300000000000003",
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_group": _first("Customer Group", is_group=0),
					"territory": _first("Territory"),
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": _first("Item Group", is_group=0),
					"stock_uom": _first("UOM"),
					"is_stock_item": 0,
				}
			).insert(ignore_permissions=True)

		cls.pi = cls._invoice("Purchase Invoice", 1000, cls.vat_in)
		cls.pi_no_vat = cls._invoice("Purchase Invoice", 50, None)
		cls.pi_cancelled = cls._invoice("Purchase Invoice", 200, cls.vat_in)
		cls.pi_cancelled.cancel()
		cls.si = cls._invoice("Sales Invoice", 2000, cls.vat_out)
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		credit_note = make_return_doc("Sales Invoice", cls.si.name)
		credit_note.posting_date = DATE
		credit_note.set_posting_time = 1
		credit_note.insert(ignore_permissions=True).submit()
		cls.credit_note = credit_note
		cls.je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": DATE,
				"cheque_no": "J-77",
				"cheque_date": DATE,
				"accounts": [
					{"account": cls.expense, "debit_in_account_currency": 400},
					{"account": cls.vat_in, "debit_in_account_currency": 60},
					{
						"account": cls.creditors,
						"credit_in_account_currency": 460,
						"party_type": "Supplier",
						"party": SUPPLIER,
					},
				],
			}
		).insert(ignore_permissions=True)
		cls.je.submit()
		cls.config = VatConfig(
			company=COMPANY,
			output_accounts={cls.vat_out: Decimal("15")},
			input_accounts={cls.vat_in: Decimal("15")},
		)

	@classmethod
	def _account(cls, name, parent):
		full = f"{name} - {ABBR}"
		if not frappe.db.exists("Account", full):
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": name,
					"parent_account": parent,
					"company": COMPANY,
					"account_type": "Tax",
				}
			).insert(ignore_permissions=True)
		return full

	@classmethod
	def _invoice(cls, doctype, rate, vat_account):
		doc = frappe.get_doc(
			{
				"doctype": doctype,
				"company": COMPANY,
				"posting_date": DATE,
				"set_posting_time": 1,
				"supplier" if doctype == "Purchase Invoice" else "customer": SUPPLIER
				if doctype == "Purchase Invoice"
				else CUSTOMER,
				"currency": "SAR",
				"items": [{"item_code": ITEM, "qty": 1, "rate": rate}],
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": vat_account,
						"rate": 15,
						"description": "VAT 15%",
					}
				]
				if vat_account
				else [],
			}
		)
		if doctype == "Purchase Invoice":
			doc.bill_no = f"B-{rate}"
			doc.bill_date = DATE
		if doctype == "Sales Invoice":
			doc.due_date = DATE
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	@classmethod
	def make_settings(cls, **values):
		if frappe.db.exists("Saudi VAT Settings", COMPANY):
			frappe.delete_doc("Saudi VAT Settings", COMPANY, ignore_permissions=True, force=True)
		settings = frappe.get_doc(
			{
				"doctype": "Saudi VAT Settings",
				"company": COMPANY,
				"accounts": [
					{"account": cls.vat_out, "family": "Output", "rate": 15},
					{"account": cls.vat_in, "family": "Input", "rate": 15},
				],
				**values,
			}
		)
		return settings.insert(ignore_permissions=True)


def make_user(email, *roles):
	"""A desk user with the given roles; Accounts User gives the general ledger read access the engine needs."""
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0]})
		user.insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.add_roles("Accounts User", *roles)
	return email
