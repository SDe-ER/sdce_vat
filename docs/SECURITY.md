# Security policy (initial draft)

This is a public code repository, not a repository for tax records or production configuration.

- No credentials, API tokens, certificates, supplier or customer identifiers, real tax IDs, invoices, backups, test exports, `.env`, `site_config.json`, database dumps, or raw logs.
- Synthetic test data only.
- Apply Frappe server-side permission checks, company isolation and audit logs; never trust client-only validation.
- Review SQL parameterization, HTML escaping, XSS, export injection and public endpoints.
- Disclose vulnerabilities privately to maintainers rather than through public issues (configure private reporting once repo is created).
