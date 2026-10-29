# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Install steps that are not DocType content."""

import frappe

REPORT = "KSA VAT Return"
SIDEBAR_MODULE = "Accounts"


def after_install():
	add_report_to_accounts_sidebar()


def add_report_to_accounts_sidebar():
	"""Show the KSA VAT Return under the Accounts sidebar, next to the other accounting reports.

	The Accounts sidebar belongs to ERPNext, so the entry goes to the site layer through Frappe's own API, which
	skips an entry that is already there. Sites on a Frappe without that API keep the report in the Saudi VAT
	module.
	"""
	try:
		from frappe.desk.doctype.custom_sidebar.custom_sidebar import add_site_sidebar_item
	except ImportError:
		return
	if not frappe.db.exists("Report", REPORT) or not frappe.db.exists("Module Def", SIDEBAR_MODULE):
		return
	add_site_sidebar_item(
		SIDEBAR_MODULE,
		{"type": "Link", "link_type": "Report", "link_to": REPORT, "label": REPORT, "child": 1},
	)
