# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import frappe
from frappe import _
from frappe.model.document import Document

from sdce_vat.engine.config import NonDeductiblePlacement, VatConfig
from sdce_vat.engine.model import Treatment
from sdce_vat.engine.money import D

FAMILY_FIELD = {
	"Output": "output_accounts",
	"Input": "input_accounts",
	"Reverse Charge": "reverse_charge_accounts",
	"Customs": "customs_accounts",
}
NON_DEDUCTIBLE_PLACEMENT = {
	"Exclude": NonDeductiblePlacement.EXCLUDE,
	"Box 7 Without VAT": NonDeductiblePlacement.BOX_7_WITHOUT_VAT,
}


class SaudiVATSettings(Document):
	def validate(self):
		seen = set()
		for row in self.accounts:
			if row.account in seen:
				frappe.throw(_("Row {0}: account {1} is listed twice").format(row.idx, row.account))
			seen.add(row.account)
			if row.rate is None or row.rate < 0:
				frappe.throw(_("Row {0}: the rate cannot be negative").format(row.idx))
			company, account_type = frappe.db.get_value("Account", row.account, ["company", "account_type"])
			if company != self.company:
				frappe.throw(
					_("Row {0}: account {1} belongs to another company").format(row.idx, row.account)
				)
			if account_type != "Tax":
				frappe.throw(_("Row {0}: account {1} is not a Tax account").format(row.idx, row.account))
		categories = [r.category for r in self.category_rules]
		if len(categories) != len(set(categories)):
			frappe.throw(_("A category is listed twice in the category rules"))

	def to_config(self) -> VatConfig:
		config = VatConfig(
			company=self.company,
			category_treatments={r.category: Treatment(r.treatment) for r in self.category_rules},
			non_deductible_placement=NON_DEDUCTIBLE_PLACEMENT.get(self.non_deductible_placement or ""),
			tolerance=D(self.tolerance or "0.01"),
			include_expense_claims=bool(self.include_expense_claims),
		)
		for row in self.accounts:
			# the rate is stored as a float field; str() keeps the typed value (15 -> "15.0")
			getattr(config, FAMILY_FIELD[row.family])[row.account] = D(str(row.rate))
		config.validate()
		return config


def get_settings(company: str) -> SaudiVATSettings:
	if not frappe.db.exists("Saudi VAT Settings", company):
		frappe.throw(_("Create Saudi VAT Settings for {0} first").format(company))
	return frappe.get_doc("Saudi VAT Settings", company)
