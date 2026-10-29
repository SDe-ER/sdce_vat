# DocTypes

Module **Saudi VAT**. All values come from the engine (`sdce_vat/engine`); DocTypes store, approve and freeze
them. No DocType creates a ledger entry.

| DocType | Kind | Purpose |
|---|---|---|
| Saudi VAT Settings | per company (name = company) | rule-set code of the published rule book, VAT accounts with family and rate (child Saudi VAT Account), category rules (child Saudi VAT Category Rule), non-deductible placement rule (empty = lines stay under review), Expense Claim switch, tolerance; `to_config()` builds the engine configuration |
| Saudi VAT Return | submittable, Workflow | one company and period; `calculate()` stores the engine result: fields (child Saudi VAT Return Line, 16 rows), sources with tax date, basis, rule set and rule issue (child Saudi VAT Return Source), GL proof (child Saudi VAT Return Proof), rule sets used with version, content hash, line count and tax-date range (child Saudi VAT Return Rule Set); approval freezes a snapshot with a full copy of the rules |
| Saudi VAT Filing | submittable | values actually filed on the ZATCA portal per field (child Saudi VAT Filing Field) next to the approved values; a reason is mandatory for every difference; one filing per return |
| Saudi VAT Rule Set | submittable, Workflow, name `{rule_set_code}-{version}` | one dated, versioned set of tax rules: references (child Saudi VAT Rule Reference), rules from a closed key list (child Saudi VAT Rule), Arabic and English return field labels (child Saudi VAT Rule Field Label); `version_type` Normal or Corrective (`supersedes`, `correction_basis`); `content_hash`; not yet used by the engine |
| Saudi VAT Amendment | submittable | later corrections linked to the original return: correction in a later return (VAT effect within the verified `correction_limit` of the published rule set in force on the last day of the original period; refused when that rule is missing or not verified, IR Art. 63) or self-amendment; lines in child Saudi VAT Amendment Line |

## Stages
Calculated (engine run stored on a draft return, `calculation_hash`) → Internally approved (submitted return,
`snapshot_hash` + private JSON snapshot file) → Actually filed (Saudi VAT Filing). Amend a cancelled return with
the standard amend (`amended_from`).

## Workflow "Saudi VAT Return Approval" (fixture)
| From | Action | To | Role | Condition |
|---|---|---|---|---|
| VAT Draft | Prepare VAT Return | VAT Prepared | VAT Preparer | calculated |
| VAT Prepared | Return to Preparer | VAT Draft | VAT Reviewer | |
| VAT Prepared | Review VAT Return | VAT Reviewed | VAT Reviewer | no source under review, reconciled; reviewer is not the preparer or calculator |
| VAT Reviewed | Reject VAT Return | VAT Draft | VAT Approver | |
| VAT Reviewed | Approve VAT Return | VAT Approved (submit) | VAT Approver | same; approver is not the calculator, preparer or reviewer |
| VAT Approved | Cancel VAT Return | VAT Cancelled | VAT Approver | |

## Workflow "Saudi VAT Rule Set Approval" (fixture)
| From | Action | To | Role | Server check |
|---|---|---|---|---|
| Rule Draft | Verify Rule Set | Rule Verified | VAT Reviewer or VAT Rule Maintainer | verifier did not create or change the set; no Pending rule; every Verified rule and the correction basis cite a complete reference (https URL, section, publication or effective date, access date); stamps verifier and `content_hash` |
| Rule Verified | Return Rule Set to Draft | Rule Draft | VAT Rule Maintainer, VAT Reviewer or VAT Approver | clears the verification stamps and the hash |
| Rule Verified | Publish Rule Set | Rule Published (submit) | VAT Approver | publisher is not a contributor or the verifier; content still has the verified hash; publication checks below |
| Rule Published | Cancel Rule Set | Rule Cancelled | VAT Approver | no approved return in its dates; no published correction of it |

## Server-side rules (Saudi VAT Rule Set)
- Content (header, references, rules, labels) changes only in Rule Draft and only by a VAT Rule Maintainer. Every
  user who saves a content change is stored in `contributors`; contributors can never verify or publish the set,
  so one person holding all three roles cannot complete the cycle.
- Verification and publication stamps, `contributors` and `content_hash` are set by the server only; a form or
  REST save that changes them is refused; a new set cannot bring its own stamps.
- Direct submit and direct state changes are refused; publication only from Rule Verified through the workflow.
- Published sets cannot be changed (form, REST, `frappe.client.set_value`); `content_is_intact()` detects a change
  made below the ORM.
