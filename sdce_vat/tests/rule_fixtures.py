# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Synthetic rule sets for tests. PARITY_RULES state, as rules, exactly what engine 0.1.0 had in code: the box of
every treatment, the 15 % standard rate and the posting date as tax date. They are test data, not tax advice."""

from decimal import Decimal

from sdce_vat.engine.config import VatConfig
from sdce_vat.engine.model import GLRow, Side, SourceLine, Treatment
from sdce_vat.engine.money import D
from sdce_vat.engine.rules import NORMAL, Rule, RuleBook, RuleSet

PARITY_CODE = "TEST-PARITY"
PARITY_RULES = {
	"standard_rate": "15",
	"treatment_box:standard_rated_sale": "S01",
	"treatment_box:government_bears": "S02",
	"treatment_box:zero_rated_sale": "S03",
	"treatment_box:export": "S04",
	"treatment_box:exempt_sale": "S05",
	"treatment_box:input_deductible": "P07",
	"treatment_box:import_customs": "P08",
	"treatment_box:import_reverse_charge": "P09",
	"treatment_box:zero_rated_purchase": "P10",
	"treatment_box:exempt_purchase": "P11",
	"treatment_box:out_of_scope": None,  # Not applicable: no return field
	"tax_date_basis:sales_invoice": "posting_date",
	"tax_date_basis:purchase_invoice": "posting_date",
	"tax_date_basis:journal_entry": "posting_date",
	"tax_date_basis:expense_claim": "posting_date",
}


def rule_set(name="TEST-PARITY-1", start="2020-01-01", end=None, rules=None, **values) -> RuleSet:
	rules = PARITY_RULES if rules is None else rules
	return RuleSet(
		name=name,
		code=values.pop("code", PARITY_CODE),
		version=values.pop("version", 1),
		version_type=values.pop("version_type", NORMAL),
		effective_from=start,
		effective_to=end,
		content_hash=values.pop("content_hash", "h-" + name),
		rules={
			key: Rule(
				key, value or "-", "Not applicable" if value is None else values.get("status", "Verified")
			)
			for key, value in rules.items()
		},
		supersedes=values.pop("supersedes", None),
	)


def parity_book() -> RuleBook:
	return RuleBook(PARITY_CODE, [rule_set()])


# ---- parity scenario: every treatment, column and review path of engine 0.1.0 -------------------------------
OUT, INP, RCM, ZERO_ACC = "VAT Out - P", "VAT In - P", "VAT RCM - P", "VAT 0 - P"


def parity_config() -> VatConfig:
	return VatConfig(
		company="P",
		output_accounts={OUT: Decimal("15"), ZERO_ACC: Decimal("0")},
		input_accounts={INP: Decimal("15")},
		reverse_charge_accounts={RCM: Decimal("15")},
		category_treatments={
			"Zero": Treatment.ZERO_RATED_SALE,
			"Exempt": Treatment.EXEMPT_SALE,
			"Outside": Treatment.OUT_OF_SCOPE,
			"NoClaim": Treatment.INPUT_NOT_DEDUCTIBLE,
			"Export": Treatment.EXPORT,
			"Gov": Treatment.GOVERNMENT_BEARS,
		},
		rule_set_code=PARITY_CODE,
	)


def _line(no, vt, side, account, base, vat, **kw):
	return SourceLine(
		voucher_type=vt,
		voucher_no=no,
		side=side,
		posting_date=kw.pop("posting_date", "2026-07-10"),
		company="P",
		vat_account=account,
		base=D(base),
		vat=D(vat),
		party_type="Supplier" if side == Side.PURCHASES else "Customer",
		party=kw.pop("party", "S1" if side == Side.PURCHASES else "C1"),
		party_tax_id=kw.pop("party_tax_id", "300000000000003"),
		**kw,
	)


def parity_lines() -> list[SourceLine]:
	S, P, SI, PI, JE = Side.SALES, Side.PURCHASES, "Sales Invoice", "Purchase Invoice", "Journal Entry"
	return [
		_line("PI-1", PI, P, INP, "100", "15", bill_no="B-1"),
		_line("PI-2", PI, P, INP, "-50", "-7.50", is_return=True, return_against="PI-1"),
		_line("PI-3", PI, P, RCM, "400", "60"),
		_line("PI-4", PI, P, None, "70", "0", tax_category="Outside"),
		_line("PI-5", PI, P, None, "80", "0", tax_category="NoClaim"),
		_line("PI-6", PI, P, None, "90", "0", tax_category="Zero"),
		_line("PI-7", PI, P, INP, "200", "40", bill_no="B-7"),  # rate mismatch warning
		_line(
			"PI-8", PI, P, INP, "100", "15", bill_no="B-1", party_tax_id=None
		),  # duplicate bill, no VAT no.
		_line("SI-1", SI, S, OUT, "1000", "150"),
		_line("SI-2", SI, S, OUT, "-200", "-30", is_return=True, return_against="SI-1"),
		_line("SI-3", SI, S, ZERO_ACC, "500", "0", tax_category="Zero"),
		_line("SI-4", SI, S, None, "300", "0", tax_category="Export"),
		_line("SI-5", SI, S, None, "50", "0", tax_category="Exempt"),
		_line("SI-6", SI, S, None, "60", "0"),  # unclassified
		_line("SI-7", SI, S, OUT, "10", "1.50", is_debit_note=True, return_against="SI-1"),
		_line("SI-8", SI, S, None, "120", "0", tax_category="Gov"),
		_line("JE-1", JE, P, INP, "400", "60"),
		_line("JE-2", JE, P, INP, "-100", "-15"),
	]


def parity_gl() -> list[GLRow]:
	rows = []
	for line in parity_lines():
		if line.vat_account:
			sign = -1 if line.vat_account in (OUT, ZERO_ACC) else 1
			rows.append(GLRow(line.voucher_type, line.voucher_no, line.vat_account, line.vat * sign))
	rows.append(GLRow("Journal Entry", "JE-99", OUT, D("-5")))  # VAT no document explains
	rows.append(GLRow("Purchase Invoice", "PI-1", INP, D("1")))  # GL differs from the document by 1
	return rows


def parity_digest(result) -> dict:
	"""The parts of a result that engine 0.1.0 already produced; new fields are left out."""
	return {
		"boxes": {k: v.as_dict() for k, v in result.boxes.items()},
		"proof": [p.as_dict() for p in result.proof],
		"review_count": len(result.review_lines),
		"warning_count": len(result.warning_lines),
		"lines": [
			[
				line.voucher_type,
				line.voucher_no,
				line.vat_account or "",
				str(line.treatment),
				line.reason,
				line.box or "",
				str(line.column or ""),
				sorted(line.warnings),
				str(line.base),
				str(line.vat),
			]
			for line in result.lines
		],
	}
