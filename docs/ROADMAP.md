# Roadmap and acceptance gates

## 0 — Governance and compliance baseline
- Verify repository owner and public visibility.
- Document intended open-source license (do not assume prior MIT choice applies automatically).
- Establish branch protection, CODEOWNERS, security reporting, issue and PR templates, CI, dependency policy, and secret scanning.
- Record dated ZATCA references and legal/accounting decisions, distinguishing verified rules from assumptions.
- Audit every file for sensitive data before publishing.

**Gate:** No production or customer data in public Git history. Maintainer approves scope and license.

## 1 — Frappe application foundation
- Pin tested Frappe/ERPNext 16 versions and Python dependencies; compatibility matrix for ksa_compliance.
- Standard app layout, lint, type checking where practical, unit tests and CI.
- QA isolation, idempotent install/migrate tests and backup/rollback steps.

**Gate:** Clean installation, repeat migrations, test suite, no production access.

## 2 — Tax classification contract
- Stable return box IDs and versioned classification rules; distinguish tax base, tax amount, recoverability, rates, outside scope, adjustments.
- Document row inclusion rules, date basis, credit/debit notes, rounding, and journal-only adjustments.
- Tests from synthetic transactions; unresolved cases must be explicit, never silently classified.

**Gate:** Approved classification matrix and traceable test cases.

## 3 — Calculation and reconciliation engine
- Central server-side calculation using Decimal and preserved document provenance.
- Handle Sales/Purchase Invoices, Returns, Expense Claims and qualified JEs with deduplication and tax account GL reconciliation.
- Avoid force-fitting expected totals; explain differences.

**Gate:** All box totals equal included source lines; GL differences reported and explained.

## 4 — Standard DocTypes, workflow, security
- Saudi VAT Return; child lines and provenance; filing evidence; amendment trail.
- Company permissions, server-side validation, separation of preparer/reviewer/approver, immutable snapshot on approval.
- Approval does not send data to ZATCA or post accounting entries automatically.

**Gate:** Authorization and tamper tests; review gate before merge.

## 5 — UI, printing and exports
- Accessible Arabic/English, RTL, server-owned calculations shared across screen, print, PDF and Excel.
- Printable return layout clearly marked internal unless validated against current ZATCA portal.

**Gate:** Rendering, reconciliation and export tests.

## 6 — Acceptance & release
- QA acceptance on synthetic data, optional authorized comparison with real data kept entirely off public GitHub.
- Security review, performance, backward compatibility, versioned release and rollback playbook.

**Gate:** Owner approval for any production installation.
