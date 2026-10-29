# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Baseline rule files: content checks, import as Draft with every rule Pending, idempotence, permissions,
atomicity and no effect on accounting data. Synthetic users only."""

import json
import re
import unittest
from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from sdce_vat.constants import VAT_PREPARER, VAT_REVIEWER, VAT_RULE_MAINTAINER
from sdce_vat.engine import boxes
from sdce_vat.rules import baseline
from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import (
	UNUSED_BOX_KEYS,
	is_valid_rule_key,
	load_rule_book,
)
from sdce_vat.tests.site_base import make_user

NAME = "ksa_vat_2026_1"
MAINTAINER = "vat-baseline-maintainer@example.com"
REVIEWER = "vat-baseline-reviewer@example.com"
PREPARER = "vat-baseline-preparer@example.com"
LEDGER_DOCTYPES = (
	"GL Entry",
	"Journal Entry",
	"Sales Invoice",
	"Purchase Invoice",
	"Payment Entry",
	"Account",
	"Saudi VAT Return",
)
# what must never appear in a public baseline file: e-mail addresses, VAT numbers, IP addresses, local paths
LEAK_PATTERNS = (
	r"[\w.+-]+@[\w-]+\.[\w.]+",
	r"\b3\d{13}3\b",
	r"\b\d{1,3}(\.\d{1,3}){3}\b",
	r"[A-Za-z]:\\",
	r"/home/",
)


class TestBaselineFile(unittest.TestCase):
	def setUp(self):
		self.data = json.loads((baseline.RULES_DIR / f"{NAME}.json").read_text(encoding="utf-8"))

	def test_the_file_is_listed(self):
		self.assertIn(NAME, baseline.baseline_names())

	def test_rules_are_known_pending_and_referenced(self):
		ref_ids = {r["ref_id"] for r in self.data["references"]}
		self.assertEqual(len(ref_ids), len(self.data["references"]))
		keys = [r["rule_key"] for r in self.data["rules"]]
		self.assertEqual(len(keys), len(set(keys)))
		for row in self.data["rules"]:
			self.assertTrue(is_valid_rule_key(row["rule_key"]), row["rule_key"])
			self.assertNotIn(row["rule_key"], UNUSED_BOX_KEYS)
			self.assertEqual(row["verification_status"], "Pending", row["rule_key"])
			self.assertIn(row["reference"], ref_ids, row["rule_key"])
			for field in ("value", "description_en", "description_ar", "notes"):
				self.assertTrue(row.get(field), f"{row['rule_key']} {field}")

	def test_references_are_official_and_fit_their_fields(self):
		for row in self.data["references"]:
			self.assertTrue(row["url"].startswith("https://zatca.gov.sa/"), row["ref_id"])
			for field in ("url", "title", "section"):
				self.assertLessEqual(len(row.get(field) or ""), 140, f"{row['ref_id']} {field}")
			self.assertTrue(row["section"] and row["accessed_on"], row["ref_id"])

	def test_every_return_field_has_both_labels(self):
		labels = {row["field_id"]: row for row in self.data["field_labels"]}
		self.assertEqual(set(labels), set(boxes.BOX_BY_ID))
		for field_id, row in labels.items():
			self.assertTrue(row["label_en"] and row["label_ar"], field_id)

	def test_rule_set_header_has_both_languages(self):
		for field in ("description_en", "description_ar", "notice_en", "notice_ar"):
			self.assertTrue(self.data.get(field), field)

	def test_no_private_data(self):
		text = json.dumps(self.data, ensure_ascii=False)
		for pattern in LEAK_PATTERNS:
			self.assertIsNone(re.search(pattern, text), pattern)


class TestBaselineImport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(MAINTAINER, VAT_RULE_MAINTAINER)
		make_user(REVIEWER, VAT_REVIEWER)
		make_user(PREPARER, VAT_PREPARER)
		# the shipped file under a code of its own, so a set already imported on the site does not interfere
		cls.data = {**baseline.read_baseline(NAME), "rule_set_code": "TEST-BASELINE"}

	def setUp(self):
		frappe.db.savepoint("baseline_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="baseline_test")

	def _import(self, data=None):
		frappe.set_user(MAINTAINER)
		with patch.object(baseline, "read_baseline", return_value=data or self.data):
			return baseline.import_baseline(NAME)

	def test_import_creates_a_draft_with_every_rule_pending(self):
		doc = frappe.get_doc("Saudi VAT Rule Set", self._import())
		self.assertEqual((doc.docstatus, doc.workflow_state), (0, "Rule Draft"))
		self.assertEqual(doc.verification_status, "Pending")
		self.assertFalse(doc.verified_by or doc.content_hash or doc.published_by)
		self.assertEqual(len(doc.rules), len(self.data["rules"]))
		self.assertEqual({row.verification_status for row in doc.rules}, {"Pending"})
		self.assertFalse(any(row.verified_by for row in doc.rules))
		self.assertEqual(len(doc.field_labels), len(boxes.BOXES))

	def test_rules_marked_verified_in_a_file_still_import_as_pending(self):
		data = json.loads(json.dumps(self.data))
		for row in data["rules"]:
			row["verification_status"] = "Verified"
		name = self._import(data)
		self.assertEqual(
			set(frappe.get_all("Saudi VAT Rule", {"parent": name}, pluck="verification_status")), {"Pending"}
		)

	def test_second_import_changes_nothing(self):
		name = self._import()
		frappe.db.set_value("Saudi VAT Rule Set", name, "description_en", "Edited by the maintainer")
		self.assertEqual(self._import(), name)
		self.assertEqual(
			frappe.db.count("Saudi VAT Rule Set", {"rule_set_code": self.data["rule_set_code"]}), 1
		)
		self.assertEqual(
			frappe.db.get_value("Saudi VAT Rule Set", name, "description_en"), "Edited by the maintainer"
		)

	def test_import_never_replaces_a_submitted_set(self):
		name = self._import()
		frappe.db.set_value(
			"Saudi VAT Rule Set",
			name,
			{"docstatus": 1, "workflow_state": "Rule Published"},
			update_modified=False,
		)
		frappe.db.set_value("Saudi VAT Rule", {"parent": name}, "verification_status", "Verified")
		self.assertEqual(self._import(), name)
		self.assertEqual(frappe.db.get_value("Saudi VAT Rule Set", name, "workflow_state"), "Rule Published")
		self.assertEqual(
			set(frappe.get_all("Saudi VAT Rule", {"parent": name}, pluck="verification_status")), {"Verified"}
		)

	def test_pending_rules_cannot_be_verified(self):
		name = self._import()
		frappe.set_user(REVIEWER)
		self.assertRaises(
			frappe.ValidationError,
			apply_workflow,
			frappe.get_doc("Saudi VAT Rule Set", name),
			"Verify Rule Set",
		)

	def test_a_draft_baseline_is_never_used_by_the_engine(self):
		self._import()
		book = load_rule_book(self.data["rule_set_code"], "2025-01-01", "2025-03-31")
		self.assertEqual(book.for_date("2025-02-01")[0], None)

	def test_only_a_maintainer_imports(self):
		for user in (PREPARER, REVIEWER):
			frappe.set_user(user)
			self.assertRaises(frappe.PermissionError, baseline.import_baseline, NAME)
			self.assertRaises(frappe.PermissionError, baseline.list_baselines)

	def test_only_shipped_files_are_read(self):
		frappe.set_user(MAINTAINER)
		for name in ("../hooks", "..\\hooks", "unknown_file", "KSA_VAT_2026_1", ""):
			self.assertRaises(frappe.ValidationError, baseline.import_baseline, name)
		self.assertEqual([row["name"] for row in baseline.list_baselines()], baseline.baseline_names())

	def test_a_broken_file_leaves_nothing_behind(self):
		data = json.loads(json.dumps(self.data))
		data["rules"].append(
			{"rule_key": "not_a_rule", "value": "1", "reference": data["references"][0]["ref_id"]}
		)
		self.assertRaises(frappe.ValidationError, self._import, data)
		self.assertFalse(frappe.db.exists("Saudi VAT Rule Set", {"rule_set_code": data["rule_set_code"]}))

	def test_import_touches_no_accounting_data(self):
		before = {doctype: frappe.db.count(doctype) for doctype in LEDGER_DOCTYPES}
		self._import()
		frappe.set_user("Administrator")
		self.assertEqual({doctype: frappe.db.count(doctype) for doctype in LEDGER_DOCTYPES}, before)
