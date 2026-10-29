# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Returns calculated with published rule books: rule sets used, tax dates, missing rules, rule changes after the
calculation, snapshot stability and the rule-set read permission. Synthetic data only."""

import json

import frappe
from frappe.model.workflow import apply_workflow

from sdce_vat.constants import VAT_APPROVER, VAT_PREPARER, VAT_REVIEWER
from sdce_vat.engine.run import compute
from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import SaudiVATRuleSet, load_rule_book
from sdce_vat.tests.rule_fixtures import PARITY_CODE
from sdce_vat.tests.site_base import (
	COMPANY,
	FROM,
	ITEM,
	SUPPLIER,
	TO,
	VatSiteTestCase,
	make_user,
	publish_rule_set,
)

PREPARER = "vat-rules-preparer@example.com"
REVIEWER = "vat-rules-reviewer@example.com"
APPROVER = "vat-rules-approver@example.com"
NO_ROLE = "vat-rules-no-role@example.com"
PARITY_SET = f"{PARITY_CODE}-1"


class TestReturnRules(VatSiteTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pi_no_vat.cancel()  # no unclassified source left in the period: approval can succeed
		cls.make_settings()
		make_user(PREPARER, VAT_PREPARER)
		make_user(REVIEWER, VAT_REVIEWER)
		make_user(APPROVER, VAT_APPROVER)
		make_user(NO_ROLE)

	def setUp(self):
		frappe.db.savepoint("return_rules_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="return_rules_test")

	# ---- helpers --------------------------------------------------------------------------------------
	def _calculated(self):
		frappe.set_user(PREPARER)
		doc = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": FROM, "to_date": TO}
		).insert()
		doc.calculate()
		return frappe.get_doc("Saudi VAT Return", doc.name)

	def _step(self, doc, user, action):
		frappe.set_user(user)
		return apply_workflow(frappe.get_doc("Saudi VAT Return", doc.name), action)

	def _reviewed(self):
		doc = self._calculated()
		self._step(doc, PREPARER, "Prepare VAT Return")
		return self._step(doc, REVIEWER, "Review VAT Return")

	def _use_code(self, code):
		frappe.set_user("Administrator")
		frappe.db.set_value("Saudi VAT Settings", COMPANY, "rule_set_code", code)

	def _correction(self, start="2026-07-01"):
		return publish_rule_set(
			PARITY_CODE,
			2,
			start,
			version_type="Corrective",
			supersedes=PARITY_SET,
			correction_basis="TEST-REF",
		)

	# ---- calculation ----------------------------------------------------------------------------------
	def test_calculation_records_rule_sets_and_tax_dates(self):
		doc = self._calculated()
		self.assertEqual(doc.engine_version, "0.2.0")
		self.assertEqual([(r.rule_set, r.version) for r in doc.rule_sets], [(PARITY_SET, 1)])
		published = frappe.get_doc("Saudi VAT Rule Set", PARITY_SET)
		self.assertEqual(doc.rule_sets[0].content_hash, published.content_hash)
		self.assertEqual(doc.rule_sets[0].line_count, len(doc.sources))
		for source in doc.sources:
			with self.subTest(voucher=source.voucher_no):
				self.assertEqual((source.rule_set, source.tax_date_basis), (PARITY_SET, "posting_date"))
				self.assertEqual(str(source.tax_date), str(source.posting_date))
				self.assertFalse(source.rule_issue)
		purchase = next(s for s in doc.sources if s.voucher_no == self.pi.name)
		self.assertEqual(str(purchase.invoice_date), str(self.pi.bill_date))  # kept apart from the tax date

	def test_without_a_published_rule_set_nothing_is_placed_and_approval_is_blocked(self):
		draft = frappe.get_doc(
			{
				"doctype": "Saudi VAT Rule Set",
				"rule_set_code": "TEST-DRAFT",
				"version": 1,
				"effective_from": "2020-01-01",
				"references": [
					{
						"ref_id": "R",
						"source_type": "Other",
						"title": "Synthetic",
						"url": "https://example.com/r",
					}
				],
				"rules": [
					{
						"rule_key": "standard_rate",
						"value": "15",
						"reference": "R",
						"verification_status": "Verified",
					}
				],
			}
		)
		frappe.set_user(make_user("vat-rules-maintainer@example.com", "VAT Rule Maintainer"))
		draft.insert()  # a draft is never used
		for code, issue in (("TEST-DRAFT", "rule_set_missing"), ("", "rule_set_not_configured")):
			with self.subTest(code=code):
				self._use_code(code)
				doc = self._calculated()
				self.assertEqual(doc.review_count, len(doc.sources))
				self.assertEqual({s.rule_issue for s in doc.sources}, {issue})
				self.assertFalse(any(s.box_id for s in doc.sources))
				self.assertFalse(doc.rule_sets)
				self._step(doc, PREPARER, "Prepare VAT Return")
				self.assertRaises(frappe.ValidationError, self._step, doc, REVIEWER, "Review VAT Return")
				frappe.set_user("Administrator")
				frappe.delete_doc(
					"Saudi VAT Return", doc.name, force=True
				)  # the next case uses the same period

	def test_two_rule_sets_in_one_period(self):
		publish_rule_set("TEST-SPLIT", 1, "2020-01-01", "2026-07-31")
		publish_rule_set("TEST-SPLIT", 2, "2026-08-01")
		august = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": COMPANY,
				"posting_date": "2026-08-20",
				"set_posting_time": 1,
				"supplier": SUPPLIER,
				"currency": "SAR",
				"bill_no": "B-AUG",
				"bill_date": "2026-08-20",
				"items": [{"item_code": ITEM, "qty": 1, "rate": 300}],
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": self.vat_in,
						"rate": 15,
						"description": "VAT",
					}
				],
			}
		).insert(ignore_permissions=True)
		august.submit()
		self._use_code("TEST-SPLIT")
		doc = self._calculated()
		used = {r.rule_set: r for r in doc.rule_sets}
		self.assertEqual(sorted(used), ["TEST-SPLIT-1", "TEST-SPLIT-2"])
		self.assertEqual(used["TEST-SPLIT-2"].line_count, 1)
		self.assertEqual(str(used["TEST-SPLIT-2"].first_tax_date), "2026-08-20")
		self.assertEqual(sum(r.line_count for r in doc.rule_sets), len(doc.sources))
		self.assertEqual(next(s.rule_set for s in doc.sources if s.voucher_no == august.name), "TEST-SPLIT-2")
		self.assertEqual(doc.review_count, 0)
		frappe.set_user("Administrator")
		later = load_rule_book(
			"TEST-SPLIT", "2026-10-01", "2026-12-31"
		)  # only sets that can cover the period
		self.assertEqual(sorted(later.sets), ["TEST-SPLIT-2"])

	# ---- rule changes ---------------------------------------------------------------------------------
	def test_rule_change_after_calculation_blocks_approval(self):
		doc = self._reviewed()
		self._correction()
		frappe.set_user(APPROVER)
		drift = frappe.get_doc("Saudi VAT Return", doc.name).check_drift()
		self.assertFalse(drift["unchanged"])
		self.assertIn([PARITY_SET, doc.rule_sets[0].content_hash], drift["changed_rule_sets"])
		self.assertRaisesRegex(
			frappe.ValidationError, "rule sets changed", self._step, doc, APPROVER, "Approve VAT Return"
		)
		self.assertEqual(frappe.db.get_value("Saudi VAT Return", doc.name, "docstatus"), 0)

	def test_snapshot_keeps_the_rules_and_stays_valid_after_a_correction(self):
		doc = self._step(self._reviewed(), APPROVER, "Approve VAT Return")
		before = (doc.calculation_hash, doc.snapshot_hash, doc.net_vat)
		frappe.set_user("Administrator")
		content = frappe.get_doc("File", {"file_url": doc.snapshot_file}).get_content()
		snapshot = json.loads(content.decode() if isinstance(content, bytes) else content)
		rule_set = frappe.get_doc("Saudi VAT Rule Set", PARITY_SET)
		self.assertEqual(
			[(r["name"], r["content_hash"]) for r in snapshot["rule_sets"]],
			[(PARITY_SET, rule_set.content_hash)],
		)
		self.assertEqual(
			snapshot["rule_sets"][0]["content"], json.loads(json.dumps(SaudiVATRuleSet.content_of(rule_set)))
		)
		self._correction()
		frappe.set_user(APPROVER)
		approved = frappe.get_doc("Saudi VAT Return", doc.name)
		self.assertEqual(approved.verify_snapshot(), {"approved": True, "file_ok": True, "tables_ok": True})
		self.assertEqual((approved.calculation_hash, approved.snapshot_hash, approved.net_vat), before)
		self.assertEqual([r.rule_set for r in approved.rule_sets], [PARITY_SET])

	def test_changed_rule_set_rows_block_approval(self):
		doc = self._reviewed()
		frappe.set_user("Administrator")
		frappe.db.set_value("Saudi VAT Return Rule Set", doc.rule_sets[0].name, "line_count", 99)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"changed after calculation",
			self._step,
			doc,
			APPROVER,
			"Approve VAT Return",
		)

	def test_tampered_rule_set_stops_the_calculation(self):
		frappe.set_user("Administrator")
		row = frappe.get_doc("Saudi VAT Rule Set", PARITY_SET).rules[0].name
		frappe.db.set_value("Saudi VAT Rule", row, "value", "5")  # change below the ORM
		self.assertRaises(frappe.ValidationError, self._calculated)

	# ---- permissions and old returns --------------------------------------------------------------------
	def test_calculation_needs_rule_set_read_permission(self):
		frappe.set_user(NO_ROLE)
		self.assertFalse(frappe.has_permission("Saudi VAT Rule Set", "read"))
		self.assertRaisesRegex(frappe.PermissionError, "rule sets", compute, self.config, FROM, TO)

	def test_return_of_an_older_engine_must_be_recalculated(self):
		doc = self._reviewed()
		frappe.db.set_value("Saudi VAT Return", doc.name, "engine_version", "0.1.0", update_modified=False)
		self.assertRaisesRegex(
			frappe.ValidationError, "recalculate it", self._step, doc, APPROVER, "Approve VAT Return"
		)

	def test_returns_of_engine_0_1_0_keep_their_payload(self):
		doc = self._calculated()
		self.assertIn("rule_sets", doc._payload())
		doc.engine_version = "0.1.0"
		self.assertNotIn("rule_sets", doc._payload())
		self.assertNotIn("source_rules", doc._payload())
