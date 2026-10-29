# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""KSA VAT Return reports: periods, figures against the saved return and the ledger, details, exceptions,
permissions, Save Snapshot and the Accounts sidebar entry. Synthetic data only."""

from datetime import date
from decimal import Decimal

import frappe
from frappe.model.workflow import apply_workflow

from sdce_vat.constants import VAT_APPROVER, VAT_PREPARER, VAT_REVIEWER
from sdce_vat.engine import boxes
from sdce_vat.saudi_vat.report.ksa_vat_return import ksa_vat_return
from sdce_vat.saudi_vat.report.ksa_vat_return_detail import ksa_vat_return_detail
from sdce_vat.saudi_vat.vat_report import box_label, period
from sdce_vat.tests.site_base import (
	COMPANY,
	DATE,
	FROM,
	TO,
	VatSiteTestCase,
	make_other_company_tax_account,
	make_user,
)

PREPARER = "vat-report-preparer@example.com"
REVIEWER = "vat-report-reviewer@example.com"
APPROVER = "vat-report-approver@example.com"
AUDITOR = "vat-report-auditor@example.com"
NO_ROLE = "vat-report-no-role@example.com"
FILTERS = {"company": COMPANY, "period_type": "Quarterly", "year": 2026, "quarter": "Q3"}


def report(filters=None):
	_columns, data, message, _chart, summary = ksa_vat_return.execute(dict(filters or FILTERS))
	return {row["box_id"]: row for row in data}, message, {s["label"]: s["value"] for s in summary}


def detail(**filters):
	_columns, rows = ksa_vat_return_detail.execute(
		{"company": COMPANY, "from_date": FROM, "to_date": TO, **filters}
	)
	return rows


def total(rows, field):
	return sum((Decimal(str(row[field])) for row in rows), Decimal(0))


class TestVatReport(VatSiteTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.make_settings()
		make_user(PREPARER, VAT_PREPARER)
		make_user(REVIEWER, VAT_REVIEWER)
		make_user(APPROVER, VAT_APPROVER)
		make_user(AUDITOR, "Auditor")
		make_user(NO_ROLE)

	def setUp(self):
		frappe.db.savepoint("vat_report_test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.lang = "en"
		frappe.db.rollback(save_point="vat_report_test")

	# ---- periods ------------------------------------------------------------------------------------------
	def test_periods(self):
		self.assertEqual(
			period({"period_type": "Monthly", "year": 2028, "month": 2}),
			(date(2028, 2, 1), date(2028, 2, 29)),
		)
		self.assertEqual(
			period({"period_type": "Quarterly", "year": 2026, "quarter": "Q4"}),
			(date(2026, 10, 1), date(2026, 12, 31)),
		)
		self.assertEqual(
			period({"period_type": "Custom", "from_date": "2026-07-05", "to_date": "2026-07-20"}),
			(date(2026, 7, 5), date(2026, 7, 20)),
		)
		for bad in (
			{"period_type": "Monthly", "year": 2026, "month": 13},
			{"period_type": "Quarterly", "year": 2026, "quarter": "Q5"},
			{"period_type": "Custom", "from_date": "2026-07-05"},
			{"period_type": "Custom", "from_date": "2026-08-01", "to_date": "2026-07-01"},
			{"period_type": "Weekly", "year": 2026},
		):
			self.assertRaises(frappe.ValidationError, period, bad)

	def test_only_the_accrual_basis(self):
		self.assertRaises(frappe.ValidationError, report, {**FILTERS, "tax_basis": "Cash"})

	# ---- figures --------------------------------------------------------------------------------------------
	def test_report_equals_the_calculated_return(self):
		fields, _message, summary = report()
		frappe.set_user(PREPARER)
		doc = frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": FROM, "to_date": TO}
		).insert()
		doc.calculate()
		for line in frappe.get_doc("Saudi VAT Return", doc.name).lines:
			row = fields[line.box_id]
			self.assertEqual(
				(Decimal(str(row["amount"])), Decimal(str(row["adjustment"])), Decimal(str(row["vat"]))),
				(Decimal(str(line.amount)), Decimal(str(line.adjustment)), Decimal(str(line.vat))),
				line.box_id,
			)
		self.assertEqual(Decimal(str(summary["Net VAT"])), Decimal(str(doc.net_vat)))

	def test_every_field_equals_its_details(self):
		fields, _message, _summary = report()
		for box_id in (*boxes.LINE_BOXES, boxes.SALES_TOTAL, boxes.PURCHASES_TOTAL):
			rows = detail(field=box_id)
			row = fields[box_id]
			self.assertEqual(len(rows), row["line_count"], box_id)
			self.assertEqual(
				total(rows, "base"), Decimal(str(row["amount"])) + Decimal(str(row["adjustment"]))
			)
			self.assertEqual(total(rows, "vat"), Decimal(str(row["vat"])), box_id)
		sales = total(detail(field=boxes.SALES_TOTAL), "vat")
		purchases = total(detail(field=boxes.PURCHASES_TOTAL), "vat")
		self.assertEqual(Decimal(str(fields[boxes.VAT_DUE]["vat"])), sales - purchases)
		self.assertEqual(fields[boxes.VAT_DUE]["line_count"], len(detail(field=boxes.VAT_DUE)))

	def test_details_point_to_the_source_documents(self):
		vouchers = {
			(row["voucher_type"], row["voucher_no"]) for row in detail(field=boxes.PURCHASES_STANDARD)
		}
		self.assertIn(("Purchase Invoice", self.pi.name), vouchers)
		self.assertNotIn(("Purchase Invoice", self.pi_cancelled.name), vouchers)
		self.assertIn(
			("Sales Invoice", self.si.name),
			{(r["voucher_type"], r["voucher_no"]) for r in detail(field="S01")},
		)

	def test_generating_writes_nothing(self):
		returns = frappe.db.count("Saudi VAT Return")
		writes = frappe.db.transaction_writes
		report()
		detail(field=boxes.SALES_STANDARD)
		detail(exceptions_only=1)
		self.assertEqual(frappe.db.transaction_writes, writes)
		self.assertEqual(frappe.db.count("Saudi VAT Return"), returns)

	def test_exceptions_are_shown_not_guessed(self):
		_fields, message, summary = report()  # the purchase invoice without VAT is not classified
		self.assertIn("Not approvable", message)
		self.assertEqual(summary["Status"], "Not approvable")
		self.assertGreaterEqual(summary["Sources Needing Review"], 1)
		exceptions = detail(exceptions_only=1)
		self.assertIn(self.pi_no_vat.name, {row["voucher_no"] for row in exceptions})
		self.assertTrue(all(row["box_no"] is None for row in exceptions))
		frappe.get_doc("Purchase Invoice", self.pi_no_vat.name).cancel()
		_fields, message, summary = report()
		self.assertIsNone(message)
		self.assertEqual(summary["Status"], "Ready for review")

	def test_vat_reversed_by_a_journal_correction_matches_the_ledger(self):
		"""The 398.04 case, synthetic: VAT booked on a purchase invoice and reversed by a journal entry. The field,
		its details and the ledger must agree; the old report dropped the negative correction from its annex."""
		before, _message, _summary = report()
		invoice = self._invoice("Purchase Invoice", 2653.60, self.vat_in)  # VAT 398.04
		journal = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": COMPANY,
				"posting_date": DATE,
				"cheque_no": invoice.bill_no,
				"cheque_date": DATE,
				"accounts": [
					{"account": self.expense, "debit_in_account_currency": 398.04},
					{"account": self.vat_in, "credit_in_account_currency": 398.04},
				],
			}
		).insert(ignore_permissions=True)
		journal.submit()
		fields, _message, summary = report()
		self.assertEqual(summary["Reconciled with General Ledger"], "Yes")
		ledger = frappe.db.sql(
			"""select coalesce(sum(debit - credit), 0) from `tabGL Entry`
			where account = %s and is_cancelled = 0 and posting_date between %s and %s""",
			(self.vat_in, FROM, TO),
		)[0][0]
		purchases = fields[boxes.PURCHASES_TOTAL]
		self.assertEqual(Decimal(str(purchases["vat"])), Decimal(str(ledger)))
		self.assertEqual(Decimal(str(purchases["vat"])), Decimal(str(before[boxes.PURCHASES_TOTAL]["vat"])))
		rows = [
			r for r in detail(field=boxes.PURCHASES_TOTAL) if r["voucher_no"] in (invoice.name, journal.name)
		]
		self.assertEqual({r["voucher_no"] for r in rows}, {invoice.name, journal.name})
		self.assertEqual(total(rows, "vat"), Decimal(0))
		self.assertEqual(total(detail(field=boxes.PURCHASES_TOTAL), "vat"), Decimal(str(purchases["vat"])))

	def test_filters_must_be_plain_values(self):
		self.assertRaises(frappe.ValidationError, report, {**FILTERS, "company": ["!=", ""]})
		rows = detail(field=boxes.SALES_STANDARD, exceptions_only="0")
		self.assertTrue(rows)
		self.assertTrue(all(row["box_no"] == 1 for row in rows))

	def test_box_labels_follow_the_user_language(self):
		box = boxes.BOX_BY_ID[boxes.NET_VAT]
		frappe.local.lang = "ar"
		self.assertEqual(box_label(box), box.label_ar)
		frappe.local.lang = "en"
		self.assertEqual(box_label(box), box.label_en)

	# ---- permissions ------------------------------------------------------------------------------------
	def test_user_without_roles_is_denied(self):
		frappe.set_user(NO_ROLE)
		self.assertRaises(frappe.PermissionError, report)

	def test_user_of_another_company_is_denied(self):
		other = frappe.get_all("Company", filters={"name": ["!=", COMPANY]}, pluck="name", limit=1)
		if not other:
			other = [frappe.db.get_value("Account", make_other_company_tax_account(), "company")]
		email = make_user("vat-report-other-company@example.com", "Auditor", VAT_PREPARER)
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Company", "for_value": other[0]}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		self.assertRaises(frappe.PermissionError, report)
		self.assertRaises(frappe.PermissionError, ksa_vat_return.save_snapshot, FILTERS)

	def test_auditor_reads_but_cannot_save(self):
		frappe.set_user(AUDITOR)
		report()
		self.assertRaises(frappe.PermissionError, ksa_vat_return.save_snapshot, FILTERS)

	# ---- Save Snapshot ------------------------------------------------------------------------------------
	def test_save_snapshot_creates_the_draft_and_reuses_it(self):
		frappe.set_user(PREPARER)
		name = ksa_vat_return.save_snapshot(FILTERS)
		doc = frappe.get_doc("Saudi VAT Return", name)
		self.assertEqual((str(doc.from_date), str(doc.to_date)), (FROM, TO))
		self.assertTrue(doc.calculation_hash)
		self.assertEqual(doc.workflow_state, "VAT Draft")
		self.assertEqual(ksa_vat_return.save_snapshot(FILTERS), name)
		self.assertEqual(frappe.db.count("Saudi VAT Return", {"company": COMPANY}), 1)

	def test_saved_snapshot_does_not_follow_later_documents(self):
		frappe.set_user(PREPARER)
		doc = frappe.get_doc("Saudi VAT Return", ksa_vat_return.save_snapshot(FILTERS))
		stored = {line.box_id: line.vat for line in doc.lines}
		frappe.set_user("Administrator")
		self._invoice("Purchase Invoice", 100, self.vat_in)
		fields, _message, _summary = report()
		self.assertNotEqual(
			Decimal(str(fields[boxes.PURCHASES_STANDARD]["vat"])), Decimal(str(stored["P07"]))
		)
		saved = frappe.get_doc("Saudi VAT Return", doc.name)
		self.assertEqual({line.box_id: line.vat for line in saved.lines}, stored)
		self.assertEqual(saved.calculation_hash, doc.calculation_hash)
		self.assertFalse(saved.check_drift()["unchanged"])

	def test_approved_period_is_refused(self):
		frappe.get_doc(
			"Purchase Invoice", self.pi_no_vat.name
		).cancel()  # approval needs a period without unresolved sources
		frappe.set_user(PREPARER)
		name = ksa_vat_return.save_snapshot(FILTERS)
		for user, action in (
			(PREPARER, "Prepare VAT Return"),
			(REVIEWER, "Review VAT Return"),
			(APPROVER, "Approve VAT Return"),
		):
			frappe.set_user(user)
			apply_workflow(frappe.get_doc("Saudi VAT Return", name), action)
		frappe.set_user(PREPARER)
		self.assertRaises(frappe.ValidationError, ksa_vat_return.save_snapshot, FILTERS)
		self.assertEqual(frappe.db.count("Saudi VAT Return", {"company": COMPANY}), 1)

	def test_return_over_part_of_the_period_is_refused(self):
		frappe.set_user(PREPARER)
		frappe.get_doc(
			{"doctype": "Saudi VAT Return", "company": COMPANY, "from_date": FROM, "to_date": "2026-07-31"}
		).insert()
		self.assertRaises(frappe.ValidationError, ksa_vat_return.save_snapshot, FILTERS)

	def test_save_snapshot_refuses_filter_lists(self):
		frappe.set_user(PREPARER)
		self.assertRaises(frappe.ValidationError, ksa_vat_return.save_snapshot, [["company", "=", COMPANY]])
		self.assertRaises(
			frappe.ValidationError, ksa_vat_return.save_snapshot, {**FILTERS, "company": ["!=", ""]}
		)

	# ---- sidebar ----------------------------------------------------------------------------------------------
	def test_report_is_listed_once_after_accounts_payable(self):
		if not frappe.db.exists("DocType", "Custom Sidebar"):
			self.skipTest("this Frappe has no site sidebar layers")
		from frappe.desk.doctype.custom_sidebar.custom_sidebar import get_customization

		from sdce_vat.install import REPORT, add_report_to_accounts_sidebar

		add_report_to_accounts_sidebar()
		add_report_to_accounts_sidebar()
		layer = frappe.get_doc("Custom Sidebar", get_customization("Accounts", None).name)
		links = [(row.link_type, row.link_to) for row in layer.sidebar_items]
		self.assertEqual(links.count(("Report", REPORT)), 1)
		position = links.index(("Report", REPORT))
		if ("Report", "Accounts Payable") in links:
			self.assertEqual(links[position - 1], ("Report", "Accounts Payable"))

	def test_sidebar_keeps_the_labels_of_site_items(self):
		if not frappe.db.exists("DocType", "Custom Sidebar"):
			self.skipTest("this Frappe has no site sidebar layers")
		from frappe.desk.doctype.custom_sidebar.custom_sidebar import add_site_sidebar_item, get_customization

		from sdce_vat.install import add_report_to_accounts_sidebar

		layer = get_customization("Accounts", None)
		if layer:
			frappe.delete_doc("Custom Sidebar", layer.name, ignore_permissions=True, force=True)
		add_site_sidebar_item(
			"Accounts",
			{
				"type": "Link",
				"link_type": "Report",
				"link_to": "General Ledger",
				"label": "Sales Invoice",
				"child": 1,
			},
		)
		frappe.local.lang = "ar"  # "Sales Invoice" has an Arabic translation; it must not be stored
		frappe.clear_cache()
		add_report_to_accounts_sidebar()
		layer = frappe.get_doc("Custom Sidebar", get_customization("Accounts", None).name)
		labels = [row.label for row in layer.sidebar_items if row.added and row.link_to == "General Ledger"]
		self.assertEqual(labels, ["Sales Invoice"])
