# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Versioned tax rule sets: three-user separation of duties, immutability, overlap and corrective versions."""

import unittest

import frappe
import frappe.client
from frappe.model.workflow import apply_workflow

from sdce_vat.constants import VAT_APPROVER, VAT_PREPARER, VAT_REVIEWER, VAT_RULE_MAINTAINER
from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import (
	SaudiVATRuleSet,
	is_valid_rule_key,
)
from sdce_vat.tests.site_base import COMPANY, FROM, TO, VatSiteTestCase, make_user

MAINTAINER = "vat-rule-maintainer@example.com"
MAINTAINER_2 = "vat-rule-maintainer-2@example.com"
REVIEWER = "vat-rule-reviewer@example.com"
APPROVER = "vat-rule-approver@example.com"
ALL_ROLES = "vat-rule-all-roles@example.com"
MAINTAINER_APPROVER = "vat-rule-maintainer-approver@example.com"
REVIEWER_APPROVER = "vat-rule-reviewer-approver@example.com"
RETURN_PREPARER = "vat-rule-return-preparer@example.com"
NO_ROLE = "vat-rule-no-role@example.com"
DENIED = (frappe.ValidationError, frappe.PermissionError)
CODE = "TEST-KSA-VAT"
# Synthetic reference: the URL and section are placeholders, not a real legal source.
REFERENCE = {
	"ref_id": "REF-1",
	"source_type": "Implementing Regulation",
	"title": "Synthetic regulation for tests",
	"url": "https://example.com/synthetic-regulation",
	"section": "Art. 1",
	"publication_date": "2026-01-01",
	"effective_date": "2026-01-01",
	"accessed_on": "2026-10-28",
}


class TestRuleKeys(unittest.TestCase):
	def test_closed_key_list(self):
		for key in (
			"standard_rate",
			"treatment_box:zero_rated_sale",
			"recoverability:fuel",
			"tax_date_basis:sales",
		):
			with self.subTest(key=key):
				self.assertTrue(is_valid_rule_key(key))
		for key in (
			"",
			"rate",
			"standard_rate ",
			"treatment_box:",
			"treatment_box:Zero Rated",
			"treatment_box:zero_rated",
			"other:x",
			"x:y:z",
		):
			with self.subTest(key=key):
				self.assertFalse(is_valid_rule_key(key))


