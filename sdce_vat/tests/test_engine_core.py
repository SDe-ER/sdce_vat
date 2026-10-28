# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of the pure engine core (no database)."""

from decimal import Decimal

from frappe.tests import UnitTestCase

from sdce_vat.engine import boxes
from sdce_vat.engine.config import NonDeductiblePlacement, VatConfig
from sdce_vat.engine.core import calculate
from sdce_vat.engine.model import Column, GLRow, Side, SourceLine, Treatment
from sdce_vat.engine.money import D, q2, total
from sdce_vat.engine.rows import invoice_lines, journal_lines
from sdce_vat.tests.rule_fixtures import parity_book

OUT, INP, RCM, ZERO_ACC = "VAT Out - T", "VAT In - T", "VAT RCM - T", "VAT 0 - T"
SUPPLIER_VAT = "300000000000003"


def config(**kwargs) -> VatConfig:
	values = dict(
		company="T",
		output_accounts={OUT: Decimal("15"), ZERO_ACC: Decimal("0")},
		input_accounts={INP: Decimal("15")},
		reverse_charge_accounts={RCM: Decimal("15")},
		category_treatments={
			"Zero": Treatment.ZERO_RATED_SALE,
			"Exempt": Treatment.EXEMPT_SALE,
			"Outside": Treatment.OUT_OF_SCOPE,
			"NoClaim": Treatment.INPUT_NOT_DEDUCTIBLE,
			"Export": Treatment.EXPORT,
		},
	)
	values.update(kwargs)
	return VatConfig(**values)


def line(no, side=Side.PURCHASES, account=INP, base="100.00", vat="15.00", vt="Purchase Invoice", **kw):
	return SourceLine(
		voucher_type=vt,
		voucher_no=no,
		side=side,
		posting_date="2026-07-01",
		company="T",
		vat_account=account,
		base=D(base),
		vat=D(vat),
		party_type="Supplier" if side == Side.PURCHASES else "Customer",
		party=kw.pop("party", "S1"),
		party_tax_id=kw.pop("party_tax_id", SUPPLIER_VAT),
		**kw,
	)


def gl(no, account, amount, vt="Purchase Invoice"):
	# input accounts are debit-positive, output accounts credit-positive
	sign = -1 if account in (OUT, ZERO_ACC) else 1
	return GLRow(vt, no, account, D(amount) * sign)


def run(lines, gl_rows=None, cfg=None, **kw):
	if gl_rows is None:
		gl_rows = [gl(x.voucher_no, x.vat_account, x.vat, x.voucher_type) for x in lines if x.vat_account]
	# rules equivalent to engine 0.1.0 (sdce_vat/tests/rule_fixtures.py): every expectation below is unchanged
	kw.setdefault("rule_book", parity_book())
	return calculate(cfg or config(), "2026-07-01", "2026-09-30", lines, gl_rows, **kw)


class TestMoney(UnitTestCase):
	def test_decimal_without_float_error(self):
		self.assertEqual(D(0.1) + D(0.2), Decimal("0.3"))

	def test_round_half_up_to_halalas(self):
		self.assertEqual(q2("2.675"), Decimal("2.68"))
		self.assertEqual(q2("-2.675"), Decimal("-2.68"))
		self.assertEqual(total(["0.005", "0.005"]), Decimal("0.02"))


