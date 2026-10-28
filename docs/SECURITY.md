# Security policy (initial draft)

This is a public code repository, not a repository for tax records or production configuration.

- No credentials, API tokens, certificates, supplier or customer identifiers, real tax IDs, invoices, backups, test exports, `.env`, `site_config.json`, database dumps, or raw logs.
- Synthetic test data only.
- Apply Frappe server-side permission checks, company isolation and audit logs; never trust client-only validation.
- Review SQL parameterization, HTML escaping, XSS, export injection and public endpoints.
- Report vulnerabilities privately through GitHub: Security tab → "Report a vulnerability"
  (https://github.com/SDe-ER/sdce_vat/security/advisories/new). Do not open a public issue.