class TestRuleSet(VatSiteTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.pi_no_vat.cancel()  # no unclassified source left in the period: the return can be approved
		cls.make_settings()
		make_user(MAINTAINER, VAT_RULE_MAINTAINER)
		make_user(MAINTAINER_2, VAT_RULE_MAINTAINER)
		make_user(REVIEWER, VAT_REVIEWER)
		make_user(APPROVER, VAT_APPROVER)
		make_user(ALL_ROLES, VAT_RULE_MAINTAINER, VAT_REVIEWER, VAT_APPROVER)
		make_user(MAINTAINER_APPROVER, VAT_RULE_MAINTAINER, VAT_APPROVER)
		make_user(REVIEWER_APPROVER, VAT_REVIEWER, VAT_APPROVER)
		make_user(RETURN_PREPARER, VAT_PREPARER)
		make_user(NO_ROLE)

	def setUp(self):
		frappe.db.savepoint("rule_set_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="rule_set_test")

	# ---- helpers --------------------------------------------------------------------------------------
	def _draft(self, user=MAINTAINER, version=1, start="2027-01-01", end=None, status="Verified", **values):
		frappe.set_user(user)
		doc = frappe.get_doc(
			{
				"doctype": "Saudi VAT Rule Set",
				"rule_set_code": CODE,
				"version": version,
				"effective_from": start,
				"effective_to": end,
				"description_en": "Synthetic rule set",
				"description_ar": "مجموعة قواعد تجريبية",
				"references": [dict(REFERENCE)],
				"rules": [
					{
						"rule_key": "standard_rate",
						"value": "15",
						"reference": "REF-1",
						"verification_status": status,
						"description_en": "Standard rate",
						"description_ar": "النسبة الأساسية",
					}
				],
				"field_labels": [
					{
						"field_id": "S01",
						"label_en": "Standard rated sales",
						"label_ar": "المبيعات الخاضعة للنسبة الأساسية",
						"reference": "REF-1",
					}
				],
				**values,
			}
		)
		return doc.insert()

	def _step(self, doc, user, action):
		frappe.set_user(user)
		doc = frappe.get_doc("Saudi VAT Rule Set", doc.name)
		return apply_workflow(doc, action)

	def _edited(self, doc, user):
		frappe.set_user(user)
		doc = frappe.get_doc("Saudi VAT Rule Set", doc.name)
		doc.rules[0].notes = f"checked by {user}"
		return doc.save()

	def _verified(self, verifier=REVIEWER, **values):
		return self._step(self._draft(**values), verifier, "Verify Rule Set")

	def _published(self, publisher=APPROVER, **values):
		return self._step(self._verified(**values), publisher, "Publish Rule Set")

	def _approved_return(self):
		frappe.set_user(RETURN_PREPARER)
		doc = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": FROM, "to_date": TO}
		).insert()
		doc.calculate()
		for user, action in (
			(RETURN_PREPARER, "Prepare VAT Return"),
			(REVIEWER, "Review VAT Return"),
			(APPROVER, "Approve VAT Return"),
		):
			frappe.set_user(user)
			doc = apply_workflow(frappe.get_doc("Saudi VAT Return", doc.name), action)
		frappe.set_user("Administrator")
		return doc

	# ---- separation of duties ---------------------------------------------------------------------------
	def test_three_users_prepare_verify_publish(self):
		doc = self._published()
		self.assertEqual((doc.docstatus, doc.workflow_state), (1, "Rule Published"))
		self.assertEqual(
			(doc.prepared_by, doc.verified_by, doc.published_by), (MAINTAINER, REVIEWER, APPROVER)
		)
		self.assertEqual(doc.verification_status, "Verified")
		self.assertEqual(doc.rules[0].verified_by, REVIEWER)
		self.assertEqual(doc.content_hash, SaudiVATRuleSet.content_hash_of(doc))
		self.assertTrue(doc.content_is_intact())
		self.assertEqual(doc.name, f"{CODE}-1")

	def test_second_maintainer_can_verify(self):
		doc = self._verified(verifier=MAINTAINER_2)
		self.assertEqual(doc.verified_by, MAINTAINER_2)

	def test_preparer_cannot_verify(self):
		doc = self._draft()
		self.assertRaises(DENIED, self._step, doc, MAINTAINER, "Verify Rule Set")

	def test_every_editor_is_excluded_from_verification(self):
		doc = self._edited(self._draft(), MAINTAINER_2)
		self.assertEqual(doc.contributors.split("\n"), [MAINTAINER, MAINTAINER_2])
		self.assertRaises(frappe.PermissionError, self._step, doc, MAINTAINER_2, "Verify Rule Set")
		self.assertEqual(self._step(doc, REVIEWER, "Verify Rule Set").verified_by, REVIEWER)

	def test_preparer_or_verifier_cannot_publish(self):
		doc = self._verified(verifier=REVIEWER_APPROVER)
		self.assertRaises(frappe.PermissionError, self._step, doc, REVIEWER_APPROVER, "Publish Rule Set")
		# the editor is not the owner, so the app check (not Frappe's self-approval check) refuses it
		doc = self._edited(self._draft(version=2, start="2028-01-01"), MAINTAINER_APPROVER)
		doc = self._step(doc, REVIEWER, "Verify Rule Set")
		self.assertRaises(frappe.PermissionError, self._step, doc, MAINTAINER_APPROVER, "Publish Rule Set")

	def test_one_user_with_all_roles_cannot_complete_the_cycle(self):
		self.assertRaises(DENIED, self._step, self._draft(user=ALL_ROLES), ALL_ROLES, "Verify Rule Set")
		doc = self._edited(self._draft(version=2, start="2028-01-01"), ALL_ROLES)
		self.assertRaises(frappe.PermissionError, self._step, doc, ALL_ROLES, "Verify Rule Set")
		doc = self._step(doc, REVIEWER, "Verify Rule Set")
		self.assertRaises(frappe.PermissionError, self._step, doc, ALL_ROLES, "Publish Rule Set")

	def test_direct_submit_or_state_change_is_refused(self):
		doc = self._draft()
		frappe.set_user(APPROVER)
		self.assertRaises(DENIED, frappe.get_doc("Saudi VAT Rule Set", doc.name).submit)
		doc = self._step(doc, REVIEWER, "Verify Rule Set")
		frappe.set_user(APPROVER)
		self.assertRaises(DENIED, frappe.get_doc("Saudi VAT Rule Set", doc.name).submit)
		verified = frappe.get_doc("Saudi VAT Rule Set", doc.name)
		verified.workflow_state = "Rule Published"
		self.assertRaises(DENIED, verified.save)
		self.assertEqual(frappe.db.get_value("Saudi VAT Rule Set", doc.name, "docstatus"), 0)

	# ---- verification ---------------------------------------------------------------------------------------
	def test_pending_rule_blocks_verification(self):
		doc = self._draft(status="Pending")
		self.assertRaises(frappe.ValidationError, self._step, doc, REVIEWER, "Verify Rule Set")

	def test_incomplete_reference_blocks_verification(self):
		reference = {**REFERENCE, "section": None}
		doc = self._draft(references=[reference])
		self.assertRaises(frappe.ValidationError, self._step, doc, REVIEWER, "Verify Rule Set")

	def test_verified_content_is_frozen_until_returned_to_draft(self):
		doc = self._verified()
		frappe.set_user(MAINTAINER)
		doc = frappe.get_doc("Saudi VAT Rule Set", doc.name)
		doc.rules[0].value = "5"
		self.assertRaises(frappe.ValidationError, doc.save)
		doc = self._step(doc, MAINTAINER, "Return Rule Set to Draft")
		self.assertFalse(doc.verified_by or doc.content_hash or doc.rules[0].verified_by)
		doc.rules[0].value = "5"
		doc.save()
		self.assertEqual(doc.verification_status, "Pending")

	def test_system_fields_cannot_be_set(self):
		doc = self._draft(
			content_hash="x" * 64, verified_by=REVIEWER, published_by=APPROVER, contributors=REVIEWER
		)
		self.assertFalse(doc.content_hash or doc.verified_by or doc.published_by)
		self.assertEqual(doc.contributors, MAINTAINER)
		for field, value in (("verified_by", REVIEWER), ("content_hash", "y" * 64), ("contributors", "")):
			with self.subTest(field=field):
				self.assertRaises(
					DENIED, frappe.client.set_value, "Saudi VAT Rule Set", doc.name, field, value
				)
		doc = frappe.get_doc("Saudi VAT Rule Set", doc.name)
		doc.rules[0].verified_by = REVIEWER
		self.assertRaises(frappe.ValidationError, doc.save)

	# ---- content checks -------------------------------------------------------------------------------------
	def test_invalid_content_is_refused(self):
		rule = {
			"rule_key": "standard_rate",
			"value": "15",
			"reference": "REF-1",
			"verification_status": "Verified",
		}
		cases = {
			"unknown key": {"rules": [{**rule, "rule_key": "free_text_rule"}]},
			"duplicate key": {"rules": [rule, dict(rule)]},
			"missing reference": {"rules": [{**rule, "reference": "REF-9"}]},
			"rate not a number": {"rules": [{**rule, "value": "abc"}]},
			"rate zero": {"rules": [{**rule, "value": "0"}]},
			"rate NaN": {"rules": [{**rule, "value": "NaN"}]},
			"months not whole": {"rules": [{**rule, "rule_key": "unpaid_adjust_months", "value": "1.5"}]},
			"plain http": {"references": [{**REFERENCE, "url": "http://example.com/x"}]},
			"script url": {"references": [{**REFERENCE, "url": "javascript:alert(1)"}]},
			"unknown field": {"field_labels": [{"field_id": "X99", "label_en": "x"}]},
			"end before start": {"effective_to": "2026-12-31"},
			"version zero": {"version": 0},
			"lower case code": {"rule_set_code": "test-ksa-vat"},
			"normal with basis": {"correction_basis": "REF-1"},
		}
		for case, values in cases.items():
			with self.subTest(case=case):
				version = values.pop("version", 7)
				self.assertRaises(frappe.ValidationError, self._draft, version=version, **values)

	# ---- published sets ---------------------------------------------------------------------------------------
	def test_published_set_is_immutable(self):
		doc = self._published()
		frappe.set_user(APPROVER)
		published = frappe.get_doc("Saudi VAT Rule Set", doc.name)
		published.rules[0].value = "5"
		self.assertRaises(DENIED, published.save)
		self.assertRaises(
			DENIED, frappe.client.set_value, "Saudi VAT Rule Set", doc.name, "description_en", "changed"
		)
		frappe.set_user(MAINTAINER)
		self.assertRaises(
			DENIED, frappe.client.set_value, "Saudi VAT Rule Set", doc.name, "effective_from", "2027-02-01"
		)
		frappe.set_user("Administrator")
		frappe.db.set_value("Saudi VAT Rule", doc.rules[0].name, "value", "5")  # tampering below the ORM
		self.assertFalse(frappe.get_doc("Saudi VAT Rule Set", doc.name).content_is_intact())

	def test_unreferenced_set_can_be_cancelled_through_the_workflow(self):
		doc = self._published()
		frappe.set_user(APPROVER)
		self.assertRaises(frappe.PermissionError, frappe.get_doc("Saudi VAT Rule Set", doc.name).cancel)
		doc = self._step(doc, APPROVER, "Cancel Rule Set")
		self.assertEqual((doc.docstatus, doc.workflow_state), (2, "Rule Cancelled"))

	def test_same_start_or_overlapping_dates_are_refused(self):
		self._published(end="2027-12-31")
		same_start = self._verified(version=2)
		self.assertRaises(frappe.ValidationError, self._step, same_start, APPROVER, "Publish Rule Set")
		overlap = self._verified(version=3, start="2027-06-01")
		self.assertRaises(frappe.ValidationError, self._step, overlap, APPROVER, "Publish Rule Set")
		next_year = self._published(version=4, start="2028-01-01")
		self.assertEqual(next_year.docstatus, 1)

	def test_open_end_stops_at_the_next_version(self):
		self._published()
		self.assertEqual(self._published(version=2, start="2028-01-01").docstatus, 1)

	def test_version_must_grow(self):
		self._published(version=2)
		older = self._verified(version=1, start="2028-01-01")
		self.assertRaises(frappe.ValidationError, self._step, older, APPROVER, "Publish Rule Set")

	# ---- approved periods and corrective versions -------------------------------------------------------------
	def test_approved_period_needs_a_corrective_version(self):
		base = self._published(start="2026-01-01")
		approved = self._approved_return()
		snapshot = (approved.docstatus, approved.snapshot_hash, approved.net_vat)

		normal = self._verified(version=2, start="2026-08-01")
		self.assertRaises(frappe.ValidationError, self._step, normal, APPROVER, "Publish Rule Set")
		self.assertRaises(frappe.ValidationError, self._step, base, APPROVER, "Cancel Rule Set")

		correction = self._published(
			version=3,
			start="2026-01-01",
			version_type="Corrective",
			supersedes=base.name,
			correction_basis="REF-1",
		)
		self.assertEqual((correction.docstatus, correction.supersedes), (1, base.name))
		again = self._verified(
			version=4,
			start="2026-01-01",
			version_type="Corrective",
			supersedes=base.name,
			correction_basis="REF-1",
		)
		self.assertRaises(frappe.ValidationError, self._step, again, APPROVER, "Publish Rule Set")
		self.assertRaises(frappe.ValidationError, self._step, base, APPROVER, "Cancel Rule Set")
		self.assertRaises(frappe.ValidationError, self._step, correction, APPROVER, "Cancel Rule Set")

		approved = frappe.get_doc("Saudi VAT Return", approved.name)
		self.assertEqual((approved.docstatus, approved.snapshot_hash, approved.net_vat), snapshot)

	def test_corrective_stays_inside_the_superseded_set(self):
		base = self._published(end="2027-12-31")
		cases = (
			("starts earlier", 2, "2026-12-01", "2027-12-31"),
			("ends later", 3, "2027-01-01", "2028-01-31"),
		)
		for case, version, start, end in cases:
			with self.subTest(case=case):
				doc = self._verified(
					version=version,
					start=start,
					end=end,
					version_type="Corrective",
					supersedes=base.name,
					correction_basis="REF-1",
				)
				self.assertRaises(frappe.ValidationError, self._step, doc, APPROVER, "Publish Rule Set")

	def test_corrective_without_basis_is_refused(self):
		base = self._published()
		for values in ({"supersedes": base.name}, {"correction_basis": "REF-1"}):
			with self.subTest(values=values):
				self.assertRaises(
					frappe.ValidationError, self._draft, version=2, version_type="Corrective", **values
				)

	def test_corrective_stops_where_the_next_version_starts(self):
		base = self._published()  # open end: applies until the next normal version
		self._published(version=2, start="2028-01-01")
		for version, end in ((3, None), (4, "2028-06-30")):
			with self.subTest(end=end):
				doc = self._verified(
					version=version,
					end=end,
					version_type="Corrective",
					supersedes=base.name,
					correction_basis="REF-1",
				)
				self.assertRaises(frappe.ValidationError, self._step, doc, APPROVER, "Publish Rule Set")
		inside = self._published(
			version=5,
			end="2027-12-31",
			version_type="Corrective",
			supersedes=base.name,
			correction_basis="REF-1",
		)
		self.assertEqual(inside.docstatus, 1)

	def test_correction_basis_must_be_a_complete_reference(self):
		base = self._published()
		basis = {**REFERENCE, "ref_id": "REF-2", "accessed_on": None}
		doc = self._draft(
			version=2,
			version_type="Corrective",
			supersedes=base.name,
			correction_basis="REF-2",
			references=[dict(REFERENCE), basis],
		)
		self.assertRaises(frappe.ValidationError, self._step, doc, REVIEWER, "Verify Rule Set")

	# ---- permissions --------------------------------------------------------------------------------------
	def test_users_without_a_rule_role_are_denied(self):
		doc = self._draft()
		frappe.set_user(NO_ROLE)
		self.assertFalse(frappe.has_permission("Saudi VAT Rule Set", "read"))
		self.assertRaises(frappe.PermissionError, frappe.client.get, "Saudi VAT Rule Set", doc.name)
		self.assertRaises(frappe.PermissionError, self._draft, user=NO_ROLE, version=2)
		frappe.set_user(RETURN_PREPARER)
		self.assertTrue(frappe.has_permission("Saudi VAT Rule Set", "read", doc=doc.name))
		self.assertFalse(frappe.has_permission("Saudi VAT Rule Set", "write", doc=doc.name))
		self.assertRaises(frappe.PermissionError, self._draft, user=RETURN_PREPARER, version=3)

	def test_reviewer_cannot_change_content(self):
		doc = self._draft()
		frappe.set_user(REVIEWER)
		doc = frappe.get_doc("Saudi VAT Rule Set", doc.name)
		doc.rules[0].value = "5"
		self.assertRaises(frappe.PermissionError, doc.save)

	def test_rule_workflow_and_role_are_installed_once(self):
		self.assertEqual(
			frappe.get_all("Workflow", {"document_type": "Saudi VAT Rule Set", "is_active": 1}, pluck="name"),
			["Saudi VAT Rule Set Approval"],
		)
		for state in ("Rule Draft", "Rule Verified", "Rule Published", "Rule Cancelled"):
			with self.subTest(state=state):
				self.assertTrue(frappe.db.exists("Workflow State", state))
		self.assertEqual(frappe.db.count("Role", {"name": VAT_RULE_MAINTAINER}), 1)
