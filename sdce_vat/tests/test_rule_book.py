# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pure rule-book tests: parity with engine 0.1.0, tax dates, several rule sets in one period, missing and
unverified rules, corrections and transitions. No database."""

import json
from pathlib import Path

from frappe.tests import UnitTestCase

from sdce_vat.engine.core import calculate
from sdce_vat.engine.model import Side
from sdce_vat.engine.rules import CORRECTIVE, RuleBook
from sdce_vat.tests import rule_fixtures as f

FROM, TO = "2026-07-01", "2026-09-30"


def run(lines, book, gl_rows=None):
	if gl_rows is None:
		gl_rows = [
			f.GLRow(
				x.voucher_type, x.voucher_no, x.vat_account, x.vat * (-1 if x.vat_account == f.OUT else 1)
			)
			for x in lines
			if x.vat_account
		]
	return calculate(f.parity_config(), FROM, TO, lines, gl_rows, rule_book=book)


def sale(no="SI-1", posting_date="2026-07-10", base="100", vat="15", **kw):
	return f._line(no, "Sales Invoice", Side.SALES, f.OUT, base, vat, posting_date=posting_date, **kw)


def purchase(no="PI-1", posting_date="2026-07-10", **kw):
	return f._line(
		no, "Purchase Invoice", Side.PURCHASES, f.INP, "100", "15", posting_date=posting_date, **kw
	)


class TestParity(UnitTestCase):
	def test_equivalent_rule_set_gives_the_results_of_engine_0_1_0(self):
		# parity_engine_0_1_0.json was produced by engine 0.1.0 (main before rule books) from the same scenario
		expected = json.loads(
			(Path(__file__).parent / "parity_engine_0_1_0.json").read_text(encoding="utf-8")
		)
		result = calculate(
			f.parity_config(), FROM, TO, f.parity_lines(), f.parity_gl(), rule_book=f.parity_book()
		)
		self.assertEqual(json.loads(json.dumps(f.parity_digest(result), sort_keys=True)), expected)
		self.assertEqual(list(result.rule_sets), ["TEST-PARITY-1"])
		self.assertEqual(result.engine_version, "0.2.0")

	def test_dates_stay_separate(self):
		line = purchase(invoice_date="2026-06-28")
		run([line], f.parity_book())
		self.assertEqual(
			(line.posting_date, line.invoice_date, line.tax_date), ("2026-07-10", "2026-06-28", "2026-07-10")
		)
		self.assertEqual(
			(line.tax_date_basis, line.rule_set, line.rule_issue), ("posting_date", "TEST-PARITY-1", "")
		)


class TestRuleResolution(UnitTestCase):
	def assertIssue(self, line, issue):
		self.assertEqual(line.rule_issue, issue)
		self.assertTrue(line.needs_review)
		self.assertIsNone(line.box)
		self.assertIsNone(line.rule_set)

	def test_two_rule_sets_in_one_period(self):
		book = RuleBook(
			f.PARITY_CODE,
			[f.rule_set("V1", end="2026-08-15"), f.rule_set("V2", start="2026-08-16", version=2)],
		)
		early, late = sale("SI-1", "2026-07-20"), sale("SI-2", "2026-09-01", base="200", vat="30")
		result = run([early, late], book)
		self.assertEqual((early.rule_set, late.rule_set), ("V1", "V2"))
		self.assertEqual(sorted(result.rule_sets), ["V1", "V2"])
		self.assertEqual(str(result.boxes["S01"].vat), "45.00")

	def test_open_end_stops_at_the_next_version(self):
		book = RuleBook(f.PARITY_CODE, [f.rule_set("V1"), f.rule_set("V2", start="2026-08-16", version=2)])
		lines = [sale("SI-1", "2026-08-15"), sale("SI-2", "2026-08-16")]
		run(lines, book)
		self.assertEqual([x.rule_set for x in lines], ["V1", "V2"])

	def test_no_code_or_no_published_set(self):
		for book, issue in (
			(RuleBook(None, []), "rule_set_not_configured"),
			(RuleBook(f.PARITY_CODE, []), "rule_set_missing"),
			(RuleBook(f.PARITY_CODE, [f.rule_set(start="2027-01-01")]), "rule_set_missing"),
		):
			with self.subTest(issue=issue):
				line = sale()
				result = run([line], book)
				self.assertIssue(line, issue)
				self.assertEqual(str(result.boxes["S01"].vat), "0.00")
				self.assertEqual(result.rule_sets, {})

	def test_unverified_missing_or_invalid_rules_are_not_used(self):
		cases = {
			"rule_unverified:treatment_box:standard_rated_sale": f.rule_set(status="Pending"),
			"rule_missing:treatment_box:standard_rated_sale": f.rule_set(
				rules={k: v for k, v in f.PARITY_RULES.items() if k != "treatment_box:standard_rated_sale"}
			),
			"rule_invalid:treatment_box:standard_rated_sale": f.rule_set(
				rules={**f.PARITY_RULES, "treatment_box:standard_rated_sale": "P07"}
			),
			"rule_missing:standard_rate": f.rule_set(
				rules={k: v for k, v in f.PARITY_RULES.items() if k != "standard_rate"}
			),
			"rule_missing:tax_date_basis:sales_invoice": f.rule_set(
				rules={k: v for k, v in f.PARITY_RULES.items() if k != "tax_date_basis:sales_invoice"}
			),
		}
		for issue, rule_set in cases.items():
			with self.subTest(issue=issue):
				line = sale()
				run([line], RuleBook(f.PARITY_CODE, [rule_set]))
				if issue == "rule_unverified:treatment_box:standard_rated_sale":
					issue = "rule_unverified:tax_date_basis:sales_invoice"  # the first rule a line needs
				self.assertIssue(line, issue)

	def test_a_field_of_the_other_side_is_refused(self):
		rules = {**f.PARITY_RULES, "treatment_box:out_of_scope": "S05"}
		line = f._line("PI-9", "Purchase Invoice", Side.PURCHASES, None, "70", "0", tax_category="Outside")
		run([line], RuleBook(f.PARITY_CODE, [f.rule_set(rules=rules)]))
		self.assertIssue(line, "rule_invalid:treatment_box:out_of_scope")

	def test_rate_that_differs_from_the_rule_is_flagged(self):
		line = sale()
		run([line], RuleBook(f.PARITY_CODE, [f.rule_set(rules={**f.PARITY_RULES, "standard_rate": "5"})]))
		self.assertIn("rate_differs_from_rule", line.warnings)
		self.assertEqual(line.box, "S01")

	def test_invoice_date_as_tax_date(self):
		rules = {**f.PARITY_RULES, "tax_date_basis:purchase_invoice": "invoice_date"}
		book = RuleBook(f.PARITY_CODE, [f.rule_set(rules=rules)])
		inside = purchase("PI-1", invoice_date="2026-07-05")
		before = purchase("PI-2", invoice_date="2026-06-30")
		missing = purchase("PI-3")
		run([inside, before, missing], book)
		self.assertEqual((inside.tax_date, inside.box), ("2026-07-05", "P07"))
		self.assertIssue(before, "tax_date_outside_period")
		self.assertEqual(before.tax_date, "2026-06-30")  # kept for the reviewer, never moved silently
		self.assertIssue(missing, "tax_date_undetermined")

	def test_transition_between_rule_sets_needs_review(self):
		early = {**f.PARITY_RULES, "tax_date_basis:purchase_invoice": "invoice_date"}
		book = RuleBook(
			f.PARITY_CODE,
			[
				f.rule_set("V1", end="2026-08-15", rules=early),
				f.rule_set("V2", start="2026-08-16", version=2),
			],
		)
		line = purchase(posting_date="2026-08-10", invoice_date="2026-08-20")
		run([line], book)
		self.assertIssue(line, "rule_transition_review")

	def test_correction_chain_applies_from_its_start(self):
		book = RuleBook(
			f.PARITY_CODE,
			[
				f.rule_set("V1"),
				f.rule_set("V2", start="2026-08-01", version=2, version_type=CORRECTIVE, supersedes="V1"),
				f.rule_set("V3", start="2026-09-01", version=3, version_type=CORRECTIVE, supersedes="V2"),
			],
		)
		lines = [sale("SI-1", "2026-07-31"), sale("SI-2", "2026-08-01"), sale("SI-3", "2026-09-15")]
		run(lines, book)
		self.assertEqual([x.rule_set for x in lines], ["V1", "V2", "V3"])

	def test_conflicting_sets_are_not_guessed(self):
		book = RuleBook(f.PARITY_CODE, [f.rule_set("V1"), f.rule_set("V2", version=2)])
		line = sale()
		run([line], book)
		self.assertIssue(line, "rule_set_conflict")

	def test_unmatched_ledger_vat_keeps_its_own_review(self):
		line = sale()
		gl_rows = [
			f.GLRow("Sales Invoice", "SI-1", f.OUT, -line.vat),
			f.GLRow("Journal Entry", "JE-9", f.OUT, f.D("-5")),
		]
		result = run([line], f.parity_book(), gl_rows)
		extra = next(x for x in result.lines if x.voucher_no == "JE-9")
		self.assertEqual((extra.reason, extra.rule_set, extra.rule_issue), ("unmatched_gl", None, ""))
