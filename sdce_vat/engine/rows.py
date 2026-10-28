# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Turn document rows (plain dicts) into SourceLines. Pure: the site reader and offline exports share it."""

from collections import defaultdict

from sdce_vat.engine.config import VatConfig
from sdce_vat.engine.model import Side, SourceLine
from sdce_vat.engine.money import ZERO, D, q2


def invoice_lines(
	doctype: str,
	doc: dict,
	taxes: list[dict],
	item_tax: list[dict],
	config: VatConfig,
	party_tax_id: str | None = None,
	item_tax_templates: tuple[str, ...] = (),
	zatca_categories: tuple[str, ...] = (),
) -> list[SourceLine]:
	"""One line per configured VAT account on a Sales or Purchase Invoice; one line without VAT otherwise.

	The base of each VAT line is the taxable amount ERPNext stored per tax row (Item Wise Tax Detail),
	not VAT divided by a rate.
	"""
	side = Side.SALES if doctype == "Sales Invoice" else Side.PURCHASES
	party_field = "customer" if side == Side.SALES else "supplier"
	common = dict(
		voucher_type=doctype,
		voucher_no=doc["name"],
		side=side,
		posting_date=str(doc["posting_date"]),
		invoice_date=_iso(doc["posting_date"] if side == Side.SALES else doc.get("bill_date")),
		company=doc["company"],
		party_type="Customer" if side == Side.SALES else "Supplier",
		party=doc.get(party_field),
		party_tax_id=party_tax_id or doc.get("tax_id"),
		bill_no=doc.get("bill_no") if side == Side.PURCHASES else doc["name"],
		is_return=bool(doc.get("is_return")),
		is_debit_note=bool(doc.get("is_debit_note")),
		return_against=doc.get("return_against"),
		tax_category=doc.get("tax_category"),
		item_tax_templates=tuple(sorted(set(item_tax_templates))),
		zatca_categories=tuple(sorted(set(zatca_categories))),
	)
	base_by_tax_row = defaultdict(lambda: ZERO)
	for row in item_tax:
		base_by_tax_row[row["tax_row"]] += D(row["taxable_amount"])

	vat = defaultdict(lambda: ZERO)
	base = defaultdict(lambda: ZERO)
	rows = defaultdict(list)
	for tax in taxes:
		account = tax["account_head"]
		if account not in config.vat_accounts:
			continue
		sign = -1 if tax.get("add_deduct_tax") == "Deduct" else 1
		vat[account] += sign * D(tax["base_tax_amount_after_discount_amount"])
		base[account] += sign * base_by_tax_row.get(tax["name"], ZERO)
		rows[account].append(tax["name"])

	if not any(q2(v) for v in vat.values()):
		# no VAT charged (no VAT row, or VAT rows of 0): the treatment must come from categories or a reviewer
		zero_rows = tuple(name for names in rows.values() for name in names)
		return [
			SourceLine(vat_account=None, base=q2(doc.get("base_net_total")), source_rows=zero_rows, **common)
		]
	return [
		SourceLine(
			vat_account=account,
			base=q2(base[account]),
			vat=q2(vat[account]),
			source_rows=tuple(rows[account]),
			**common,
		)
		for account in sorted(vat)
	]


def journal_lines(je: dict, accounts: list[dict], config: VatConfig, party_tax_ids: dict) -> list[SourceLine]:
	"""One line per configured VAT account on a Journal Entry.

	Base (rule NON_VAT_LINES): the non-VAT lines without a party that sit on the same side (debit or credit)
	as the VAT. A bank or cash line on the other side is the payment, not the base.
	"""
	party_rows = [a for a in accounts if a.get("party")]
	party = party_rows[0] if party_rows else {}
	lines = []
	for account in sorted({a["account"] for a in accounts if a["account"] in config.vat_accounts}):
		sign = -1 if account in config.output_accounts else 1
		side = Side.SALES if account in config.output_accounts else Side.PURCHASES
		own = [a for a in accounts if a["account"] == account]
		vat = sign * sum((D(a["debit"]) - D(a["credit"]) for a in own), ZERO)
		others = [a for a in accounts if a["account"] not in config.vat_accounts and not a.get("party")]
		vat_on_debit = (vat >= ZERO) == (sign == 1)
		side_total = sum((D(a["debit"] if vat_on_debit else a["credit"]) for a in others), ZERO)
		base = side_total if vat >= ZERO else -side_total
		lines.append(
			SourceLine(
				voucher_type="Journal Entry",
				voucher_no=je["name"],
				side=side,
				posting_date=str(je["posting_date"]),
				invoice_date=_iso(je.get("bill_date")),
				company=je["company"],
				vat_account=account,
				base=q2(base),
				vat=q2(vat),
				party_type=party.get("party_type"),
				party=party.get("party"),
				party_tax_id=party_tax_ids.get((party.get("party_type"), party.get("party"))),
				bill_no=je.get("bill_no") or je.get("cheque_no"),
				source_rows=tuple(a["name"] for a in own),
			)
		)
	return lines


def expense_claim_lines(claim: dict, taxes: list[dict], config: VatConfig) -> list[SourceLine]:
	"""One line per configured VAT account on an Expense Claim (hrms)."""
	vat = defaultdict(lambda: ZERO)
	rows = defaultdict(list)
	for tax in taxes:
		if tax["account_head"] in config.vat_accounts:
			vat[tax["account_head"]] += D(tax["base_tax_amount"])
			rows[tax["account_head"]].append(tax["name"])
	single = len(vat) == 1
	return [
		SourceLine(
			voucher_type="Expense Claim",
			voucher_no=claim["name"],
			side=Side.PURCHASES,
			posting_date=str(claim["posting_date"]),
			company=claim["company"],
			vat_account=account,
			# with one VAT account the sanctioned amount is the base; with several it cannot be split safely
			base=q2(claim.get("total_sanctioned_amount")) if single else ZERO,
			vat=q2(vat[account]),
			party_type="Employee",
			party=claim.get("employee"),
			source_rows=tuple(rows[account]),
		)
		for account in sorted(vat)
	]


def _iso(value) -> str | None:
	return str(value) if value else None
