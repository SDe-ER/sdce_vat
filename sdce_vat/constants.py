# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

MODULE = "Saudi VAT"

# Separate duties: the preparer computes, the reviewer checks, the approver approves.
VAT_PREPARER = "VAT Preparer"
VAT_REVIEWER = "VAT Reviewer"
VAT_APPROVER = "VAT Approver"
# Tax rule sets: a maintainer prepares, a second person verifies, an approver publishes (three different users).
VAT_RULE_MAINTAINER = "VAT Rule Maintainer"
VAT_ROLES = (VAT_PREPARER, VAT_REVIEWER, VAT_APPROVER, VAT_RULE_MAINTAINER)

# Closed list of rule keys. A key is either one of RULE_KEYS or `<prefix>:<name>` with a prefix of RULE_KEY_PREFIXES.
RULE_KEYS = (
	"standard_rate",
	"non_recoverable_placement",
	"credit_note_period",
	"rounding",
	"late_claim_limit_years",
	"late_claim_limit_basis",
	"unpaid_adjust_months",
	"unpaid_adjust_start",
	"unpaid_financing_exception",
	"correction_rules",
	"correction_limit",
	"correction_limit_basis",
	"correction_limit_measure",
)
RULE_KEY_PREFIXES = ("treatment_box", "recoverability", "tax_date_basis")
DECIMAL_RULE_KEYS = ("standard_rate",)
WHOLE_NUMBER_RULE_KEYS = ("late_claim_limit_years", "unpaid_adjust_months")
AMOUNT_RULE_KEYS = ("correction_limit",)  # amounts in SAR
# Candidate readings of IR Art. 63 the app can apply; the verifier chooses one per rule set.
CORRECTION_LIMIT_BASES = ("original_period_end", "correcting_return_end")
CORRECTION_LIMIT_MEASURES = ("net_total", "per_line", "absolute_total")