class TestClassification(UnitTestCase):
	def test_standard_sale_and_input(self):
		result = run([line("SI1", Side.SALES, OUT, vt="Sales Invoice"), line("PI1")])
		self.assertEqual(result.boxes[boxes.SALES_STANDARD].vat, Decimal("15.00"))
		self.assertEqual(result.boxes[boxes.PURCHASES_STANDARD].vat, Decimal("15.00"))
		self.assertEqual(result.boxes[boxes.VAT_DUE].vat, Decimal("0.00"))
		self.assertTrue(result.is_reconciled)

	def test_zero_vat_without_category_needs_review(self):
		result = run([line("PI1", account=None, vat="0")])
		(only,) = result.lines
		self.assertEqual(only.treatment, Treatment.NEEDS_REVIEW)
		self.assertEqual(only.reason, "zero_vat_unclassified")
		self.assertIsNone(only.box)
		self.assertEqual(result.boxes[boxes.PURCHASES_TOTAL].amount, Decimal("0.00"))

	def test_zero_rated_exempt_out_of_scope_by_category(self):
		result = run(
			[
				line("PI1", account=None, vat="0", tax_category="Zero"),
				line("PI2", account=None, vat="0", item_tax_templates=("Exempt",)),
				line("PI3", account=None, vat="0", zatca_categories=("Outside",)),
				line("SI1", Side.SALES, None, vat="0", vt="Sales Invoice", tax_category="Export"),
			]
		)
		by_no = {x.voucher_no: x for x in result.lines}
		self.assertEqual(by_no["PI1"].box, boxes.PURCHASES_ZERO_RATED)
		self.assertEqual(by_no["PI2"].box, boxes.PURCHASES_EXEMPT)
		self.assertIsNone(by_no["PI3"].box)
		self.assertFalse(by_no["PI3"].needs_review)
		self.assertEqual(by_no["SI1"].box, boxes.SALES_EXPORTS)

	def test_conflicting_categories_need_review(self):
		result = run(
			[line("PI1", account=None, vat="0", tax_category="Zero", item_tax_templates=("Exempt",))]
		)
		self.assertEqual(result.lines[0].reason, "conflicting_categories")

	def test_export_category_on_purchase_needs_review(self):
		result = run([line("PI1", account=None, vat="0", tax_category="Export")])
		self.assertEqual(result.lines[0].treatment, Treatment.NEEDS_REVIEW)

	def test_non_deductible_waits_for_placement_rule(self):
		result = run([line("PI1", account=None, vat="0", tax_category="NoClaim")])
		(only,) = result.lines
		self.assertEqual(only.treatment, Treatment.INPUT_NOT_DEDUCTIBLE)
		self.assertEqual(only.reason, "pending_placement_rule")
		self.assertTrue(only.needs_review)
		self.assertIsNone(only.box)

	def test_non_deductible_follows_placement_rule_when_set(self):
		exclude = run(
			[line("PI1", account=None, vat="0", tax_category="NoClaim")],
			cfg=config(non_deductible_placement=NonDeductiblePlacement.EXCLUDE),
		)
		self.assertIsNone(exclude.lines[0].box)
		self.assertFalse(exclude.lines[0].needs_review)
		box7 = run(
			[line("PI1", account=None, vat="0", tax_category="NoClaim")],
			cfg=config(non_deductible_placement=NonDeductiblePlacement.BOX_7_WITHOUT_VAT),
		)
		self.assertEqual(box7.boxes[boxes.PURCHASES_STANDARD].amount, Decimal("100.00"))
		self.assertEqual(box7.boxes[boxes.PURCHASES_STANDARD].vat, Decimal("0.00"))

	def test_reverse_charge_account(self):
		result = run([line("PI1", account=RCM)])
		self.assertEqual(result.lines[0].box, boxes.PURCHASES_IMPORT_REVERSE_CHARGE)

	def test_rate_is_configuration_not_assumed(self):
		cfg = config(input_accounts={"VAT 5 - T": Decimal("5")})
		result = run([line("PI1", account="VAT 5 - T", base="100", vat="5")], cfg=cfg)
		self.assertNotIn("rate_mismatch", result.lines[0].warnings)
		result = run([line("PI2", account="VAT 5 - T", base="100", vat="15")], cfg=cfg)
		self.assertIn("rate_mismatch", result.lines[0].warnings)

	def test_vat_on_zero_rate_account_needs_review(self):
		result = run([line("SI1", Side.SALES, ZERO_ACC, vt="Sales Invoice")])
		self.assertEqual(result.lines[0].reason, "vat_on_zero_rate_account")

	def test_unconfigured_account_needs_review(self):
		result = run([line("PI1", account="Other - T")], gl_rows=[])
		self.assertEqual(result.lines[0].reason, "account_not_configured")


