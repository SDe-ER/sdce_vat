// Copyright (c) 2026, SDCE VAT Contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Opened from the fields of the KSA VAT Return report; the lines come from the server.

frappe.query_reports["KSA VAT Return Detail"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1 },
		{
			fieldname: "field",
			label: __("Field"),
			fieldtype: "Select",
			options: [
				"",
				"S01",
				"S02",
				"S03",
				"S04",
				"S05",
				"S06",
				"P07",
				"P08",
				"P09",
				"P10",
				"P11",
				"P12",
				"T13",
				"T16",
			],
			depends_on: "eval:!doc.exceptions_only",
		},
		{ fieldname: "exceptions_only", label: __("Exceptions Only"), fieldtype: "Check" },
	],
};
