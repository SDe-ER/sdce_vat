# Implementation status

Status: **pre-release, not for production use**. Not affiliated with, endorsed by, or certified by ZATCA.
No automatic filing, journal posting, invoice change or period lock is done by this app.

This file lists what the imported code does, how it maps to the requirements in
[INSTALLATION_REQUIREMENTS](INSTALLATION_REQUIREMENTS.md) and [ZATCA_REQUIREMENTS](ZATCA_REQUIREMENTS.md)
(proposed in a separate pull request), and what is still open.

## What is implemented
- Frappe v16 app `sdce_vat`, module **Saudi VAT**, `required_apps = ["erpnext"]`.
- Roles **VAT Preparer**, **VAT Reviewer**, **VAT Approver**, **VAT Rule Maintainer** and the workflows
  **Saudi VAT Return Approval** and **Saudi VAT Rule Set Approval** (fixtures).
- Versioned tax rule sets (DocType Saudi VAT Rule Set, see [DOCTYPES](DOCTYPES.md)): references, closed rule keys,
  Arabic and English field labels, three-user prepare / verify / publish, immutable and hashed after
  publication, normal and corrective versions. The engine does not read rule sets yet.
- Calculation engine (`sdce_vat/engine`, see [ENGINE](ENGINE.md)): Decimal arithmetic, stable field ids
  `S01`–`S06`, `P07`–`P12`, `T13`–`T16`, source lines from Sales/Purchase Invoices (returns, debit notes),
  Journal Entries and Expense Claims (only when HRMS is installed), GL reconciliation per VAT account,
  duplicate flags, read-only guard.
- DocTypes (see [DOCTYPES](DOCTYPES.md)): Saudi VAT Settings (per company), Saudi VAT Return, Saudi VAT Filing,
  Saudi VAT Amendment and their child tables. Calculated, internally approved and filed values are separate
  records. Approval writes a hashed JSON snapshot; drift and snapshot checks are read-only.
- Optional integrations: ksa_compliance category fields are read by field name only when present (no code import);
  HRMS Expense Claims are read only when HRMS is installed.
- No account, rate, company, VAT number or period is hard-coded. Every value comes from Saudi VAT Settings of the
  company.

## Tests
- `sdce_vat/tests/test_engine_core.py`: pure engine tests (no database).
- `sdce_vat/tests/test_rule_set.py`: rule-set separation of duties, immutability, overlap, corrective versions and
  permissions (synthetic references only).
- `sdce_vat/tests/test_engine_site.py`, `test_vat_return.py`, `test_security.py`, `test_app_setup.py`: site tests
  with synthetic companies (`_Test VAT Co`, `_Test VAT Co B`) and synthetic VAT numbers. All test data is rolled
  back.
- Security tests cover: API submit of a draft, `frappe.client.set_value` on calculated and approval fields, direct
  workflow state change, input change after preparation, update of an approved return, users without a VAT role,
  role separation, and two-company isolation (read, list, calculate, create, foreign accounts in settings).

## Known differences from the proposed requirements
| Requirement | Current behaviour | Planned change |
|---|---|---|
| Never infer recoverability from a VAT posting (INST §3, Z-04) | VAT posted to a configured input account is treated as deductible (field 7), with warnings | Separate *claimed* input VAT from a recoverability status (Unverified / Recoverable / Non-recoverable) per line; unverified lines block approval when the company policy says so |
| Versioned rule sets with source, dates and verification state (ZATCA release rule) | Rule sets can be prepared, verified and published (#4); the engine still uses its constants, the ±5,000 SAR correction limit is still a constant | Engine and return read the published rule set by tax date; the snapshot stores the rule sets used; impact report and "correction available" flag for corrective versions; baseline rule file (all Pending) |
| VAT registration profile and period calendar (Z-01, Z-02) | VAT number from Company; free period dates with an overlap check | Profile per company: VAT number check, filing frequency, first period, period validation |
| Onboarding wizard and preflight (INST §4) | Not built | Setup wizard and a read-only readiness check; the first return is blocked while a check fails |
| Mixed-use / partial exemption (INST §3) | Not supported | Versioned apportionment rule per company and period, manual until verified |
| Journal Entries only when eligible (ARCHITECTURE: "approved JE categories") | Every JE on a mapped VAT account is read, with a review warning on input claims | Eligibility rule (category or reviewer confirmation) |
| Other sources | POS Invoice, Payment Entry taxes and Landed Cost taxes are not read; their GL VAT shows as `unmatched_gl` for review | Readers for these sources |
| Optional app version checks (INST §1) | Presence of ksa_compliance fields is checked, not the app version | Version check in the readiness check |
| Multi-currency (COMPATIBILITY_MATRIX) | Base-currency amounts are used; no foreign-currency tests | Tests with foreign-currency invoices |
| CI matrix and secret scanning (RELEASE_CRITERIA) | CI runs with ERPNext only; Linters run pre-commit, Semgrep and pip-audit; this PR adds a gitleaks job | Matrix with and without ksa_compliance and HRMS; uninstall and reinstall test |
| Arabic-first UI, print, PDF and Excel (INST §4–5) | Minimal form buttons only | Separate phase after design approval |

Treatments whose reporting rule is not configured (for example input VAT that is not deductible) stay out of
every field and block approval. The app never guesses a tax rule.
