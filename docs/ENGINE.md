# Calculation engine

Package `sdce_vat/engine`. Server-side, read-only, Decimal arithmetic.

| Module | Role | Imports frappe |
|---|---|---|
| `money.py` | `D()` (Decimal without float error), `q2()` (round half up to 0.01), `total()` | no |
| `boxes.py` | stable field ids `S01`…`S06`, `P07`…`P12`, `T13`…`T16` with ZATCA labels (AR/EN) | no |
| `model.py` | `SourceLine`, `GLRow`, `BoxTotal`, `AccountProof`, `VatResult`, `Treatment`, `Column` | no |
| `config.py` | `VatConfig`: VAT accounts with rates, category → treatment map, non-deductible placement rule, tolerance | no |
| `rows.py` | document rows → `SourceLine` (Sales/Purchase Invoice, Journal Entry, Expense Claim) | no |
| `rules.py` | `RuleSet`, `RuleBook.for_date()` (normal version + correction chain), `resolve()`: tax date and rule set of one line | no |
| `classify.py` | treatment, box (from the rule set), column and warnings of one line | no |
| `core.py` | `calculate(..., rule_book=)`: resolve rules, classify, unmatched GL, GL differences, possible duplicates, box totals, proof, rule sets used | no |
| `sources.py` | SELECT queries on the site (documents, child rows, GL Entry, optional ksa_compliance fields) | yes |
| `run.py` | `compute(config, from_date, to_date)`: permission checks (GL, company, rule sets), read the published rule book, calculate, prove no write | yes |

Engine version 0.2.0 (rule books). 0.1.0 had the box map and the tax date (= posting date) in code.

## Rule books (0.2.0)
- Settings name a rule-set code (`rule_set_code`). Only **published** Saudi VAT Rule Sets of that code are read;
  drafts, verified-only and cancelled sets are never used. The stored content of each set is hashed again before
  use; a mismatch stops the calculation.
- Per line: the set in force on the posting date gives `tax_date_basis:<source>` (`sales_invoice`,
  `purchase_invoice`, `journal_entry`, `expense_claim`; value `posting_date` or `invoice_date`). The tax date is
  that date; the set in force on the tax date classifies the line. Documents are still selected by posting date;
  a tax date outside the return period is reported, never moved.
- Dates stay separate on every line: `posting_date` (ledger, GL proof), `invoice_date` (Sales Invoice posting
  date, Purchase Invoice / Journal Entry bill date), `tax_date`. Supply date and the claim period of input VAT
  are not built yet (#7, #10).
- A date resolves to the one normal version that covers it (an open end stops the day before the next normal
  version), then along its published corrections. Several sets in one period are normal: each line keeps its set.
- Box of a treatment: rule `treatment_box:<treatment>` (Verified: field id; Not applicable: no field). The
  account rate is compared with `standard_rate` (`rate_differs_from_rule` warning).
- Rule issues (the line is not placed, needs review, approval is blocked): `rule_set_not_configured`,
  `rule_set_missing`, `rule_set_conflict`, `rule_missing:<key>`, `rule_unverified:<key>`, `rule_invalid:<key>`,
  `tax_date_undetermined`, `tax_date_outside_period`, `rule_transition_review` (the set of the tax date states
  another basis), `tax_date_source_unknown`.
- Parity: `sdce_vat/tests/rule_fixtures.py` states the 0.1.0 behaviour as rules; with it the engine gives results
  identical to 0.1.0 (`tests/parity_engine_0_1_0.json`, produced by 0.1.0).

## Sources
- Sales Invoice and Purchase Invoice (incl. returns `is_return` and debit notes `is_debit_note`): VAT from tax rows
  on configured VAT accounts (`base_tax_amount_after_discount_amount`, Deduct rows negative); base from
  `Item Wise Tax Detail.taxable_amount` of the same tax row (ERPNext v16). A document with no VAT charged
  (no VAT row, or VAT rows of 0) gives one line without a VAT account.
- Journal Entry: one line per configured VAT account; base = non-VAT lines without party on the same side
  (debit or credit) as the VAT.
- Expense Claim (only when hrms is installed): VAT rows; base = sanctioned amount when the claim has one VAT account.
- GL Entry (`is_cancelled = 0`) on the configured VAT accounts proves every line; VAT in the ledger that no line
  explains becomes an `unmatched_gl` line for review (e.g. Payment Entry taxes).
- ksa_compliance (optional): `custom_zatca_item_tax_category` (Sales Invoice Item, Item Tax Template) and
  `custom_zatca_category` (Tax Category) are read only when the fields exist.

## Treatments and placement
Placement below is the content of the parity rule set (it was code in 0.1.0); a published rule set decides it.

| Treatment | Field |
|---|---|
| standard_rated_sale | 1 (S01) |
| government_bears | 2 |
| zero_rated_sale | 3 |
| export | 4 |
| exempt_sale | 5 |
| input_deductible | 7 |
| import_customs | 8 |
| import_reverse_charge | 9 |
| zero_rated_purchase | 10 |
| exempt_purchase | 11 |
| input_not_deductible | none while `non_deductible_placement` is empty (line stays under review); then excluded or field 7 without VAT |
| out_of_scope | none (listed, not reported) |
| needs_review | none; blocks approval |

- Credit notes, debit notes and negative journal corrections go to the adjustment column.
- A line without VAT takes its treatment only from configured categories (Tax Category, Item Tax Template,
  ZATCA category). No category → `zero_vat_unclassified`; two different categories → `conflicting_categories`.
- Warnings never move a line: `rate_mismatch`, `base_missing`, `supplier_vat_number_missing_or_invalid`,
  `journal_entry_claim_needs_document_review`, `gl_difference`, `possible_duplicate`.

## Guarantees (asserted in code and tests)
- A source (voucher, VAT account, side) is counted once (`ValueError` otherwise).
- Every line box = sum of its lines; totals = sum of their boxes; field 13 = VAT 6 − VAT 12;
  field 16 = 13 + corrections − credit carried.
- `compute()` raises if the database write counter changes during the run.
- No account, rate or category is hard-coded; the caller passes `VatConfig` (built from Saudi VAT Settings).
- No box map or tax-date rule is in code; they come from the published rule book.
