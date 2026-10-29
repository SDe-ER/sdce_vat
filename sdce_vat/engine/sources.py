# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Read the VAT-relevant documents of a company and period from the site. SELECT queries only."""

from collections import defaultdict

import frappe
from frappe.query_builder.functions import Sum

from sdce_vat.engine.config import VatConfig
from sdce_vat.engine.model import GLRow, SourceLine
from sdce_vat.engine.money import D
from sdce_vat.engine.rows import expense_claim_lines, invoice_lines, journal_lines

ZATCA_ITEM_FIELD = (
	"custom_zatca_item_tax_category"  # ksa_compliance, on Sales Invoice Item and Item Tax Template
)
ZATCA_CATEGORY_FIELD = "custom_zatca_category"  # ksa_compliance, on Tax Category


def read_lines(config: VatConfig, from_date: str, to_date: str) -> list[SourceLine]:
	lines = []
	lines += _invoices("Sales Invoice", config, from_date, to_date)
	lines += _invoices("Purchase Invoice", config, from_date, to_date)
	lines += _journal_entries(config, from_date, to_date)
	if config.include_expense_claims and "hrms" in frappe.get_installed_apps():
		lines += _expense_claims(config, from_date, to_date)
	return lines


def read_gl(config: VatConfig, from_date: str, to_date: str) -> list[GLRow]:
	if not config.vat_accounts:
		return []
	gle = frappe.qb.DocType("GL Entry")
	rows = (
		frappe.qb.from_(gle)
		.select(gle.voucher_type, gle.voucher_no, gle.account, (Sum(gle.debit) - Sum(gle.credit)).as_("net"))
		.where(
			(gle.company == config.company)
			& (gle.is_cancelled == 0)
			& (gle.posting_date >= from_date)
			& (gle.posting_date <= to_date)
			& (gle.account.isin(list(config.vat_accounts)))
		)
		.groupby(gle.voucher_type, gle.voucher_no, gle.account)
		.run(as_dict=True)
	)
	return [GLRow(r.voucher_type, r.voucher_no, r.account, D(r.net)) for r in rows]


def _submitted(doctype, config, from_date, to_date, fields):
	return frappe.get_all(
		doctype,
		filters={
			"company": config.company,
			"docstatus": 1,
			"posting_date": ["between", [from_date, to_date]],
		},
		fields=fields,
		order_by="posting_date asc, name asc",
	)


def _children(doctype, parenttype, parents, fields):
	by_parent = defaultdict(list)
	if parents:
		for row in frappe.get_all(
			doctype,
			filters={"parenttype": parenttype, "parent": ["in", parents]},
			fields=["parent", *fields],
			order_by="idx asc",
		):
			by_parent[row.parent].append(row)
	return by_parent


def _has_field(doctype, fieldname) -> bool:
	return frappe.get_meta(doctype).has_field(fieldname)


def _invoices(doctype, config, from_date, to_date) -> list[SourceLine]:
	is_sales = doctype == "Sales Invoice"
	fields = [
		"name",
		"posting_date",
		"company",
		"customer" if is_sales else "supplier",
		"tax_id",
		"is_return",
		"return_against",
		"tax_category",
		"base_net_total",
	]
	if is_sales:
		fields.append("is_debit_note")
	else:
		fields += ["bill_no", "bill_date"]
	docs = _submitted(doctype, config, from_date, to_date, fields)
	names = [d.name for d in docs]
	tax_doctype = "Sales Taxes and Charges" if is_sales else "Purchase Taxes and Charges"
	tax_fields = ["name", "account_head", "base_tax_amount_after_discount_amount"]
	if not is_sales:
		tax_fields.append("add_deduct_tax")
	taxes = _children(tax_doctype, doctype, names, tax_fields)
	item_tax = _children("Item Wise Tax Detail", doctype, names, ["tax_row", "taxable_amount"])
	item_doctype = f"{doctype} Item"
	item_fields = ["item_tax_template"]
	if _has_field(item_doctype, ZATCA_ITEM_FIELD):
		item_fields.append(ZATCA_ITEM_FIELD)
	items = _children(item_doctype, doctype, names, item_fields)
	party_tax_ids = _party_tax_ids("Customer" if is_sales else "Supplier", docs)
	template_categories = _template_zatca_categories()
	tax_category_zatca = _tax_category_zatca()

	lines = []
	for doc in docs:
		doc_items = items.get(doc.name, [])
		templates = tuple(i.item_tax_template for i in doc_items if i.item_tax_template)
		zatca = {i.get(ZATCA_ITEM_FIELD) for i in doc_items if i.get(ZATCA_ITEM_FIELD)}
		zatca |= {template_categories[t] for t in templates if t in template_categories}
		if doc.tax_category in tax_category_zatca:
			zatca.add(tax_category_zatca[doc.tax_category])
		party = doc.customer if is_sales else doc.supplier
		lines += invoice_lines(
			doctype,
			doc,
			taxes.get(doc.name, []),
			item_tax.get(doc.name, []),
			config,
			party_tax_id=doc.tax_id or party_tax_ids.get(party),
			item_tax_templates=templates,
			zatca_categories=tuple(zatca),
		)
	return lines


