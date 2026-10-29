# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Install steps that are not DocType content."""

import frappe

REPORT = "KSA VAT Return"
SIDEBAR_MODULE = "Accounts"
PLACE_AFTER = "Accounts Payable"  # the last report of the Reports section of the ERPNext v16 Accounts sidebar


def after_install():
	add_report_to_accounts_sidebar()


def add_report_to_accounts_sidebar():
	"""Show the KSA VAT Return in the Reports section of the Accounts sidebar, after Accounts Payable.

	The Accounts sidebar belongs to ERPNext, so the entry goes to the site layer. A layer that only appends
	puts its rows at the end of the sidebar, so the site's current arrangement is saved with the entry in
	place, the same way the sidebar editor saves it (references to the existing items, one added item).

	Once the entry is part of an arrangement, the site decides: it is never moved or shown again. Sites on a
	Frappe without site sidebar layers keep the report in the Saudi VAT module.
	"""
	try:
		from frappe.desk.doctype.custom_sidebar import custom_sidebar as layers
	except ImportError:
		return
	if not frappe.db.exists("Report", REPORT) or not frappe.db.exists("Module Def", SIDEBAR_MODULE):
		return

	site_layer = layers.get_customization(SIDEBAR_MODULE, None)
	rows = frappe.get_doc("Custom Sidebar", site_layer.name).sidebar_items if site_layer else []
	if any(_is_entry(row) for row in rows) and any(not row.added for row in rows):
		return

	resolved, hidden = layers.resolve_arrangement(
		layers.base_items(SIDEBAR_MODULE), layers.get_layers(SIDEBAR_MODULE, None)
	)
	# resolved added rows carry their label translated for this session; save the stored label instead, so
	# re-saving the layer does not freeze another language into the site's own items
	stored_labels = {layers.item_key(row): row.label for row in rows if row.added}
	arrangement = [
		{
			**item,
			"hidden": int(hidden.get(layers.item_key(item)) or 0),
			**(
				{"label": stored_labels.get(layers.item_key(item), item.get("label"))}
				if item.get("added")
				else {}
			),
		}
		for item in resolved
		if not _is_entry(item)
	]
	arrangement.insert(
		_position(arrangement),
		{
			"type": "Link",
			"link_type": "Report",
			"link_to": REPORT,
			"label": REPORT,
			"child": 1,
			"added": 1,
		},
	)
	layers.save_site_sidebar(SIDEBAR_MODULE, arrangement)


def _is_entry(item) -> bool:
	return item.get("link_type") == "Report" and item.get("link_to") == REPORT


def _position(arrangement: list[dict]) -> int:
	"""After Accounts Payable; else after the last report link; else at the end."""
	reports = [i for i, item in enumerate(arrangement) if item.get("link_type") == "Report"]
	for i in reports:
		if arrangement[i].get("link_to") == PLACE_AFTER:
			return i + 1
	return reports[-1] + 1 if reports else len(arrangement)
