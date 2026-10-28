# Changelog

## [Unreleased]

### Added
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
