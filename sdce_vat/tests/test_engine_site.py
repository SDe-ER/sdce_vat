# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Integration tests: real ERPNext documents in a throw-away test company, rolled back after the class."""

from decimal import Decimal

import frappe

from sdce_vat.engine import boxes
from sdce_vat.engine.config import VatConfig
from sdce_vat.engine.model import Treatment
from sdce_vat.engine.run import compute
from sdce_vat.tests.site_base import (
	COMPANY,
	CUSTOMER,
	DATE,
	FROM,
	ITEM,
	SUPPLIER,
	TO,
	VatSiteTestCase,
	make_other_company_tax_account,
)


class TestEngineOnSite(VatSiteTestCase):
	def _result(self):
		return compute(self.config, FROM, TO)

	def test_boxes_from_real_documents(self):
		result = self._result()
		s01 = result.boxes[boxes.SALES_STANDARD]
		self.assertEqual(
			(s01.amount, s01.adjustment, s01.vat), (Decimal("2000.00"), Decimal("-2000.00"), Decimal("0.00"))
		)
		p07 = result.boxes[boxes.PURCHASES_STANDARD]
		self.assertEqual((p07.amount, p07.vat), (Decimal("1400.00"), Decimal("210.00")))
		self.assertTrue(result.is_reconciled)

	def test_cancelled_document_is_not_counted(self):
		self.assertNotIn(self.pi_cancelled.name, {line.voucher_no for line in self._result().lines})

	def test_zero_vat_invoice_waits_for_review(self):
		line = next(x for x in self._result().lines if x.voucher_no == self.pi_no_vat.name)
		self.assertEqual(line.treatment, Treatment.NEEDS_REVIEW)
		self.assertIsNone(line.box)

	def test_lines_are_traceable(self):
		result = self._result()
		for line in result.lines:
			self.assertTrue(line.voucher_type and line.voucher_no)
		pi_line = next(x for x in result.lines if x.voucher_no == self.pi.name)
		self.assertTrue(pi_line.source_rows)
		self.assertEqual(pi_line.bill_no, "B-1000")
		je_line = next(x for x in result.lines if x.voucher_no == self.je.name)
		self.assertEqual((je_line.base, je_line.party), (Decimal("400.00"), SUPPLIER))
		self.assertIn("journal_entry_claim_needs_document_review", je_line.warnings)

	def test_only_the_requested_company(self):
		self.assertEqual({line.company for line in self._result().lines}, {COMPANY})

	def test_engine_does_not_write(self):
		counts = {
			dt: frappe.db.count(dt)
			for dt in ("GL Entry", "Purchase Invoice", "Sales Invoice", "Journal Entry")
		}
		writes = frappe.db.transaction_writes
		self._result()
		self.assertEqual(frappe.db.transaction_writes, writes)
		self.assertEqual(
			counts,
			{
				dt: frappe.db.count(dt)
				for dt in ("GL Entry", "Purchase Invoice", "Sales Invoice", "Journal Entry")
			},
		)

	def test_user_without_company_permission_is_denied(self):
		email = "vat-engine-denied@example.com"
		if not frappe.db.exists("User", email):
			user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "VAT Denied"})
			user.insert(ignore_permissions=True)
			user.add_roles("Accounts User")
		other = frappe.get_all("Company", filters={"name": ["!=", COMPANY]}, pluck="name", limit=1)
		if not other:  # a fresh site has only the test company
			other = [frappe.db.get_value("Account", make_other_company_tax_account(), "company")]
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Company", "for_value": other[0]}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				self._result()
		finally:
			frappe.set_user("Administrator")

	def test_ksa_compliance_fields_are_optional(self):
		installed = "ksa_compliance" in frappe.get_installed_apps()
		has_field = frappe.get_meta("Sales Invoice Item").has_field("custom_zatca_item_tax_category")
		self.assertEqual(installed, has_field)
		self._result()  # runs whether the app is there or not

	def test_ksa_compliance_category_classifies_a_sale_without_vat(self):
		if "ksa_compliance" not in frappe.get_installed_apps():
			self.skipTest("ksa_compliance not installed")
		category = "Zero rated goods || Export of goods"
		template = frappe.get_doc(
			{
				"doctype": "Item Tax Template",
				"title": "_Test VAT Export",
				"company": COMPANY,
				"custom_zatca_item_tax_category": category,
				"taxes": [{"tax_type": self.vat_out, "tax_rate": 0}],
			}
		).insert(ignore_permissions=True)
		sale = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": COMPANY,
				"posting_date": DATE,
				"set_posting_time": 1,
				"due_date": DATE,
				"customer": CUSTOMER,
				"currency": "SAR",
				"items": [{"item_code": ITEM, "qty": 1, "rate": 300, "item_tax_template": template.name}],
			}
		).insert(ignore_permissions=True)
		sale.submit()
		config = VatConfig(
			company=COMPANY,
			output_accounts={self.vat_out: Decimal("15")},
			input_accounts={self.vat_in: Decimal("15")},
			category_treatments={category: Treatment.EXPORT},
			rule_set_code=self.config.rule_set_code,  # rule books are required input since engine 0.2.0
		)
		line = next(x for x in compute(config, FROM, TO).lines if x.voucher_no == sale.name)
		self.assertIn(category, line.zatca_categories)
		self.assertEqual((line.box, line.base), (boxes.SALES_EXPORTS, Decimal("300.00")))
