# Installation and adoption requirements — Saudi Arabia

Status: **draft requirements**, not certified compliance. Applies to a reusable app for any Saudi VAT-registered organization; not a template for a single company.

## 1. Technical prerequisites
- Supported platform for initial release: **Frappe v16 and ERPNext v16** on a supported Frappe deployment; supported minor versions and dependency ranges must be recorded and confirmed by automated tests before release.
- Install in an isolated staging site first; make a verified backup, document rollback and test migrations twice before production rollout.
- Use the current Frappe v16 deployment prerequisites from official documentation. Do not hard-code OS, database, Python or Node versions without a tested compatibility matrix.
- Bench installation is per-site. The project will publish audited Git tags and documented `bench get-app`, `bench --site <site> install-app sdce_vat`, and `bench --site <site> migrate` instructions once installability is proven.
- **ksa_compliance must be optional** unless a future feature explicitly requires it; integrations should check app presence and installed version, and gracefully degrade with an actionable warning.
- No assumption that HRMS, a specific chart of accounts, or a company's custom fields are installed. Extra integrations must be opt-in and tested.

## 2. Organizational prerequisites
- Saudi legal entity with an applicable VAT registration; authorized staff must verify tax identity, registration information, filing frequency and periods.
- An ERPNext Company record, base currency and fiscal settings, accounts/tax templates, posting/date conventions and historical migrations reviewed for completeness.
- Tax account mapping and document tax classifications must be **configured and confirmed per company**. Never infer universal account codes such as 2310.
- Source accounting records must be accessible to authorized app roles. Anomalies, unclassified records and unresolved GL differences block approval, but not drafting or diagnostics.
- Require designated preparer, reviewer and approver roles with server-side company isolation and a documented delegation policy.
- No company-specific defaults, supplier lists, VAT numbers, logos, bank accounts or taxpayer details in the distributed app.

## 3. Supported accounting and tax scenarios
- Separate sales and purchase tax bases and VAT amounts. Handle standard-rated, zero-rated, exempt and outside-scope supplies; domestic and cross-border transactions; returns/credit and debit notes; import VAT; reverse charge; corrections and prior-period adjustments subject to verified tax rules.
- Distinguish recoverable and non-recoverable input VAT. Never automatically infer recoverability from a VAT posting or from a zero tax amount.
- Address mixed-use and partial-exemption deductions through documented, versioned rules and reviewable configuration rather than one global percentage.
- Consider standard ERPNext Sales/Purchase Invoices and returns, tax rows, GL Entries, applicable Journal Entries and Expense Claims with eligibility validation; do not count multiple representations of one transaction twice.
- Period boundary, credit note allocation, exchange-rate/currency precision, date basis and rounding policies must be documented and tested.
- Classify all unmapped or questionable transactions explicitly as **Needs Review**, never silently suppress them.

## 4. Required behavior
- Company-scoped onboarding wizard with preflight validation: installed app versions, data permissions, VAT registration profile, tax-account mapping, tax classification completeness and source document availability.
- Calculation core must produce stable box IDs, full traceable source lines and a reconciliation report with GL, plus exceptions for unsupported or unclassified transactions.
- Approved return snapshot records calculation-engine and rule versions, source references and amounts; modifications after approval are detected without mutating original evidence.
- Separate statuses for calculated, internally approved, and externally filed returns. Filing with ZATCA is **manual unless a separately approved integration is implemented**.
- Arabic-first UX with English localization, RTL and accessible print/PDF/export. All representations use a single calculation snapshot.
- Approval is NOT proof of a correctly filed return; filing evidence/portal reference may be recorded by authorized users.
- No automatic journal posting, invoice amendment, electronic filing, or period locking by default.

## 5. Acceptance before public release
- Clean install, upgrade, uninstall and rollback tests on supported versions.
- Cross-company isolation tests and strict permission tests for every DocType, report and server endpoint.
- Synthetic-data tests covering all supported ZATCA form boxes, VAT treatments, amendments, returns, RCM, mixed-use deduction, no-VAT tax rows and GL exceptions.
- Repeatable reconciliation of every return box with its included source lines; test rounding; ensure no hard-coded expected totals.
- Print/PDF/Excel parity tests in Arabic/English; test CSV/Excel formula injection and escaping.
- Static analysis, dependency audit, secret scanning, independent security review and review of public release content.
- Document unsupported cases, regulator reference versions and explicit manual review requirements.
