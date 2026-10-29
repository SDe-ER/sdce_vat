# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Phase 3: return lifecycle, separation of duties, snapshot integrity, filing and amendment."""

import frappe
from frappe.model.workflow import apply_workflow

from sdce_vat.constants import VAT_APPROVER, VAT_PREPARER, VAT_REVIEWER
from sdce_vat.tests.site_base import (
	COMPANY,
	DATE,
	FROM,
	ITEM,
	SUPPLIER,
	TO,
	VatSiteTestCase,
	make_other_company_tax_account,
	make_user,
)

PREPARER = "vat-preparer@example.com"
REVIEWER = "vat-reviewer@example.com"
APPROVER = "vat-approver@example.com"
DOUBLE = "vat-preparer-reviewer@example.com"
DENIED = (frappe.ValidationError, frappe.PermissionError)


class TestVatReturn(VatSiteTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pi_no_vat.cancel()  # no unclassified source left in the period: approval can succeed
		cls.make_settings()
		make_user(PREPARER, VAT_PREPARER)
		make_user(REVIEWER, VAT_REVIEWER)
		make_user(APPROVER, VAT_APPROVER)
		make_user(DOUBLE, VAT_PREPARER, VAT_REVIEWER)

	def setUp(self):
		frappe.db.savepoint("vat_return_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="vat_return_test")

	# ---- helpers --------------------------------------------------------------------------------------
	def _calculated(self, user=PREPARER):
		frappe.set_user(user)
		doc = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": FROM, "to_date": TO}
		)
		doc.insert()
		doc.calculate()
		return doc

	def _step(self, doc, user, action):
		frappe.set_user(user)
		doc = frappe.get_doc("Saudi VAT Return", doc.name)
		return apply_workflow(doc, action)

	def _approved(self):
		doc = self._calculated()
		self._step(doc, PREPARER, "Prepare VAT Return")
		self._step(doc, REVIEWER, "Review VAT Return")
		return self._step(doc, APPROVER, "Approve VAT Return")

	# ---- settings -------------------------------------------------------------------------------------
	def test_settings_refuse_foreign_and_non_tax_accounts(self):
		other = frappe.db.get_value("Account", {"company": ["!=", COMPANY], "account_type": "Tax"})
		if not other:  # a fresh site has only the test company: add a second one with a Tax account
			other = make_other_company_tax_account()
		settings = frappe.get_doc("Saudi VAT Settings", COMPANY)
		settings.append("accounts", {"account": other, "family": "Input", "rate": 15})
		self.assertRaises(frappe.ValidationError, settings.save, ignore_permissions=True)
		settings.reload()
		settings.append("accounts", {"account": self.expense, "family": "Input", "rate": 15})
		self.assertRaises(frappe.ValidationError, settings.save, ignore_permissions=True)

	# ---- calculation ----------------------------------------------------------------------------------
	def test_calculation_stores_engine_result(self):
		doc = self._calculated()
		by_box = {row.box_id: row for row in doc.lines}
		self.assertEqual(len(doc.lines), 16)
		self.assertEqual((by_box["P07"].vat, by_box["S01"].vat), (210, 0))
		self.assertTrue(doc.calculation_hash and doc.gl_reconciled)
		self.assertEqual(doc.review_count, 0)
		self.assertTrue(all(row.voucher_no for row in doc.sources))

	def test_only_a_preparer_calculates(self):
		doc = self._calculated()
		frappe.set_user(REVIEWER)
		doc = frappe.get_doc("Saudi VAT Return", doc.name)
		self.assertRaises(DENIED, doc.calculate)

	def test_calculated_values_cannot_be_edited(self):
		doc = self._calculated()
		doc.reload()
		doc.sources[0].vat = 999
		self.assertRaises(frappe.ValidationError, doc.save)
		doc.reload()
		doc.calculation_hash = "x" * 64
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_new_return_cannot_bring_its_own_values(self):
		frappe.set_user(PREPARER)
		doc = frappe.get_doc(
			{
				"doctype": "Saudi VAT Return",
				"company": COMPANY,
				"from_date": FROM,
				"to_date": TO,
				"calculation_hash": "y" * 64,
				"approved_by": APPROVER,
				"lines": [{"box_id": "P07", "vat": 1}],
			}
		).insert()
		self.assertFalse(doc.calculation_hash or doc.approved_by or doc.lines)

	def test_overlapping_period_is_refused(self):
		self._calculated()
		other = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": DATE, "to_date": TO}
		)
		self.assertRaises(frappe.ValidationError, other.insert)

	# ---- workflow and separation of duties -----------------------------------------------------------
	def test_full_approval_creates_snapshot_and_no_ledger_entry(self):
		gl_before = frappe.db.count("GL Entry")
		doc = self._approved()
		self.assertEqual((doc.docstatus, doc.workflow_state), (1, "VAT Approved"))
		self.assertEqual((doc.prepared_by, doc.reviewed_by, doc.approved_by), (PREPARER, REVIEWER, APPROVER))
		self.assertEqual(frappe.db.count("GL Entry"), gl_before)
		self.assertEqual(doc.verify_snapshot(), {"approved": True, "file_ok": True, "tables_ok": True})

	def test_reviewer_cannot_review_own_preparation(self):
		doc = self._calculated(DOUBLE)
		self._step(doc, DOUBLE, "Prepare VAT Return")
		self.assertRaises(DENIED, self._step, doc, DOUBLE, "Review VAT Return")

	def test_preparer_cannot_review(self):
		doc = self._calculated()
		self._step(doc, PREPARER, "Prepare VAT Return")
		self.assertRaises(DENIED, self._step, doc, PREPARER, "Review VAT Return")

	def test_approver_must_differ_from_reviewer(self):
		make_user(REVIEWER, VAT_APPROVER)
		try:
			doc = self._calculated()
			self._step(doc, PREPARER, "Prepare VAT Return")
			self._step(doc, REVIEWER, "Review VAT Return")
			self.assertRaises(DENIED, self._step, doc, REVIEWER, "Approve VAT Return")
		finally:
			frappe.set_user("Administrator")
			frappe.get_doc("User", REVIEWER).remove_roles(VAT_APPROVER)

	def test_direct_submit_without_review_is_refused(self):
		doc = self._calculated()
		frappe.set_user(APPROVER)
		draft = frappe.get_doc("Saudi VAT Return", doc.name)
		self.assertRaises(DENIED, draft.submit)
		self._step(doc, PREPARER, "Prepare VAT Return")
		frappe.set_user(APPROVER)
		prepared = frappe.get_doc("Saudi VAT Return", doc.name)
		self.assertRaises(DENIED, prepared.submit)

	def test_rejection_clears_the_earlier_review(self):
		doc = self._calculated()
		self._step(doc, PREPARER, "Prepare VAT Return")
		self._step(doc, REVIEWER, "Review VAT Return")
		rejected = self._step(doc, APPROVER, "Reject VAT Return")
		self.assertEqual(
			(rejected.workflow_state, rejected.prepared_by, rejected.reviewed_by), ("VAT Draft", None, None)
		)
		frappe.set_user(APPROVER)
		self.assertRaises(DENIED, frappe.get_doc("Saudi VAT Return", doc.name).submit)

	def test_unresolved_sources_block_review_and_approval(self):
		frappe.set_user("Administrator")
		extra = self._purchase_without_vat()
		doc = self._calculated()
		self.assertGreater(doc.review_count, 0)
		self._step(doc, PREPARER, "Prepare VAT Return")
		self.assertRaises(frappe.ValidationError, self._step, doc, REVIEWER, "Review VAT Return")
		self.assertTrue(extra)

	def test_changed_documents_block_approval(self):
		doc = self._calculated()
		self._step(doc, PREPARER, "Prepare VAT Return")
		self._step(doc, REVIEWER, "Review VAT Return")
		frappe.set_user("Administrator")
		self._invoice("Purchase Invoice", 300, self.vat_in)
		drift = frappe.get_doc("Saudi VAT Return", doc.name).check_drift()
		self.assertFalse(drift["unchanged"])
		self.assertRaises(frappe.ValidationError, self._step, doc, APPROVER, "Approve VAT Return")

	def test_approved_return_cannot_be_changed(self):
		doc = self._approved()
		frappe.set_user(APPROVER)
		doc = frappe.get_doc("Saudi VAT Return", doc.name)
		doc.lines[0].vat = 1
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_user_of_another_company_is_denied(self):
		other = frappe.get_all("Company", filters={"name": ["!=", COMPANY]}, pluck="name", limit=1)
		if not other:  # a fresh site has only the test company
			other = [frappe.db.get_value("Account", make_other_company_tax_account(), "company")]
		email = make_user("vat-other-company@example.com", VAT_PREPARER)
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Company", "for_value": other[0]}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		doc = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": FROM, "to_date": TO}
		)
		self.assertRaises(frappe.PermissionError, doc.insert)

	# ---- filing and amendment ----------------------------------------------------------------------------
	def test_filing_requires_reason_for_differences(self):
		doc = self._approved()
		frappe.set_user(APPROVER)
		filing = frappe.get_doc(
			{
				"doctype": "Saudi VAT Filing",
				"vat_return": doc.name,
				"filed_on": TO,
				"zatca_reference": "TEST-1",
			}
		).insert()
		self.assertEqual(len(filing.fields), 16)
		row = next(r for r in filing.fields if r.box_id == "P07")
		row.filed_vat = 200
		filing.save()
		self.assertEqual(row.difference, -10)
		self.assertRaises(frappe.ValidationError, filing.submit)
		filing.reload()
		next(r for r in filing.fields if r.box_id == "P07").reason = "Rounded on the portal"
		filing.submit()
		second = frappe.get_doc(
			{
				"doctype": "Saudi VAT Filing",
				"vat_return": doc.name,
				"filed_on": TO,
				"zatca_reference": "TEST-2",
			}
		)
		self.assertRaises(frappe.ValidationError, second.insert)

	def test_filing_needs_an_approved_return(self):
		doc = self._calculated()
		frappe.set_user(APPROVER)
		filing = frappe.get_doc(
			{
				"doctype": "Saudi VAT Filing",
				"vat_return": doc.name,
				"filed_on": TO,
				"zatca_reference": "TEST-3",
			}
		)
		self.assertRaises(frappe.ValidationError, filing.insert)

	def test_amendment_limit_for_later_return(self):
		# the parity rule set has no verified correction rules (IR Art. 63), so a later-return correction can be
		# saved as a draft but not submitted; the rules themselves are covered in test_amendment_rules.py
		doc = self._approved()
		frappe.set_user(PREPARER)
		amendment = frappe.get_doc(
			{
				"doctype": "Saudi VAT Amendment",
				"original_return": doc.name,
				"kind": "Correction in a Later Return",
				"reason": "Late supplier invoice",
				"lines": [{"box_id": "P07", "vat_effect": 6000}],
			}
		).insert()
		frappe.set_user(APPROVER)
		self.assertRaises(
			frappe.ValidationError, frappe.get_doc("Saudi VAT Amendment", amendment.name).submit
		)
		frappe.set_user(PREPARER)
		amendment = frappe.get_doc(
			{
				"doctype": "Saudi VAT Amendment",
				"original_return": doc.name,
				"kind": "Self-Amendment",
				"reason": "Late supplier invoice",
				"lines": [{"box_id": "P07", "vat_effect": 6000}],
			}
		).insert()
		self.assertEqual(amendment.total_vat_effect, 6000)

	# ---- data -------------------------------------------------------------------------------------------------
	def _purchase_without_vat(self):
		doc = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"posting_date": DATE,
				"set_posting_time": 1,
				"supplier": SUPPLIER,
				"bill_no": "NO-VAT-2",
				"bill_date": DATE,
				"items": [{"item_code": ITEM, "qty": 1, "rate": 40}],
			}
		).insert(ignore_permissions=True)
		doc.submit()
		return doc.name
