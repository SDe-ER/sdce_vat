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


def _first_or_make(doctype, filters=None, **values):
	"""An existing record, or a new synthetic one on a fresh site where the setup wizard never ran."""
	found = frappe.get_all(doctype, filters=filters or {}, pluck="name", limit=1)
	if found:
		return found[0]
	return frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True).name


def _ensure_masters():
	"""Masters that ERPNext creates in the setup wizard, not on install (CI uses a fresh site)."""
	if not frappe.db.exists("Warehouse Type", "Transit"):
		frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(ignore_permissions=True)
	for party_type, account_type in (("Supplier", "Payable"), ("Customer", "Receivable")):
		if not frappe.db.exists("Party Type", party_type):
			frappe.get_doc(
				{"doctype": "Party Type", "party_type": party_type, "account_type": account_type}
			).insert(ignore_permissions=True)
	year = DATE[:4]
	if not frappe.db.exists(
		"Fiscal Year", {"year_start_date": ("<=", DATE), "year_end_date": (">=", DATE), "disabled": 0}
	):
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": f"_Test VAT {year}",
				"year_start_date": f"{year}-01-01",
				"year_end_date": f"{year}-12-31",
			}
		).insert(ignore_permissions=True)


class VatSiteTestCase(IntegrationTestCase):
	"""A throw-away company with VAT accounts and a few submitted documents; rolled back after the class."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_masters()
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
					"supplier_group": _first_or_make(
						"Supplier Group",
						{"is_group": 0},
						supplier_group_name="_Test VAT Supplier Group",
					),
					"tax_id": "300000000000003",
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": CUSTOMER,
					"customer_group": _first_or_make(
						"Customer Group",
						{"is_group": 0},
						customer_group_name="_Test VAT Customer Group",
					),
					"territory": _first_or_make("Territory", territory_name="_Test VAT Territory"),
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ITEM,
					"item_name": ITEM,
					"item_group": _first_or_make(
						"Item Group",
						{"is_group": 0},
						item_group_name="_Test VAT Item Group",
					),
					"stock_uom": _first_or_make("UOM", uom_name="_Test VAT Unit"),
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
			doc.selling_price_list = _first_or_make(
				"Price List",
				{"selling": 1, "enabled": 1, "currency": "SAR"},
				price_list_name="_Test VAT Selling",
				selling=1,
				currency="SAR",
			)
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
