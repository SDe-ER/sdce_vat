// Copyright (c) 2026, SDCE VAT Contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Import a shipped baseline rule file as a draft rule set; the server checks the role and keeps every rule Pending.

frappe.listview_settings["Saudi VAT Rule Set"] = {
	onload(listview) {
		if (!frappe.user.has_role("VAT Rule Maintainer")) {
			return;
		}
		listview.page.add_inner_button(__("Import Baseline Rules"), () =>
			frappe
				.call({ method: "sdce_vat.rules.baseline.list_baselines", type: "GET" })
				.then((r) => {
					const files = r.message || [];
					const dialog = new frappe.ui.Dialog({
						title: __("Import Baseline Rules"),
						fields: [
							{
								fieldname: "name",
								label: __("Baseline File"),
								fieldtype: "Select",
								reqd: 1,
								options: files.map((f) => ({
									value: f.name,
									label: `${f.rule_set_code} ${f.version} (${f.name})`,
								})),
							},
							{
								fieldname: "notice",
								fieldtype: "HTML",
								options: `<p class="text-muted">${__(
									"The rule set is created as a draft and every rule stays Pending until a verifier checks it against the official source."
								)}</p>`,
							},
						],
						primary_action_label: __("Import"),
						primary_action(values) {
							frappe
								.call({
									method: "sdce_vat.rules.baseline.import_baseline",
									args: { name: values.name },
									freeze: true,
								})
								.then((res) => {
									dialog.hide();
									frappe.set_route("Form", "Saudi VAT Rule Set", res.message);
								});
						},
					});
					dialog.show();
				})
		);
	},
};
