# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Correction limit of a Saudi VAT Amendment from the published rule set (IR Art. 63), never from a constant.
Synthetic data only; the amounts in these tests are test values, not the legal threshold."""

from pathlib import Path

import frappe
from frappe.model.workflow import apply_workflow

from sdce_vat.constants import VAT_APPROVER, VAT_PREPARER, VAT_REVIEWER
from sdce_vat.saudi_vat.doctype.saudi_vat_amendment import saudi_vat_amendment
from sdce_vat.tests.rule_fixtures import PARITY_CODE, PARITY_RULES
from sdce_vat.tests.site_base import COMPANY, FROM, TO, VatSiteTestCase, make_user, publish_rule_set

PREPARER = "vat-amend-preparer@example.com"
REVIEWER = "vat-amend-reviewer@example.com"
APPROVER = "vat-amend-approver@example.com"
LATER = "Correction in a Later Return"


class TestAmendmentRules(VatSiteTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pi_no_vat.cancel()  # no unclassified source left in the period: approval can succeed
		cls.make_settings()
		make_user(PREPARER, VAT_PREPARER)
		make_user(REVIEWER, VAT_REVIEWER)
		make_user(APPROVER, VAT_APPROVER)

	def setUp(self):
		frappe.db.savepoint("amendment_rules_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="amendment_rules_test")

	# ---- helpers --------------------------------------------------------------------------------------
	def _approved(self, code=PARITY_CODE, **rules):
		"""An approved return calculated with the published rule set `code` (published here when new)."""
		frappe.set_user("Administrator")
		if code != PARITY_CODE:
			publish_rule_set(code, 1, "2020-01-01", rules={**PARITY_RULES, **rules})
		frappe.db.set_value("Saudi VAT Settings", COMPANY, "rule_set_code", code)
		frappe.set_user(PREPARER)
		doc = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": FROM, "to_date": TO}
		)
		doc.insert()
		doc.calculate()
		for user, action in (
			(PREPARER, "Prepare VAT Return"),
			(REVIEWER, "Review VAT Return"),
			(APPROVER, "Approve VAT Return"),
		):
			frappe.set_user(user)
			doc = apply_workflow(frappe.get_doc("Saudi VAT Return", doc.name), action)
		return doc

	def _amendment(self, original, effect, kind=LATER):
		frappe.set_user(PREPARER)
		return frappe.get_doc(
			{
				"doctype": "Saudi VAT Amendment",
				"original_return": original.name,
				"kind": kind,
				"reason": "Late supplier invoice",
				"lines": [{"box_id": "P07", "vat_effect": effect}],
			}
		)

	# ---- tests ------------------------------------------------------------------------------------------
	def test_no_limit_in_the_rule_set_refuses_a_later_return_correction(self):
		original = self._approved()  # the parity set has no correction_limit rule
		with self.assertRaisesRegex(frappe.ValidationError, "rule_missing:correction_limit"):
			self._amendment(original, 10).insert()

	def test_unverified_limit_refuses_a_later_return_correction(self):
		original = self._approved("TEST-LIMIT-NA", correction_limit=None)  # Not applicable: no verified value
		with self.assertRaisesRegex(frappe.ValidationError, "rule_unverified:correction_limit"):
			self._amendment(original, 10).insert()

	def test_verified_limit_is_followed(self):
		original = self._approved("TEST-LIMIT", correction_limit="15000")
		self.assertEqual(self._amendment(original, 6000).insert().total_vat_effect, 6000)
		self.assertEqual(self._amendment(original, -15000).insert().total_vat_effect, -15000)
		with self.assertRaisesRegex(frappe.ValidationError, "above 15000"):
			self._amendment(original, 15000.01).insert()

	def test_self_amendment_needs_no_limit(self):
		original = self._approved()
		amendment = self._amendment(original, 60000, kind="Self-Amendment").insert()
		self.assertEqual(amendment.total_vat_effect, 60000)

	def test_limit_must_be_a_positive_amount(self):
		frappe.set_user("Administrator")
		for number, value in enumerate(("abc", "0", "-1", "NaN")):
			self.assertRaises(
				frappe.ValidationError,
				publish_rule_set,
				f"TEST-LIMIT-BAD-{number}",
				1,
				"2020-01-01",
				rules={**PARITY_RULES, "correction_limit": value},
			)

	def test_no_limit_constant_in_the_code(self):
		source = Path(saudi_vat_amendment.__file__).read_text(encoding="utf-8")
		self.assertNotIn("5000", source)
		self.assertNotIn("5,000", source)
		self.assertNotIn("CORRECTION_LIMIT", source)
