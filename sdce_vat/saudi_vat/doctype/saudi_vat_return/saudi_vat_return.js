// Copyright (c) 2026, SDCE VAT Contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// The form only calls server methods; all calculation and checks run on the server.

frappe.ui.form.on("Saudi VAT Return", {
	refresh(frm) {
		if (
			frm.doc.docstatus === 0 &&
			!frm.is_new() &&
			(frm.doc.workflow_state || "VAT Draft") === "VAT Draft"
		) {
			frm.add_custom_button(__("Calculate"), () =>
				frm
					.call({ doc: frm.doc, method: "calculate", freeze: true })
					.then(() => frm.reload_doc())
			);
		}
		if (!frm.is_new() && frm.doc.calculation_hash) {
			frm.add_custom_button(
				__("Check for Changes"),
				() =>
					frm.call({ doc: frm.doc, method: "check_drift", type: "GET" }).then((r) => {
						const result = r.message || {};
						frappe.msgprint(
							result.unchanged
								? __("The documents of the period still give the stored values.")
								: __("{0} sources changed since the calculation.", [
										(result.changed_sources || []).length,
								  ])
						);
					}),
				__("Checks")
			);
		}
		if (frm.doc.docstatus === 1 && frm.doc.snapshot_hash) {
			frm.add_custom_button(
				__("Verify Snapshot"),
				() =>
					frm
						.call({ doc: frm.doc, method: "verify_snapshot", type: "GET" })
						.then((r) => {
							const result = r.message || {};
							frappe.msgprint(
								result.file_ok && result.tables_ok
									? __("The snapshot matches the approved values.")
									: __("The snapshot does not match the approved values.")
							);
						}),
				__("Checks")
			);
		}
		if (frm.doc.review_count) {
			frm.dashboard.set_headline_alert(
				__("{0} sources need review; approval is blocked.", [frm.doc.review_count]),
				"red"
			);
		}
	},
});
