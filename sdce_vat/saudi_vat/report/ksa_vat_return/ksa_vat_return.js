// Copyright (c) 2026, SDCE VAT Contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// All figures come from the server; this file only defines the filters, the links to the details and the
// Save Snapshot action.

frappe.query_reports["KSA VAT Return"] = {
	filters: sdce_vat_period_filters(),

	formatter(value, row, column, data, default_formatter) {
		const shown = default_formatter(value, row, column, data);
		if (!data || !["amount", "adjustment", "vat", "line_count"].includes(column.fieldname)) {
			return data && data.is_total ? `<b>${shown}</b>` : shown;
		}
		if (!data.line_count) {
			return data.is_total ? `<b>${shown}</b>` : shown;
		}
		const params = new URLSearchParams(
			sdce_vat_detail_filters(frappe.query_report, data, data.box_id)
		);
		const link = `<a href="/app/query-report/${encodeURIComponent(
			"KSA VAT Return Detail"
		)}?${params.toString()}">${shown}</a>`;
		return data.is_total ? `<b>${link}</b>` : link;
	},

	onload(report) {
		report.page.add_inner_button(__("Show Exceptions"), () => {
			const first = (report.data || [])[0];
			if (!first) {
				frappe.msgprint(__("Generate the report first."));
				return;
			}
			frappe.set_route(
				"query-report",
				"KSA VAT Return Detail",
				sdce_vat_detail_filters(report, first)
			);
		});
		report.page.add_inner_button(__("Save Snapshot"), () => {
			frappe.confirm(
				__(
					"Save a copy of this return as a draft Saudi VAT Return? Saving is not approval and not filing."
				),
				() =>
					frappe
						.call({
							method: "sdce_vat.saudi_vat.report.ksa_vat_return.ksa_vat_return.save_snapshot",
							args: { filters: report.get_values() },
							freeze: true,
						})
						.then(
							(r) =>
								r.message &&
								frappe.set_route("Form", "Saudi VAT Return", r.message)
						)
			);
		});
	},
};

// Filters of the detail report: the company and the resolved period of the generated report, and either
// one field or the exceptions.
function sdce_vat_detail_filters(report, row, field) {
	const values = report.get_values() || {};
	const filters = { company: values.company, from_date: row.from_date, to_date: row.to_date };
	if (field) {
		filters.field = field;
	} else {
		filters.exceptions_only = 1;
	}
	return filters;
}

function sdce_vat_period_filters() {
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const is = (kind) => `eval:doc.period_type=='${kind}'`;
	return [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "period_type",
			label: __("Period Type"),
			fieldtype: "Select",
			options: [
				{ value: "Monthly", label: __("Monthly") },
				{ value: "Quarterly", label: __("Quarterly") },
				{ value: "Custom", label: __("Custom") },
			],
			default: "Quarterly",
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Int",
			default: today.getFullYear(),
			depends_on: "eval:doc.period_type!='Custom'",
		},
		{
			fieldname: "quarter",
			label: __("Quarter"),
			fieldtype: "Select",
			options: ["Q1", "Q2", "Q3", "Q4"],
			default: `Q${Math.floor(today.getMonth() / 3) + 1}`,
			depends_on: is("Quarterly"),
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: Array.from({ length: 12 }, (_, i) => ({
				value: String(i + 1),
				label: String(i + 1),
			})),
			default: String(today.getMonth() + 1),
			depends_on: is("Monthly"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			depends_on: is("Custom"),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			depends_on: is("Custom"),
		},
		{
			fieldname: "tax_basis",
			label: __("Tax Basis"),
			fieldtype: "Select",
			options: [{ value: "Accrual", label: __("Accrual") }],
			default: "Accrual",
			read_only: 1,
		},
		{
			fieldname: "corrections",
			label: __("Corrections from Previous Periods (VAT)"),
			fieldtype: "Currency",
		},
		{
			fieldname: "credit_carried",
			label: __("VAT Credit from Previous Periods"),
			fieldtype: "Currency",
		},
	];
}