def _journal_entries(config, from_date, to_date) -> list[SourceLine]:
	jea = frappe.qb.DocType("Journal Entry Account")
	je = frappe.qb.DocType("Journal Entry")
	names = [
		r[0]
		for r in frappe.qb.from_(jea)
		.join(je)
		.on(je.name == jea.parent)
		.select(je.name)
		.distinct()
		.where(
			(je.company == config.company)
			& (je.docstatus == 1)
			& (je.posting_date >= from_date)
			& (je.posting_date <= to_date)
			& (jea.account.isin(list(config.vat_accounts)))
		)
		.run()
	]
	if not names:
		return []
	docs = frappe.get_all(
		"Journal Entry",
		filters={"name": ["in", names]},
		fields=["name", "posting_date", "company", "bill_no", "bill_date", "cheque_no"],
		order_by="posting_date asc, name asc",
	)
	accounts = _children(
		"Journal Entry Account",
		"Journal Entry",
		names,
		["name", "account", "debit", "credit", "party_type", "party"],
	)
	parties = {(a.party_type, a.party) for rows in accounts.values() for a in rows if a.party}
	party_tax_ids = {}
	for party_type in {p[0] for p in parties}:
		ids = _party_tax_ids(party_type, [{"party": p[1]} for p in parties if p[0] == party_type], "party")
		party_tax_ids.update({(party_type, k): v for k, v in ids.items()})
	lines = []
	for doc in docs:
		lines += journal_lines(doc, accounts.get(doc.name, []), config, party_tax_ids)
	return lines


def _expense_claims(config, from_date, to_date) -> list[SourceLine]:
	docs = _submitted(
		"Expense Claim",
		config,
		from_date,
		to_date,
		["name", "posting_date", "company", "employee", "total_sanctioned_amount"],
	)
	taxes = _children(
		"Expense Taxes and Charges",
		"Expense Claim",
		[d.name for d in docs],
		["name", "account_head", "base_tax_amount"],
	)
	lines = []
	for doc in docs:
		lines += expense_claim_lines(doc, taxes.get(doc.name, []), config)
	return lines


def _party_tax_ids(party_type, docs, field=None) -> dict:
	if party_type not in ("Supplier", "Customer"):
		return {}
	field = field or party_type.lower()
	names = sorted({d[field] for d in docs if d.get(field)})
	if not names:
		return {}
	return dict(
		frappe.get_all(party_type, filters={"name": ["in", names]}, fields=["name", "tax_id"], as_list=True)
	)


def _template_zatca_categories() -> dict:
	if not _has_field("Item Tax Template", ZATCA_ITEM_FIELD):
		return {}
	return dict(
		frappe.get_all(
			"Item Tax Template",
			filters={ZATCA_ITEM_FIELD: ["is", "set"]},
			fields=["name", ZATCA_ITEM_FIELD],
			as_list=True,
		)
	)


def _tax_category_zatca() -> dict:
	if not _has_field("Tax Category", ZATCA_CATEGORY_FIELD):
		return {}
	return dict(
		frappe.get_all(
			"Tax Category",
			filters={ZATCA_CATEGORY_FIELD: ["is", "set"]},
			fields=["name", ZATCA_CATEGORY_FIELD],
			as_list=True,
		)
	)