class TestAdjustments(UnitTestCase):
	def test_credit_note_goes_to_adjustment_column(self):
		result = run(
			[
				line("SI1", Side.SALES, OUT, base="1000", vat="150", vt="Sales Invoice"),
				line("SI2", Side.SALES, OUT, base="-200", vat="-30", vt="Sales Invoice", is_return=True),
			]
		)
		box = result.boxes[boxes.SALES_STANDARD]
		self.assertEqual(
			(box.amount, box.adjustment, box.vat), (Decimal("1000.00"), Decimal("-200.00"), Decimal("120.00"))
		)
		self.assertEqual(result.lines[1].column, Column.ADJUSTMENT)

	def test_negative_journal_correction_is_an_adjustment(self):
		result = run([line("PI1"), line("JV1", base="0", vat="-15", vt="Journal Entry")])
		self.assertEqual(result.boxes[boxes.PURCHASES_STANDARD].vat, Decimal("0.00"))
		jv = next(x for x in result.lines if x.voucher_no == "JV1")
		self.assertEqual(jv.column, Column.ADJUSTMENT)

	def test_journal_claim_and_missing_vat_number_warn(self):
		result = run([line("JV1", vt="Journal Entry", party_tax_id="3")])
		warnings = result.lines[0].warnings
		self.assertIn("journal_entry_claim_needs_document_review", warnings)
		self.assertIn("supplier_vat_number_missing_or_invalid", warnings)
		self.assertEqual(result.lines[0].box, boxes.PURCHASES_STANDARD)  # warned, still placed

	def test_corrections_and_credit_carried(self):
		result = run([line("SI1", Side.SALES, OUT, vt="Sales Invoice")], corrections="10", credit_carried="4")
		self.assertEqual(result.boxes[boxes.NET_VAT].vat, Decimal("21.00"))


class TestReconciliationAndDuplicates(UnitTestCase):
	def test_same_source_twice_is_refused(self):
		with self.assertRaises(ValueError):
			run([line("PI1"), line("PI1")])

	def test_unmatched_gl_becomes_review_line(self):
		lines = [line("PI1")]
		gl_rows = [gl("PI1", INP, "15"), gl("PE1", INP, "7", vt="Payment Entry")]
		result = run(lines, gl_rows)
		extra = next(x for x in result.lines if x.voucher_no == "PE1")
		self.assertEqual(extra.reason, "unmatched_gl")
		self.assertIsNone(extra.box)
		self.assertTrue(result.is_reconciled)  # explained by a review line, still counted in proof

	def test_gl_difference_is_reported_not_forced(self):
		result = run([line("PI1")], [gl("PI1", INP, "14")])
		self.assertIn("gl_difference", result.lines[0].warnings)
		self.assertFalse(result.is_reconciled)
		(proof,) = result.proof
		self.assertEqual(proof.difference, Decimal("-1.00"))
		self.assertEqual(result.boxes[boxes.PURCHASES_STANDARD].vat, Decimal("15.00"))

	def test_possible_duplicate_is_flagged_not_removed(self):
		result = run([line("PI1", bill_no="0012-"), line("JV1", vt="Journal Entry", bill_no="12")])
		self.assertTrue(all("possible_duplicate" in x.warnings for x in result.lines))
		self.assertEqual(result.boxes[boxes.PURCHASES_STANDARD].vat, Decimal("30.00"))

	def test_box_detail_sums_to_box(self):
		lines = [line(f"PI{i}", base="33.33", vat="5.00") for i in range(3)]
		result = run(lines)
		box = result.boxes[boxes.PURCHASES_STANDARD]
		self.assertEqual(len(box.lines), 3)
		self.assertEqual(box.amount, Decimal("99.99"))
		self.assertEqual(result.boxes[boxes.PURCHASES_TOTAL].vat, box.vat)


