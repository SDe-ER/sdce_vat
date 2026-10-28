# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Negative authorization tests: API calls, direct submit, field and state tampering, roles and two companies."""

import frappe
import frappe.client
from frappe.model.workflow import apply_workflow

from sdce_vat.constants import VAT_APPROVER, VAT_PREPARER, VAT_REVIEWER
from sdce_vat.tests.site_base import COMPANY, DATE, FROM, ITEM, SUPPLIER, TO, VatSiteTestCase, make_user

COMPANY_B = "_Test VAT Co B"
ABBR_B = "_TVB"
PREPARER = "vat-sec-preparer@example.com"
REVIEWER = "vat-sec-reviewer@example.com"
APPROVER = "vat-sec-approver@example.com"
PREPARER_B = "vat-sec-preparer-b@example.com"
NO_ROLE = "vat-sec-no-role@example.com"
DENIED = (frappe.ValidationError, frappe.PermissionError)


class TestSecurity(VatSiteTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pi_no_vat.cancel()
		cls.make_settings()
		cls._company_b()
		for email, role in ((PREPARER, VAT_PREPARER), (REVIEWER, VAT_REVIEWER), (APPROVER, VAT_APPROVER)):
			make_user(email, role)
			cls._restrict(email, COMPANY)
		make_user(PREPARER_B, VAT_PREPARER)
		cls._restrict(PREPARER_B, COMPANY_B)
		make_user(NO_ROLE)

	@classmethod
	def _restrict(cls, email, company):
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Company", "for_value": company}
		).insert(ignore_permissions=True)

	@classmethod
	def _company_b(cls):
		if not frappe.db.exists("Company", COMPANY_B):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": COMPANY_B,
					"abbr": ABBR_B,
					"country": "Saudi Arabia",
					"default_currency": "SAR",
					"create_chart_of_accounts_based_on": "Standard Template",
					"chart_of_accounts": "Standard",
				}
			).insert(ignore_permissions=True)
		group = frappe.db.get_value("Account", {"company": COMPANY_B, "account_name": "Duties and Taxes"})
		accounts = {}
		for name in ("VAT Output", "VAT Input"):
			full = f"{name} - {ABBR_B}"
			if not frappe.db.exists("Account", full):
				frappe.get_doc(
					{
						"doctype": "Account",
						"account_name": name,
						"parent_account": group,
						"company": COMPANY_B,
						"account_type": "Tax",
					}
				).insert(ignore_permissions=True)
			accounts[name] = full
		cls.vat_in_b = accounts["VAT Input"]
		frappe.get_doc(
			{
				"doctype": "Saudi VAT Settings",
				"company": COMPANY_B,
				"accounts": [
					{"account": accounts["VAT Output"], "family": "Output", "rate": 15},
					{"account": accounts["VAT Input"], "family": "Input", "rate": 15},
				],
			}
		).insert(ignore_permissions=True)
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY_B,
				"posting_date": DATE,
				"set_posting_time": 1,
				"supplier": SUPPLIER,
				"currency": "SAR",
				"bill_no": "B-ONLY",
				"bill_date": DATE,
				"items": [{"item_code": ITEM, "qty": 1, "rate": 700}],
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": accounts["VAT Input"],
						"rate": 15,
						"description": "VAT",
					}
				],
			}
		).insert(ignore_permissions=True)
		pi.submit()
		cls.pi_b = pi.name

	def setUp(self):
		frappe.db.savepoint("vat_security_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="vat_security_test")

	def _new_return(self, user=PREPARER, company=COMPANY):
		frappe.set_user(user)
		doc = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": company, "from_date": FROM, "to_date": TO}
		)
		doc.insert()
		doc.calculate()
		return frappe.get_doc("Saudi VAT Return", doc.name)

	def _step(self, name, user, action):
		frappe.set_user(user)
		return apply_workflow(frappe.get_doc("Saudi VAT Return", name), action)

	# ---- API and direct submit ------------------------------------------------------------------------------
	def test_api_submit_of_a_draft_is_refused(self):
		doc = self._new_return()
		frappe.set_user(APPROVER)
		self.assertRaises(
			DENIED, frappe.client.submit, frappe.get_doc("Saudi VAT Return", doc.name).as_dict()
		)

	def test_api_set_value_on_calculated_field_is_refused(self):
		doc = self._new_return()
		frappe.set_user(PREPARER)
		self.assertRaises(DENIED, frappe.client.set_value, "Saudi VAT Return", doc.name, "net_vat", 1)
		self.assertRaises(
			DENIED, frappe.client.set_value, "Saudi VAT Return", doc.name, "reviewed_by", REVIEWER
		)

	def test_direct_state_change_without_transition_is_refused(self):
		doc = self._new_return()
		frappe.set_user(PREPARER)
		doc.workflow_state = "VAT Reviewed"
		self.assertRaises(DENIED, doc.save)

	def test_reviewer_cannot_change_inputs_of_a_prepared_return(self):
		doc = self._new_return()
		self._step(doc.name, PREPARER, "Prepare VAT Return")
		frappe.set_user(REVIEWER)
		prepared = frappe.get_doc("Saudi VAT Return", doc.name)
		prepared.corrections = 100
		self.assertRaises(DENIED, prepared.save)

	def test_approved_return_api_update_is_refused(self):
		doc = self._new_return()
		self._step(doc.name, PREPARER, "Prepare VAT Return")
		self._step(doc.name, REVIEWER, "Review VAT Return")
		self._step(doc.name, APPROVER, "Approve VAT Return")
		frappe.set_user(APPROVER)
		self.assertRaises(DENIED, frappe.client.set_value, "Saudi VAT Return", doc.name, "corrections", 50)

	# ---- roles -----------------------------------------------------------------------------------------------
	def test_user_without_vat_role_cannot_read_or_calculate(self):
		doc = self._new_return()
		frappe.set_user(NO_ROLE)
		self.assertFalse(frappe.has_permission("Saudi VAT Return", "read", doc=doc.name))
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Saudi VAT Return", doc.name).calculate)

	def test_preparer_cannot_change_settings(self):
		frappe.set_user(PREPARER)
		settings = frappe.get_doc("Saudi VAT Settings", COMPANY)
		settings.tolerance = 5
		self.assertRaises(frappe.PermissionError, settings.save)

	def test_approver_cannot_calculate(self):
		doc = self._new_return()
		frappe.set_user(APPROVER)
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Saudi VAT Return", doc.name).calculate)

	# ---- two companies -------------------------------------------------------------------------------------
	def test_each_company_gets_its_own_return_for_the_same_period(self):
		a = self._new_return(PREPARER, COMPANY)
		b = self._new_return(PREPARER_B, COMPANY_B)
		self.assertNotIn(self.pi_b, {s.voucher_no for s in a.sources})
		self.assertEqual({s.voucher_no for s in b.sources}, {self.pi_b})

	def test_user_of_company_a_cannot_see_or_use_company_b(self):
		b = self._new_return(PREPARER_B, COMPANY_B)
		frappe.set_user(PREPARER)
		self.assertFalse(frappe.has_permission("Saudi VAT Return", "read", doc=b.name))
		self.assertNotIn(b.name, frappe.get_list("Saudi VAT Return", pluck="name"))
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Saudi VAT Return", b.name).calculate)
		other = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY_B, "from_date": FROM, "to_date": TO}
		)
		self.assertRaises(frappe.PermissionError, other.insert)

	def test_rule_sets_are_shared_while_returns_stay_per_company(self):
		frappe.db.set_value("Saudi VAT Settings", COMPANY_B, "rule_set_code", "TEST-PARITY")
		a = self._new_return(PREPARER, COMPANY)
		b = self._new_return(PREPARER_B, COMPANY_B)
		self.assertEqual([r.rule_set for r in a.rule_sets], [r.rule_set for r in b.rule_sets])
		self.assertEqual({s.voucher_no for s in b.sources}, {self.pi_b})
		self.assertFalse(frappe.get_meta("Saudi VAT Rule Set").has_field("company"))
		frappe.set_user(PREPARER_B)
		self.assertTrue(frappe.has_permission("Saudi VAT Rule Set", "read", doc=b.rule_sets[0].rule_set))
		self.assertFalse(frappe.has_permission("Saudi VAT Return", "read", doc=a.name))

	def test_settings_of_one_company_reject_accounts_of_another(self):
		settings = frappe.get_doc("Saudi VAT Settings", COMPANY_B)
		settings.append("accounts", {"account": self.vat_in, "family": "Input", "rate": 15})
		self.assertRaises(frappe.ValidationError, settings.save, ignore_permissions=True)
