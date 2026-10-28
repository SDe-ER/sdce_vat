# SDCE VAT

An open-source, Frappe/ERPNext-based Saudi VAT return application under development.

> **Project status:** Planning / pre-implementation. Not affiliated with, endorsed by, or certified by ZATCA. No automated filing or compliance guarantee is claimed.

## Goals
- Auditable VAT return calculation and source traceability.
- Company-scoped permissions and approval workflow.
- Reconciliation with ERPNext GL and tax documents.
- Arabic/English output, accessible RTL layouts, printable returns and detail reports.
- Versioned calculation rules and immutable approved snapshots.

## References
- ZATCA's official VAT return filing user guide (reviewed separately; do not assume screenshots define every legal tax treatment).
- Frappe/ERPNext official development and accounting documentation.

## Safety and disclosure
Never commit company names, invoices, tax IDs, customer/supplier records, credentials, certificates, backups, exported ledger rows, real tax returns, `.env` files, site configs, or local QA evidence. Use synthetic fixtures only.

## Development workflow
See [Roadmap](docs/ROADMAP.md), [Architecture](docs/ARCHITECTURE.md), and [Security](docs/SECURITY.md). All changes via reviewed pull requests. Production is out of scope until explicit approval.

## Existing work
Earlier local `sdce_vat` phases remain preserved separately as reference material. This repository starts fresh; nothing is imported until code review, licensing review, and data-leak checks pass.

## National scope and prerequisites
This project is intended for Saudi organizations using ERPNext, not a single taxpayer. Review [Installation and adoption requirements](docs/INSTALLATION_REQUIREMENTS.md), [ZATCA traceability](docs/ZATCA_REQUIREMENTS.md), [Compatibility matrix](docs/COMPATIBILITY_MATRIX.md), and [Release gates](docs/RELEASE_CRITERIA.md) before deploying. **No ZATCA certification or automatic submission is claimed.**
