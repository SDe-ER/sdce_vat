# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Engine configuration. Every account, rate and category comes from here; nothing is hard-coded.

Phase 3 stores this in a settings DocType per company; until then callers build it explicitly.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from sdce_vat.engine.model import Treatment
from sdce_vat.engine.money import CENT


class NonDeductiblePlacement(StrEnum):
	"""Placement of input VAT that is not deductible. Unset (None in VatConfig) keeps such lines out of every box and under review."""

	EXCLUDE = "exclude"
	BOX_7_WITHOUT_VAT = "box_7_without_vat"


class JournalBaseRule(StrEnum):
	"""How the taxable base of a journal entry line is found."""

	NON_VAT_LINES = "non_vat_lines"  # sum of the non-VAT, non-party lines on the same side


@dataclass
class VatConfig:
	company: str
	# VAT account -> rate in percent (e.g. Decimal("15")). Rates are configuration, never assumed.
	output_accounts: dict[str, Decimal] = field(default_factory=dict)
	input_accounts: dict[str, Decimal] = field(default_factory=dict)
	reverse_charge_accounts: dict[str, Decimal] = field(default_factory=dict)
	customs_accounts: dict[str, Decimal] = field(default_factory=dict)
	# category (Tax Category, Item Tax Template or ksa_compliance ZATCA category value) -> treatment,
	# used for lines without VAT. Keys are matched exactly.
	category_treatments: dict[str, Treatment] = field(default_factory=dict)
	non_deductible_placement: NonDeductiblePlacement | None = None
	journal_base_rule: JournalBaseRule = JournalBaseRule.NON_VAT_LINES
	tolerance: Decimal = CENT
	include_expense_claims: bool = True

	@property
	def vat_accounts(self) -> dict[str, Decimal]:
		return {
			**self.output_accounts,
			**self.input_accounts,
			**self.reverse_charge_accounts,
			**self.customs_accounts,
		}

	def validate(self) -> None:
		accounts = [
			*self.output_accounts,
			*self.input_accounts,
			*self.reverse_charge_accounts,
			*self.customs_accounts,
		]
		duplicates = {a for a in accounts if accounts.count(a) > 1}
		if duplicates:
			raise ValueError(f"VAT account mapped twice: {sorted(duplicates)}")
		if not (self.output_accounts or self.input_accounts):
			raise ValueError("No VAT account configured")
		for rate in self.vat_accounts.values():
			if not isinstance(rate, Decimal) or rate < 0:
				raise ValueError(f"VAT rate must be a non-negative Decimal, got {rate!r}")