- Rule keys: the closed list in `sdce_vat/constants.py` (`RULE_KEYS`, `RULE_KEY_PREFIXES`); one row per key;
  numeric keys are checked. Field labels only for existing return field ids.
- Publication: version higher than every published version of the same code. Normal versions of a code never
  cover the same day (same start refused; an explicit Effective To may not reach the next start; an open end
  stops the day before the next normal version starts) and never cover the period of an approved VAT return.
  A Corrective version supersedes one published set of the same code, stays inside its dates, cites a complete
  correction basis, and may cover approved periods. Corrections form one chain: each published set has at most
  one published correction, so a further correction supersedes the latest one (v1 ← v2 ← v3). The chain has no
  branch and no loop, because a correction can only supersede a set that was published before it and has a
  lower version. Publishing never changes an approved return, filing or snapshot.
- Rows of a rule set cannot be saved on their own (`PUT /api/resource/<child>/<name>`, `frappe.client.save` with a
  row); no role has delete, import, amend or rename on rule sets.

### Rule sets in a multi-company site
- Rule sets are national tax rules and have no company field: one published set applies to every company of the
  site. That is why the three duties are separate users and why a normal version is refused when an approved
  return of **any** company falls in its dates. A refusal names that return only when the user may read it.
- Give the rule roles (VAT Rule Maintainer, and VAT Reviewer / VAT Approver used for rule sets) only to people
  trusted for all companies. Company User Permissions do not restrict rule sets.
- The duty checks use the user's roles and user id in the controller, not only DocPerms, so an extra DocPerm
  does not let a user skip a step. A System Manager can still change roles, DocPerms or server scripts; that is
  the site administration trust boundary and is outside what an app can enforce.

### Concurrent publication
Publication takes a `SELECT … FOR UPDATE` on every set of the same code (indexed `rule_set_code`) inside the
request transaction; Frappe has already locked the set's own row. Two publications of one code at the same
moment therefore cannot both commit: on QA (MariaDB, two processes, one forced 3-second overlap) one published
and the other was rolled back by the database (`QueryDeadlockError`, "Record has changed since last read");
its retry was refused by the publication checks. The user sees an error and retries; nothing is half-written.

## Server-side rules (Saudi VAT Return)
- Company read permission required; overlapping periods of the same company are refused.
- Calculated values, approval stamps and snapshot fields change only through `calculate()` / the workflow; a form
  or REST save that changes them (or child rows) is refused; a new return cannot bring its own values.
- `calculate()` (POST): write permission, role VAT Preparer, draft state only; it clears earlier preparation and
  review stamps. Returning to draft clears them too.
- Review: role VAT Reviewer; the reviewer must not be the preparer or the calculator.
- Approval (`before_submit`): only from VAT Reviewed (a direct submit is refused); no source under review;
  reconciled with GL; approver ≠ calculator, preparer and reviewer; stored tables still match `calculation_hash`;
  a fresh engine run still gives the same hash (documents unchanged). Then the snapshot is written.
- `check_drift()` (GET) and `verify_snapshot()` (GET): read permission, no writes. `check_drift()` also lists
  changed rule sets (`changed_rule_sets`).
- Rule books (engine 0.2.0): `calculation_hash` covers each source's tax date, basis, rule set and rule issue and
  the (rule set, content hash) list. Approval re-runs the engine; a published correction or a new version after
  the calculation changes that list and approval is refused ("rule sets changed"). The snapshot stores the full
  canonical content of every rule set used, so the approved return stays verifiable after later corrections.
  Returns calculated by engine 0.1.0 keep their original payload and snapshot.
- Submitted returns are immutable (no allow-on-submit fields).

## Permissions
| DocType | VAT Preparer | VAT Reviewer | VAT Approver | Others |
|---|---|---|---|---|
| Settings | read | read | read | Accounts Manager / System Manager write; Auditor read |
| Return | create, write | write | write, submit, cancel, amend | Accounts Manager, Auditor read |
| Filing | read | create, write | create, write, submit, cancel, amend | Auditor read |
| Amendment | create, write | write | write, submit, cancel, amend | Auditor read |
| Rule Set | read | write (workflow steps only) | write, submit, cancel | VAT Rule Maintainer create, write; Accounts Manager, System Manager, Auditor read |
The engine also needs read access to the general ledger (e.g. Accounts User); no existing permission was widened.
