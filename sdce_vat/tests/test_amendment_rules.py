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

	def _submitted(self, amendment):
		amendment.insert()
		frappe.set_user(APPROVER)
		doc = frappe.get_doc("Saudi VAT Amendment", amendment.name)
		doc.submit()
		return doc

	def _refused(self, amendment, text):
		with self.assertRaises(frappe.ValidationError) as caught:
			self._submitted(amendment)
		message = str(caught.exception)
		self.assertIn(text, message)
		self.assertIn("self-amendment is required or suitable", message)
		self.assertNotIn("rule_", message)  # readable reason; the diagnostic code goes to the log

	def _verified(self, code, limit="15000", basis="original_period_end", measure="net_total"):
		rules = {
			"correction_limit": limit,
			"correction_limit_basis": basis,
			"correction_limit_measure": measure,
		}
		return self._approved(code, **{k: v for k, v in rules.items() if v})

	# ---- tests ------------------------------------------------------------------------------------------
	def test_draft_is_saved_but_not_submitted_without_rules(self):
		original = self._approved()  # the parity set has no correction rules
		amendment = self._amendment(original, 10)
		amendment.insert()
		self.assertEqual(amendment.docstatus, 0)
		self._refused(self._amendment(original, 10), "date that decides the correction limit")

	def test_limit_without_verified_date_basis_is_not_submitted(self):
		original = self._verified("TEST-LIMIT-NB", basis=None)
		self._refused(self._amendment(original, 10), "date that decides the correction limit")

	def test_limit_without_verified_measure_is_not_submitted(self):
		original = self._verified("TEST-LIMIT-NM", measure=None)
		self._refused(self._amendment(original, 10), "How corrections are measured")

	def _offsetting(self, original):
		amendment = self._amendment(original, 10000)
		amendment.append("lines", {"box_id": "S01", "vat_effect": -9000})
		return amendment

	def test_net_total_lets_offsetting_corrections_through(self):
		original = self._verified("TEST-LIMIT-NET", limit="9500", measure="net_total")
		self.assertEqual(self._submitted(self._offsetting(original)).docstatus, 1)

	def test_per_line_does_not_let_the_net_hide_a_large_line(self):
		original = self._verified("TEST-LIMIT-LINE", limit="9500", measure="per_line")
		self._refused(self._offsetting(original), "above the correction limit 9500")

	def test_absolute_total_adds_both_directions(self):
		original = self._verified("TEST-LIMIT-ABS", limit="15000", measure="absolute_total")
		self._refused(self._offsetting(original), "The VAT effect 19000")

	def test_verified_limit_is_followed_at_its_edge(self):
		original = self._verified("TEST-LIMIT")
		self.assertEqual(self._submitted(self._amendment(original, -15000)).docstatus, 1)
		self._refused(self._amendment(original, 15000.01), "above the correction limit 15000")

	def test_correcting_return_basis_needs_the_later_return(self):
		original = self._verified("TEST-LIMIT-CR", basis="correcting_return_end")
		self._refused(self._amendment(original, 10), "Choose the later return first")

	def test_self_amendment_is_not_affected(self):
		original = self._approved()
		self.assertEqual(
			self._submitted(self._amendment(original, 60000, kind="Self-Amendment")).docstatus, 1
		)

	def test_rule_values_are_checked_when_verified(self):
		frappe.set_user("Administrator")
		for number, (key, value) in enumerate(
			(
				("correction_limit", "abc"),
				("correction_limit", "0"),
				("correction_limit", "-1"),
				("correction_limit_basis", "discovery_date"),
				("correction_limit_measure", "average"),
			)
		):
			self.assertRaises(
				frappe.ValidationError,
				publish_rule_set,
				f"TEST-LIMIT-BAD-{number}",
				1,
				"2020-01-01",
				rules={**PARITY_RULES, key: value},
			)

	def test_no_limit_constant_in_the_code(self):
		source = Path(saudi_vat_amendment.__file__).read_text(encoding="utf-8")
		self.assertNotIn("5000", source)
		self.assertNotIn("5,000", source)
		self.assertNotIn("CORRECTION_LIMIT =", source)
