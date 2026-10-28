# Calculation engine

Package `sdce_vat/engine`. Server-side, read-only, Decimal arithmetic.

| Module | Role | Imports frappe |
|---|---|---|
| `money.py` | `D()` (Decimal without float error), `q2()` (round half up to 0.01), `total()` | no |
| `boxes.py` | stable field ids `S01`…`S06`, `P07`…`P12`, `T13`…`T16` with ZATCA labels (AR/EN) | no |
| `model.py` | `SourceLine`, `GLRow`, `BoxTotal`, `AccountProof`, `VatResult`, `Treatment`, `Column` | no |
| `config.py` | `VatConfig`: VAT accounts with rates, category → treatment map, non-deductible placement rule, tolerance | no |
| `rows.py` | document rows → `SourceLine` (Sales/Purchase Invoice, Journal Entry, Expense Claim) | no |
| `classify.py` | treatment, box, column and warnings of one line | no |
| `core.py` | `calculate()`: classify, unmatched GL, GL differences, possible duplicates, box totals, proof | no |
| `sources.py` | SELECT queries on the site (documents, child rows, GL Entry, optional ksa_compliance fields) | yes |
| `run.py` | `compute(config, from_date, to_date)`: permission checks, read, calculate, prove no write | yes |

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
