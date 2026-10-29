# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Classification and placement rules. Pure functions: a line plus the configuration in, a decided line out.

Rule order for one line:
1. The VAT account decides the family (output, input, reverse charge, customs).
2. A line without VAT (or on a 0 % account) takes its treatment from its categories; no category, no treatment:
   it is NEEDS_REVIEW and never placed in a box.
3. The published rule set of the line's tax date decides the box of the treatment (`treatment_box:<t>`; Not
   applicable = no box). Returns, debit notes and negative journal corrections go to the adjustment column.
   A missing, unverified or invalid rule is a rule issue: the line is not placed and needs review.
4. Input VAT that is not deductible is placed only when a placement rule is configured in the settings.
Warnings never move a line; they mark it for the reviewer.
"""

import re

from sdce_vat.engine import boxes
from sdce_vat.engine.config import NonDeductiblePlacement, VatConfig
from sdce_vat.engine.model import Column, Side, SourceLine, Treatment
from sdce_vat.engine.money import ZERO, D, q2
from sdce_vat.engine.rules import NOT_APPLICABLE, VERIFIED, RuleSet, verified_value

SAUDI_VAT_NUMBER = re.compile(r"3\d{13}3")

SALES_TREATMENTS = {
	Treatment.STANDARD_RATED_SALE,
	Treatment.GOVERNMENT_BEARS,
	Treatment.ZERO_RATED_SALE,
	Treatment.EXPORT,
	Treatment.EXEMPT_SALE,
	Treatment.OUT_OF_SCOPE,
}
PURCHASE_TREATMENTS = {
	Treatment.INPUT_DEDUCTIBLE,
	Treatment.INPUT_NOT_DEDUCTIBLE,
	Treatment.IMPORT_CUSTOMS,
	Treatment.IMPORT_REVERSE_CHARGE,
	Treatment.ZERO_RATED_PURCHASE,
	Treatment.EXEMPT_PURCHASE,
	Treatment.OUT_OF_SCOPE,
}
# a category written for one side means the same thing on the other side
SIDE_EQUIVALENT = {
	(Treatment.ZERO_RATED_SALE, Side.PURCHASES): Treatment.ZERO_RATED_PURCHASE,
	(Treatment.EXEMPT_SALE, Side.PURCHASES): Treatment.EXEMPT_PURCHASE,
	(Treatment.ZERO_RATED_PURCHASE, Side.SALES): Treatment.ZERO_RATED_SALE,
	(Treatment.EXEMPT_PURCHASE, Side.SALES): Treatment.EXEMPT_SALE,
}


def classify(line: SourceLine, config: VatConfig, rule_set: RuleSet | None) -> SourceLine:
	"""`rule_set` is the published set of the line's tax date, or None when `line.rule_issue` says why not."""
	treatment, reason = _treatment(line, config)
	line.treatment, line.reason = treatment, reason
	line.box = _box(line, config, rule_set)
	if treatment == Treatment.INPUT_NOT_DEDUCTIBLE and config.non_deductible_placement is None:
		line.reason = "pending_placement_rule"
	line.column = _column(line) if line.box else None
	line.warnings = _warnings(line, config, rule_set)
	return line


def _treatment(line: SourceLine, config: VatConfig) -> tuple[Treatment, str]:
	account = line.vat_account
	if account in config.vat_accounts and config.vat_accounts[account] > 0 and line.vat == ZERO:
		return Treatment.NEEDS_REVIEW, "zero_vat_on_vat_account"
	if account in config.reverse_charge_accounts:
		return _for_side(Treatment.IMPORT_REVERSE_CHARGE, line.side, "reverse_charge_account")
	if account in config.customs_accounts:
		return _for_side(Treatment.IMPORT_CUSTOMS, line.side, "customs_account")
	if account in config.output_accounts and line.side == Side.SALES and config.output_accounts[account] > 0:
		return Treatment.STANDARD_RATED_SALE, "output_account"
	if (
		account in config.input_accounts
		and line.side == Side.PURCHASES
		and config.input_accounts[account] > 0
	):
		return Treatment.INPUT_DEDUCTIBLE, "input_account"
	if account is not None and account not in config.vat_accounts:
		return Treatment.NEEDS_REVIEW, "account_not_configured"
	if account is not None and line.vat != ZERO and config.vat_accounts[account] == 0:
		return Treatment.NEEDS_REVIEW, "vat_on_zero_rate_account"
	if account is not None and config.vat_accounts[account] > 0:
		# an output account seen from purchases (or the reverse): only a reviewer can say what it is
		return Treatment.NEEDS_REVIEW, "account_side_mismatch"
	return _from_categories(line, config)


