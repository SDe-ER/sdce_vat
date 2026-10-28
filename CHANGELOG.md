# Changelog

## [Unreleased]

### Added
- Versioned tax rule sets (#4): role VAT Rule Maintainer, workflow "Saudi VAT Rule Set Approval", DocTypes Saudi
  VAT Rule Set, Rule Reference, Rule and Rule Field Label. Three different users prepare, verify and publish
  (checked on the server by user id); published sets are hashed and cannot be changed; normal versions cannot
  overlap or cover approved return periods; corrective versions need a documented basis. Rule sets are not used
  by the engine yet.
  - Impact: new role, workflow and DocTypes; no change to existing DocTypes, permissions or returns. Rollback:
    revert the change and migrate; the fixture role and workflow stay until an administrator deletes them.
- Initial import of the reviewed core (see docs/IMPLEMENTATION_STATUS.md):
  - Frappe v16 app `sdce_vat`, module Saudi VAT, roles VAT Preparer, VAT Reviewer and VAT Approver, and the
    workflow "Saudi VAT Return Approval" as fixtures.
  - Read-only calculation engine (`sdce_vat/engine`, docs/ENGINE.md).
  - DocTypes Saudi VAT Settings, Saudi VAT Return, Saudi VAT Filing and Saudi VAT Amendment with child tables
    (docs/DOCTYPES.md); server-side separation of duties, protected calculated values, approval only from the
    reviewed state, hashed snapshot, drift and snapshot checks.
  - Tests with synthetic data only, including negative authorization and two-company tests.
  - License GPL-3.0-or-later.
- Impact: new module, roles, workflow and DocTypes. No ledger entry, no change to existing DocTypes or
  permissions. Rollback: `bench --site <site> uninstall-app sdce_vat` (fixture roles stay unless an
  administrator deletes them).
