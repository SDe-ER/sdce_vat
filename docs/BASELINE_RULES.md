# Baseline rule file (Saudi VAT)

Status: reference data, **not tax advice**. Every rule ships and imports as **Pending**.

## Use
- File: `sdce_vat/rules/ksa_vat_2026_1.json`. The import creates the rule set `KSA-VAT` version 1.
- **Effective From is UNVERIFIED and left empty.** 19 Nov 2024 is the date of BoD resolution 01-06-24 (a decision
  date, stored only as `resolution_date` in the file). The date its amendments took effect was not found.
  - Without a confirmed Effective From, the set cannot be verified or published, so it can never be used in a return.
  - Each rule keeps its own date in its reference: the effective date, or else the publication date. The 15 % rate, for
    example, applies from 1 Jul 2020.
  - Verification is refused when a verified rule takes effect after the set's first day.
  - A rule set is one dated snapshot of the law, so it can mix rules of different dates as long as all of them
    already apply on its first day. A period before a later amendment needs an earlier version with its own start.
- **Import:** a VAT Rule Maintainer opens the *Saudi VAT Rule Set* list and selects **Import Baseline Rules**. The server equivalent is `sdce_vat.rules.baseline.import_baseline`, called with POST.
- **Result:** a Draft rule set (`Rule Draft`) in which every rule is Pending. A status in the file is ignored.
- **Verification and publication:** a second person checks each rule against the official Arabic source and marks it *Verified* or *Not applicable*. The existing workflow then verifies and publishes the set; this needs three different users.
- **Never used while pending:** the engine reads only published sets, so a Pending rule never reaches an approvable return.
- **Importing again changes nothing:** an existing set with the same code and version is returned as it is, in any state.
- **Atomic:** a file error creates nothing.
- **No effect on accounting data:** the import creates no invoices, journal entries or accounts, and changes no financial data.

## Why a small import action instead of a standard tool
```
STANDARD_OPTION_CHECKED=YES
STANDARD_OPTION_USED=NO
REASON_FOR_CUSTOM=see below
```
- **Fixtures** (`hooks.py` `fixtures`) would sync the set on every migrate and on every site, and overwrite the verifier's work. A rule set must be created on purpose and then checked by people.
- **Data Import** (Frappe) can create the document and its child tables, but:
  - it keeps any *Verified* status written in the file;
  - it has no check for "same code and version already exists" other than a duplicate-name error;
  - the user must find and upload a file from the repository.

  The action keeps the standard document, workflow and permissions. It only reads a shipped file, forces Pending, and is idempotent.

## Sources
The official Arabic texts are the legal reference. English texts are secondary (unofficial translation).
| Ref ID | Source | Version / date | Link |
|---|---|---|---|
| LAW-AR-2-2 | VAT Law, Art. 2(2) (Royal Decree M/113, Royal Order A/638) | Arabic official text; 15 % from 1 Jul 2020 | https://zatca.gov.sa/ar/RulesRegulations/Taxes/Pages/VATLaw.aspx |
| IR-AR-* | Implementing Regulations, 10th edition, Arabic official | Shawwal 1446H / Apr 2025; includes BoD resolution 01-06-24 (19 Nov 2024) | https://zatca.gov.sa/ar/RulesRegulations/Taxes/Documents/Implmenting%20Regulations%20of%20the%20VAT%20Law.pdf |
| GUIDE-RETURN-AR | VAT return user guide (e-service 009) | AR 2026-08-06 (EN 2026-07-29) | https://zatca.gov.sa/ar/eServices/Documents/eServices_Manual_009.pdf |
| GUIDE-ITD-AR | Input tax deduction guideline, 3rd edition | May 2026 | https://zatca.gov.sa/ar/HelpCenter/guidelines/Documents/Guideline-on-Input-Tax-Deduction-under-VAT-Provisions.pdf |
| GUIDE-AMEND-EN | Guideline on the amendments (BoD 01-06-24), English | 2024 | https://zatca.gov.sa/en/HelpCenter/guidelines/Documents/Amendments-to-the-Implementing-Regulation-of-(VAT).PDF |

The English Implementing Regulations (8th edition, 09 Nov 2021, unofficial) do **not** contain the 2024 amendments.

The Implementing Regulations references have no publication or effective date, because the exact day of the 10th edition and the date the 2024 amendments came into force were not found. A rule can be verified only when its reference has a URL, a section, a date and an access date. **The verifier enters the confirmed date in the reference before verifying.**

## Legal evidence matrix
Status of each date and provision. A rule is used only after a qualified person verifies it and the set is published.

### Confirmed from official texts
| Provision | Evidence | Source |
|---|---|---|
| The 15 % rate applies from 1 Jul 2020 | IR Art. 79(10), added by resolution 2-3-20 of 09 Jun 2020 | ZATCA Implementing Regulations (Arabic 10th edition, English 8th edition) |
| Art. 63(3) threshold changed from 5,000 to 15,000 by BoD decision 01-04-23 (26/11/1444H) | Published 1444-12-05 = 23 Jun 2023; "applied from the date of its publication" | Umm Al-Qura: https://www.uqn.gov.sa/details?p=23145 and https://www.uqn.gov.sa/details?p=23146 |
| The 10th edition of the Implementing Regulations includes BoD 01-06-24 (19 Nov 2024) | Edition dated Shawwal 1446H / Apr 2025; footnotes give the resolution date | ZATCA Arabic Implementing Regulations PDF |

