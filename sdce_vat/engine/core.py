# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pure calculation core: lines and GL rows in, a reconciled result out. No database access.

The same core serves the live engine (lines read from the site) and offline runs on exported rows.
"""

import re
from collections import defaultdict

from sdce_vat.engine import boxes
from sdce_vat.engine.classify import classify
from sdce_vat.engine.config import VatConfig
from sdce_vat.engine.model import (
	AccountProof,
	BoxTotal,
	Column,
	GLRow,
	Side,
	SourceLine,
	Treatment,
	VatResult,
)
from sdce_vat.engine.money import ZERO, q2, total
from sdce_vat.engine.rules import RuleBook, resolve

ENGINE_VERSION = "0.2.0"


def calculate(
	config: VatConfig,
	from_date: str,
	to_date: str,
	lines: list[SourceLine],
	gl_rows: list[GLRow],
	*,
	rule_book: RuleBook,
	corrections=ZERO,
	credit_carried=ZERO,
) -> VatResult:
	config.validate()
	_assert_unique(lines)
	used = {}
	for line in lines:
		line.base, line.vat = q2(line.base), q2(line.vat)
		rule_set = resolve(line, rule_book, from_date, to_date)
		classify(line, config, rule_set)
		if rule_set and not line.rule_issue:
			used[rule_set.name] = rule_set
		else:
			line.rule_set = None
	lines = lines + _unmatched_gl_lines(lines, gl_rows, config)
	_flag_gl_differences(lines, gl_rows, config)
	_flag_possible_duplicates(lines)
	lines.sort(
		key=lambda line: (line.posting_date, line.voucher_type, line.voucher_no, line.vat_account or "")
	)
	result = VatResult(
		company=config.company,
		from_date=from_date,
		to_date=to_date,
		engine_version=ENGINE_VERSION,
		lines=lines,
		boxes=_box_totals(lines, q2(corrections), q2(credit_carried)),
		proof=_proof(lines, gl_rows, config),
		rule_sets=dict(sorted(used.items())),
	)
	_assert_boxes_match_lines(result)
	return result


def gl_sign(account: str, config: VatConfig) -> int:
	"""Input-type accounts are debit-positive; output accounts are credit-positive."""
	return -1 if account in config.output_accounts else 1


def _assert_unique(lines: list[SourceLine]) -> None:
	seen = set()
	for line in lines:
		if line.key in seen:
			raise ValueError(f"Source line counted twice: {line.key}")
		seen.add(line.key)


def _gl_by_voucher(gl_rows, config) -> dict[tuple, object]:
	grouped = defaultdict(lambda: ZERO)
	for row in gl_rows:
		if row.account in config.vat_accounts:
			grouped[(row.voucher_type, row.voucher_no, row.account)] += row.debit_minus_credit * gl_sign(
				row.account, config
			)
	return {key: q2(value) for key, value in grouped.items()}


def _lines_by_voucher(lines) -> dict[tuple, object]:
	grouped = defaultdict(lambda: ZERO)
	for line in lines:
		if line.vat_account:
			grouped[(line.voucher_type, line.voucher_no, line.vat_account)] += line.vat
	return grouped


def _unmatched_gl_lines(lines, gl_rows, config) -> list[SourceLine]:
	"""VAT in the ledger that no document line explains becomes a line that needs review."""
	known = _lines_by_voucher(lines)
	extra = []
	for (voucher_type, voucher_no, account), vat in _gl_by_voucher(gl_rows, config).items():
		if (voucher_type, voucher_no, account) in known or vat == ZERO:
			continue
		line = SourceLine(
			voucher_type=voucher_type,
			voucher_no=voucher_no,
			side=Side.SALES if account in config.output_accounts else Side.PURCHASES,
			posting_date="",
			company=config.company,
			vat_account=account,
			vat=vat,
			treatment=Treatment.NEEDS_REVIEW,
			reason="unmatched_gl",
		)
		extra.append(line)
	return extra


def _flag_gl_differences(lines, gl_rows, config) -> None:
	gl = _gl_by_voucher(gl_rows, config)
	for key, vat in _lines_by_voucher(lines).items():
		if gl.get(key, ZERO) != q2(vat):
			for line in lines:
				if (line.voucher_type, line.voucher_no, line.vat_account) == key:
					line.warnings.append("gl_difference")


def _normal_bill(bill_no) -> str:
	return re.sub(r"[^0-9A-Za-z]", "", str(bill_no or "")).lstrip("0").upper()


def _flag_possible_duplicates(lines) -> None:
	"""The same supplier invoice in two vouchers is reported, never removed."""
	by_bill = defaultdict(set)
	for line in lines:
		if line.side == Side.PURCHASES and line.party and _normal_bill(line.bill_no) and line.vat != ZERO:
			by_bill[(line.party, _normal_bill(line.bill_no))].add((line.voucher_type, line.voucher_no))
	for line in lines:
		vouchers = by_bill.get((line.party, _normal_bill(line.bill_no)), set())
		if len(vouchers) > 1:
			line.warnings.append("possible_duplicate")


def _box_totals(lines, corrections, credit_carried) -> dict[str, BoxTotal]:
	result = {box.id: BoxTotal(box.id) for box in boxes.BOXES}
	for line in lines:
		if not line.box:
			continue
		box = result[line.box]
		if line.column == Column.ADJUSTMENT:
			box.adjustment += line.base
		else:
			box.amount += line.base
		box.vat += line.vat
		box.lines.append(line.key)
	for total_box, parts in (
		(boxes.SALES_TOTAL, boxes.SALES_LINE_BOXES),
		(boxes.PURCHASES_TOTAL, boxes.PURCHASE_LINE_BOXES),
	):
		result[total_box].amount = total(result[p].amount for p in parts)
		result[total_box].adjustment = total(result[p].adjustment for p in parts)
		result[total_box].vat = total(result[p].vat for p in parts)
	result[boxes.VAT_DUE].vat = q2(result[boxes.SALES_TOTAL].vat - result[boxes.PURCHASES_TOTAL].vat)
	result[boxes.CORRECTIONS].vat = corrections
	result[boxes.VAT_CREDIT_CARRIED].vat = credit_carried
	result[boxes.NET_VAT].vat = q2(result[boxes.VAT_DUE].vat + corrections - credit_carried)
	return result


def _proof(lines, gl_rows, config) -> list[AccountProof]:
	gl = defaultdict(lambda: ZERO)
	for (_vt, _vn, account), vat in _gl_by_voucher(gl_rows, config).items():
		gl[account] += vat
	by_account = defaultdict(lambda: ZERO)
	for line in lines:
		if line.vat_account:
			by_account[line.vat_account] += line.vat
	proof = []
	for account in sorted(set(gl) | set(by_account)):
		side = Side.SALES if account in config.output_accounts else Side.PURCHASES
		proof.append(AccountProof(account, side, q2(gl[account]), q2(by_account[account])))
	return proof


def _assert_boxes_match_lines(result: VatResult) -> None:
	"""Every box equals the sum of its lines; totals equal the sum of their boxes."""
	for box_id in boxes.LINE_BOXES:
		placed = [line for line in result.lines if line.box == box_id]
		box = result.boxes[box_id]
		assert box.vat == total(line.vat for line in placed), box_id
		assert box.amount + box.adjustment == total(line.base for line in placed), box_id
	assert result.boxes[boxes.SALES_TOTAL].vat == total(result.boxes[b].vat for b in boxes.SALES_LINE_BOXES)
	assert result.boxes[boxes.PURCHASES_TOTAL].vat == total(
		result.boxes[b].vat for b in boxes.PURCHASE_LINE_BOXES
	)
