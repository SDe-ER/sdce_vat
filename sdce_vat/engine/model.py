# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Data shapes of the engine. Plain dataclasses, no database access."""

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import StrEnum

from sdce_vat.engine.money import ZERO


class Side(StrEnum):
	SALES = "sales"
	PURCHASES = "purchases"


class Treatment(StrEnum):
	STANDARD_RATED_SALE = "standard_rated_sale"
	GOVERNMENT_BEARS = "government_bears"
	ZERO_RATED_SALE = "zero_rated_sale"
	EXPORT = "export"
	EXEMPT_SALE = "exempt_sale"
	INPUT_DEDUCTIBLE = "input_deductible"
	INPUT_NOT_DEDUCTIBLE = "input_not_deductible"
	IMPORT_CUSTOMS = "import_customs"
	IMPORT_REVERSE_CHARGE = "import_reverse_charge"
	ZERO_RATED_PURCHASE = "zero_rated_purchase"
	EXEMPT_PURCHASE = "exempt_purchase"
	OUT_OF_SCOPE = "out_of_scope"
	NEEDS_REVIEW = "needs_review"


class Column(StrEnum):
	AMOUNT = "amount"
	ADJUSTMENT = "adjustment"


@dataclass
class SourceLine:
	"""One VAT-relevant line: a document (or ledger rest) on one VAT account, or a document without VAT."""

	voucher_type: str
	voucher_no: str
	side: Side
	posting_date: str
	company: str
	vat_account: str | None  # None: the document carries no VAT row
	base: Decimal = ZERO  # taxable amount in company currency, signed
	vat: Decimal = ZERO  # VAT in company currency, signed (input: debit +; output: credit +)
	party_type: str | None = None
	party: str | None = None
	party_tax_id: str | None = None
	bill_no: str | None = None
	is_return: bool = False  # credit/debit note of an invoice, or a return
	is_debit_note: bool = False
	return_against: str | None = None
	tax_category: str | None = None
	item_tax_templates: tuple[str, ...] = ()
	zatca_categories: tuple[str, ...] = ()  # ksa_compliance categories when that app is installed
	source_rows: tuple[str, ...] = ()  # child row names that produced the line (traceability)
	# filled by classification
	treatment: Treatment | None = None
	reason: str = ""
	box: str | None = None
	column: Column | None = None
	warnings: list[str] = field(default_factory=list)

	@property
	def key(self) -> tuple:
		return (self.voucher_type, self.voucher_no, self.vat_account or "", self.side)

	@property
	def needs_review(self) -> bool:
		# unclassified, or not deductible while no placement rule is set
		return self.treatment == Treatment.NEEDS_REVIEW or self.reason == "pending_placement_rule"

	def as_dict(self) -> dict:
		data = asdict(self)
		for key in ("base", "vat"):
			data[key] = str(data[key])
		return data


@dataclass(frozen=True)
class GLRow:
	voucher_type: str
	voucher_no: str
	account: str
	debit_minus_credit: Decimal


@dataclass
class BoxTotal:
	box: str
	amount: Decimal = ZERO
	adjustment: Decimal = ZERO
	vat: Decimal = ZERO
	lines: list[tuple] = field(default_factory=list)  # SourceLine keys

	def as_dict(self) -> dict:
		return {
			"box": self.box,
			"amount": str(self.amount),
			"adjustment": str(self.adjustment),
			"vat": str(self.vat),
			"line_count": len(self.lines),
		}


@dataclass
class AccountProof:
	account: str
	side: Side
	gl_vat: Decimal
	lines_vat: Decimal

	@property
	def difference(self) -> Decimal:
		return self.gl_vat - self.lines_vat

	def as_dict(self) -> dict:
		return {
			"account": self.account,
			"side": str(self.side),
			"gl_vat": str(self.gl_vat),
			"lines_vat": str(self.lines_vat),
			"difference": str(self.difference),
		}


@dataclass
class VatResult:
	company: str
	from_date: str
	to_date: str
	engine_version: str
	lines: list[SourceLine]
	boxes: dict[str, BoxTotal]
	proof: list[AccountProof]

	@property
	def review_lines(self) -> list[SourceLine]:
		return [line for line in self.lines if line.needs_review]

	@property
	def warning_lines(self) -> list[SourceLine]:
		return [line for line in self.lines if line.warnings]

	@property
	def is_reconciled(self) -> bool:
		return all(p.difference == 0 for p in self.proof)

	def as_dict(self) -> dict:
		return {
			"company": self.company,
			"from_date": self.from_date,
			"to_date": self.to_date,
			"engine_version": self.engine_version,
			"boxes": {k: v.as_dict() for k, v in self.boxes.items()},
			"proof": [p.as_dict() for p in self.proof],
			"is_reconciled": self.is_reconciled,
			"review_count": len(self.review_lines),
			"warning_count": len(self.warning_lines),
			"lines": [line.as_dict() for line in self.lines],
		}
