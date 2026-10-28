# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from frappe.model.document import Document

from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import refuse_standalone_save


class SaudiVATRuleFieldLabel(Document):
	def validate(self):
		refuse_standalone_save()