class TestRows(UnitTestCase):
	def test_invoice_base_from_item_wise_tax_detail(self):
		doc = {
			"name": "PI1",
			"posting_date": "2026-07-01",
			"company": "T",
			"supplier": "S1",
			"base_net_total": 300,
		}
		taxes = [
			{"name": "t1", "account_head": INP, "base_tax_amount_after_discount_amount": 30},
			{"name": "t2", "account_head": "Freight - T", "base_tax_amount_after_discount_amount": 50},
		]
		item_tax = [{"tax_row": "t1", "taxable_amount": 200}, {"tax_row": "t2", "taxable_amount": 300}]
		(only,) = invoice_lines("Purchase Invoice", doc, taxes, item_tax, config())
		self.assertEqual((only.base, only.vat, only.vat_account), (Decimal("200.00"), Decimal("30.00"), INP))

	def test_invoice_without_vat_row(self):
		doc = {
			"name": "PI1",
			"posting_date": "2026-07-01",
			"company": "T",
			"supplier": "S1",
			"base_net_total": "19.51",
		}
		(only,) = invoice_lines("Purchase Invoice", doc, [], [], config())
		self.assertIsNone(only.vat_account)
		self.assertEqual(only.base, Decimal("19.51"))

	def test_vat_row_of_zero_is_no_vat_charged(self):
		doc = {
			"name": "PI1",
			"posting_date": "2026-07-01",
			"company": "T",
			"supplier": "S1",
			"base_net_total": "20",
		}
		taxes = [{"name": "t1", "account_head": INP, "base_tax_amount_after_discount_amount": 0}]
		(only,) = invoice_lines(
			"Purchase Invoice", doc, taxes, [{"tax_row": "t1", "taxable_amount": 0}], config()
		)
		self.assertIsNone(only.vat_account)
		self.assertEqual((only.base, only.source_rows), (Decimal("20.00"), ("t1",)))
		result = run([only], [])
		self.assertEqual(result.lines[0].reason, "zero_vat_unclassified")

	def test_deducted_tax_row_is_negative(self):
		doc = {"name": "PI1", "posting_date": "2026-07-01", "company": "T", "supplier": "S1"}
		taxes = [
			{
				"name": "t1",
				"account_head": INP,
				"base_tax_amount_after_discount_amount": 15,
				"add_deduct_tax": "Deduct",
			}
		]
		(only,) = invoice_lines(
			"Purchase Invoice", doc, taxes, [{"tax_row": "t1", "taxable_amount": 100}], config()
		)
		self.assertEqual((only.base, only.vat), (Decimal("-100.00"), Decimal("-15.00")))

	def test_journal_base_with_party_and_bank_entry(self):
		je = {"name": "JV1", "posting_date": "2026-07-01", "company": "T"}
		with_party = [
			{"name": "a", "account": "Expense - T", "debit": 2000, "credit": 0},
			{"name": "b", "account": INP, "debit": 300, "credit": 0},
			{
				"name": "c",
				"account": "Creditors - T",
				"debit": 0,
				"credit": 2300,
				"party_type": "Supplier",
				"party": "S1",
			},
		]
		(jl,) = journal_lines(je, with_party, config(), {("Supplier", "S1"): SUPPLIER_VAT})
		self.assertEqual(
			(jl.base, jl.vat, jl.party_tax_id), (Decimal("2000.00"), Decimal("300.00"), SUPPLIER_VAT)
		)
		bank = [
			{"name": "a", "account": "Expense - T", "debit": 100, "credit": 0},
			{"name": "b", "account": INP, "debit": 15, "credit": 0},
			{"name": "c", "account": "Bank - T", "debit": 0, "credit": 115},
		]
		(bl,) = journal_lines(je, bank, config(), {})
		self.assertEqual(bl.base, Decimal("100.00"))

	def test_journal_correction_has_no_base(self):
		je = {"name": "JV1", "posting_date": "2026-07-01", "company": "T"}
		rows = [
			{"name": "a", "account": "Expense - T", "debit": 13.05, "credit": 0},
			{"name": "b", "account": INP, "debit": 0, "credit": 13.05},
		]
		(jl,) = journal_lines(je, rows, config(), {})
		self.assertEqual((jl.base, jl.vat), (Decimal("0.00"), Decimal("-13.05")))


class TestConfig(UnitTestCase):
	def test_account_mapped_twice_is_refused(self):
		with self.assertRaises(ValueError):
			config(input_accounts={OUT: Decimal("15")}).validate()

	def test_float_rate_is_refused(self):
		with self.assertRaises(ValueError):
			config(input_accounts={INP: 15.0}).validate()
