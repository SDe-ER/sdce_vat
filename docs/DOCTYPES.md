# DocTypes

Module **Saudi VAT**. All values come from the engine (`sdce_vat/engine`); DocTypes store, approve and freeze
them. No DocType creates a ledger entry.

| DocType | Kind | Purpose |
|---|---|---|
| Saudi VAT Settings | per company (name = company) | VAT accounts with family and rate (child Saudi VAT Account), category rules (child Saudi VAT Category Rule), non-deductible placement rule (empty = lines stay under review), Expense Claim switch, tolerance; `to_config()` builds the engine configuration |
| Saudi VAT Return | submittable, Workflow | one company and period; `calculate()` stores the engine result: fields (child Saudi VAT Return Line, 16 rows), sources (child Saudi VAT Return Source), GL proof (child Saudi VAT Return Proof); approval freezes a snapshot |
| Saudi VAT Filing | submittable | values actually filed on the ZATCA portal per field (child Saudi VAT Filing Field) next to the approved values; a reason is mandatory for every difference; one filing per return |
| Saudi VAT Rule Set | submittable, Workflow, name `{rule_set_code}-{version}` | one dated, versioned set of tax rules: references (child Saudi VAT Rule Reference), rules from a closed key list (child Saudi VAT Rule), Arabic and English return field labels (child Saudi VAT Rule Field Label); `version_type` Normal or Corrective (`supersedes`, `correction_basis`); `content_hash`; not yet used by the engine |
| Saudi VAT Amendment | submittable | later corrections linked to the original return: correction in a later return (VAT effect ≤ ± 5,000 SAR; rule reference still to be versioned, see IMPLEMENTATION_STATUS.md) or self-amendment; lines in child Saudi VAT Amendment Line |

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
  correction basis, and may cover approved periods; one published correction per set. Publishing never changes
  an approved return, filing or snapshot.

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
- `check_drift()` (GET) and `verify_snapshot()` (GET): read permission, no writes.
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