### Candidates that need the official text
| Point | Candidate | Evidence so far | Still needed |
|---|---|---|---|
| Entry into force of BoD 01-06-24 | 18 Apr 2025 (date of publication) | Umm Al-Qura issue 5082 of 18 Apr 2025, reported by professional alerts (KPMG, PwC, DLA Piper) | The official gazette text of issue 5082, matched provision by provision |
| Exceptions to that date | Art. 47(3) from 1 Jan 2026; a 180-day grace for existing tax groups (Art. 10) | Same alerts | The same official text |

### Needs tax interpretation (not decided by the app)
- **Art. 63 threshold per period.** Candidates: 5,000 until 22 Jun 2023, then 15,000 from 23 Jun 2023, with the wording revised again by 01-06-24.
  - Open: which date decides. It may be the period of the error, the date it is found, or the date of the correcting return.
  - The return form label of field 14 ("± 5000") does not by itself override the newer regulation. The difference is recorded, not resolved.
- **Transitional rules that depend on another date than the tax date:** Art. 79(10), the Art. 10 grace period and the Art. 40(10) start month.
- **Art. 54(6)** timing, the **tax point** (GCC Agreement, Art. 23), and **fields 8 and 9**: see the points below.

### Effect on the app today
- No rule in this file is used: every rule is Pending and the set has no Effective From.
- The amendment check still uses a constant limit of 5,000 (`saudi_vat_amendment.py`, Issue #5). It sends a correction of 5,000–15,000 to a self-amendment instead of a later return.
- Filed or approved returns are never changed by a rule set.

## Rules (all Pending)
| Rule key | Proposed value | Source | Effective | Notes |
|---|---|---|---|---|
| `standard_rate` | 15 | Law Art. 2(2); IR Art. 79(10) | 1 Jul 2020 | Transitional rules until 30 Jun 2021. The rate is unreadable in the PDF text layer; it is readable in a layout extraction. |
| `treatment_box:*` (10 treatments) | S01–S05, P07–P11 | Return guide; IR Art. 62(2) | Form of 2026 | Art. 62(2) has no separate item for exports or non-deductible input. Fields 8 and 9 come from the guide only. |
| `treatment_box:out_of_scope` | `-` (no field) | IR Art. 62(2) | — | The verifier should set it to *Not applicable*. |
| `tax_date_basis:sales_invoice` / `purchase_invoice` | `invoice_date` (a purchase invoice without a bill date then needs review) | Input tax guideline p.33 (cites the GCC Agreement, Art. 23) | — | The general tax point is the earliest of supply, invoice and payment. Supply date is Issue #7. |
| `tax_date_basis:journal_entry` / `expense_claim` | `posting_date` | same | — | Proposal only. |
| `late_claim_limit_years` | 5 | IR Art. 49(7)–(8) | original text | Deferred claims: Issue #10. |
| `late_claim_limit_basis` | end of the calendar year of supply | IR Art. 49(8) | original text | |
| `unpaid_adjust_months` | 12 | IR Art. 40(10)–(11) | BoD 19 Nov 2024* | Re-deduction when paid: Art. 40(11). Issue #11. |
| `unpaid_adjust_start` | month after the supply month | IR Art. 40(10) | BoD 19 Nov 2024* | The 8th edition counted from the supply date. |
| `unpaid_financing_exception` | finance lease, murabaha, lease to own | IR Art. 40(10) | BoD 19 Nov 2024* | Conditions apply: contract in force, no dispute, VAT declared, supplier certificate. |
| `credit_note_period` | 15 days after the end of the month of the event | IR Art. 54(1)–(3), 54(6); Art. 40(4)–(6) | BoD 19 Nov 2024* | The Arabic wording of 54(6) is ambiguous. |
| `correction_rules` | `threshold_unresolved` (procedure: below the threshold in the current return; otherwise notify within 20 days; overstatement within 5 years) | IR Art. 63(1)–(4) | BoD 19 Nov 2024* | **Threshold not decided.** Art. 63(3) says 15,000, but the field 14 label says 5,000. |
| `recoverability:entertainment`, `employee_catering_health_insurance`, `restricted_vehicles`, `personal_use` | not deductible (with exceptions) | IR Art. 50(1)–(2); input tax guideline pp.27–28 | BoD 19 Nov 2024* | Vehicles: 10 seats or fewer. Heavy equipment and business-only vehicles are excluded. Issue #9. |

\* Date of the Board resolution only. The date the amendments **took effect** was not found, so these references carry no effective date and the verifier must enter it.

The file has **no rule** for these: `rounding` (no provision found; the nearest is Art. 45(2), a tax-inclusive price formula) and `non_recoverable_placement` (not stated in Art. 62). They stay in Saudi VAT Settings until a source is found.

All 16 return fields carry the ZATCA Arabic and English labels.

## Points for the tax adviser
1. **Entry into force of BoD resolution 01-06-24.** It is needed for Effective From (now empty) and for the effective dates of the amended references. Older periods need an earlier version.
2. **Art. 63 threshold of SAR 15,000 against field 14.** The current return form labels field 14 "between ± 5000". Decide which applies to corrections reported in the return.
3. **Art. 54(6):** exactly when a credit or debit note must be issued.
4. **Tax point:** the GCC Agreement, Art. 23, is not among the reviewed sources. Confirm the rule and how the app should use document dates until supply dates exist (#7).
5. **Fields 8 and 9 (imports):** the split between customs and reverse charge is taken from the guide only. Confirm it against the e-service form.
6. **Excerpts to recheck:** Art. 20(3), 40(5), 40(10), 49(7), 54(6), 62(2) and 63(1) were rebuilt from a damaged text layer. Check them against the rendered PDF.
7. **The 15 % figure:** check it in the rendered Law PDF, Art. 2(2), and the date of Royal Order A/638.
