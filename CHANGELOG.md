# Changelog

## [Unreleased]

### Added
- Correction limit from rules (#5): a Saudi VAT Amendment of kind "Correction in a Later Return" checks its VAT
  effect against the verified `correction_limit` rule (new rule key, positive SAR amount) of the published rule set
  in force on the last day of the original period. The 5,000 constant is removed; without a verified rule the
  correction is refused (IR Art. 63 threshold stays open for the verifier).
  - Impact: until a verified `correction_limit` is published, only self-amendments are possible. Rollback: revert.
- Baseline rule file `sdce_vat/rules/ksa_vat_2026_1.json` (#17): official ZATCA references (Arabic Implementing
  Regulations 10th edition, VAT Law, return guide, input tax guideline) for 27 rules and the 16 return field labels
  in Arabic and English. "Import Baseline Rules" (VAT Rule Maintainer) creates a Draft rule set with every rule
  Pending; importing again changes nothing; nothing is verified or published automatically. See
  docs/BASELINE_RULES.md for the points a tax adviser must verify.
  - Impact: no change to existing rule sets, returns or accounting data. Rollback: revert; an imported draft set
    can be deleted by its maintainer.
- Engine 0.2.0 reads published rule books (#6): box placement, standard rate and tax-date basis come from the
  published Saudi VAT Rule Set in force on each line's tax date; several rule sets in one period are supported;
  missing, unverified or conflicting rules, undetermined tax dates and rule transitions are rule issues that block
  approval (never guessed). Settings gain `rule_set_code`; the return stores the rule sets used, the tax date and
  rule set of each source, a full rule copy in the snapshot, and refuses approval when the rules changed after the
  calculation.
  - Impact: a site must publish a rule set and set `rule_set_code` in Saudi VAT Settings before a return can be
    approved; with a rule set equivalent to the old code the results are identical (parity test). Returns of
    engine 0.1.0 keep their snapshot. Rollback: revert the change and migrate; new fields stay empty.
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