def _from_categories(line: SourceLine, config: VatConfig) -> tuple[Treatment, str]:
	categories = [c for c in (line.tax_category, *line.item_tax_templates, *line.zatca_categories) if c]
	found = {config.category_treatments[c] for c in categories if c in config.category_treatments}
	if not found:
		return Treatment.NEEDS_REVIEW, "zero_vat_unclassified"
	if len(found) > 1:
		return Treatment.NEEDS_REVIEW, "conflicting_categories"
	return _for_side(found.pop(), line.side, "category")


def _for_side(treatment: Treatment, side: Side, reason: str) -> tuple[Treatment, str]:
	treatment = SIDE_EQUIVALENT.get((treatment, side), treatment)
	allowed = SALES_TREATMENTS if side == Side.SALES else PURCHASE_TREATMENTS
	if treatment not in allowed:
		return Treatment.NEEDS_REVIEW, f"{treatment}_not_valid_for_{side}"
	return treatment, reason


def _box(line: SourceLine, config: VatConfig, rule_set: RuleSet | None) -> str | None:
	treatment = line.treatment
	if treatment == Treatment.NEEDS_REVIEW or line.rule_issue:
		return None
	if treatment == Treatment.INPUT_NOT_DEDUCTIBLE:
		if config.non_deductible_placement == NonDeductiblePlacement.BOX_7_WITHOUT_VAT:
			return boxes.PURCHASES_STANDARD
		return None
	key = f"treatment_box:{treatment}"
	rule = rule_set.rule(key)
	if not rule:
		line.rule_issue = f"rule_missing:{key}"
		return None
	if rule.status == NOT_APPLICABLE:
		return None  # the treatment has no return field (e.g. out of scope)
	allowed = boxes.SALES_LINE_BOXES if line.side == Side.SALES else boxes.PURCHASE_LINE_BOXES
	if rule.status != VERIFIED or rule.value not in allowed:
		line.rule_issue = f"rule_invalid:{key}" if rule.status == VERIFIED else f"rule_unverified:{key}"
		return None
	return rule.value


def _column(line: SourceLine) -> Column:
	if line.is_return or line.is_debit_note:
		return Column.ADJUSTMENT
	if line.voucher_type == "Journal Entry" and line.vat < ZERO:
		return Column.ADJUSTMENT  # a correction that reverses VAT
	return Column.AMOUNT


def _warnings(line: SourceLine, config: VatConfig, rule_set: RuleSet | None) -> list[str]:
	warnings = []
	rate = config.vat_accounts.get(line.vat_account) if line.vat_account else None
	if rate and rule_set and not line.rule_issue:
		standard, issue = verified_value(rule_set, "standard_rate")
		if issue:
			line.rule_issue, line.box, line.column = issue, None, None
		elif _decimal(standard) != rate:
			warnings.append("rate_differs_from_rule")
	if rate and line.vat != ZERO:
		if line.base == ZERO:
			warnings.append("base_missing")
		else:
			expected = q2(line.base * rate / 100)
			allowed = config.tolerance * max(1, len(line.source_rows))
			if abs(expected - line.vat) > allowed:
				warnings.append("rate_mismatch")
	if line.side == Side.PURCHASES and line.treatment == Treatment.INPUT_DEDUCTIBLE:
		if not SAUDI_VAT_NUMBER.fullmatch(line.party_tax_id or ""):
			warnings.append("supplier_vat_number_missing_or_invalid")
		if line.voucher_type == "Journal Entry":
			warnings.append("journal_entry_claim_needs_document_review")
	return warnings


def _decimal(value):
	try:
		return D(value)
	except ArithmeticError:
		return None
