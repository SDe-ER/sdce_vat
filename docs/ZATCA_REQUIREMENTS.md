# ZATCA requirements traceability (draft)

**Status:** This file is a requirements catalogue, not a statement of certification or legal advice. For each release, verify the **current** law, implementing regulations, guidance, amendments and actual portal form. Archive the publication/version date and effective date for every verified rule.

## Source hierarchy
1. Saudi VAT law and current implementing regulations including amendments.
2. ZATCA official binding instructions and applicable official electronic-invoicing requirements.
3. ZATCA official VAT filing portal/user guide and tax guidance (procedural and interpretive).
4. Frappe/ERPNext technical documentation.

Do not treat an illustrative portal screenshot as a legally complete taxonomy or independently sufficient proof of correct filing.

## Capability mapping

| ID | Topic | Required implementation behavior | Evidence before marking verified |
|---|---|---|---|
| Z-01 | Taxpayer identity | Separate VAT profile by legal entity; no hard-coded taxpayer info | Registration and current rules |
| Z-02 | Filing period | Company-level period calendar; validated date boundaries | Portal / registration context |
| Z-03 | Sales categories | Configurable, versioned mapping to applicable form boxes | Current ZATCA form and regulations |
| Z-04 | Purchases and deductions | Record recoverable vs non-recoverable input VAT and evidence | Input-tax guidance and regulations |
| Z-05 | Imports / reverse charge | Separate treatment and associated taxes | Current rules and official guidance |
| Z-06 | Credit/debit notes and adjustments | Explicit provenance and correct period mapping | Current rules, official guidance |
| Z-07 | Corrections / carried balances | Separate filing correction model; no silent netting | Current rules/portal |
| Z-08 | Audit trail | Evidence, source references, approval and filed values retained | Retention requirements and product audit review |
| Z-09 | Output | Arabic/English view and print aligned to current portal labels | Validated live portal/manual comparison |
| Z-10 | Security and data protection | Role-based access, lawful data handling; no data exposure to public repo | Security assessment / local legal review |
| Z-11 | E-invoicing integration | Separate integration; never claim FATOORA certification | Applicable ZATCA technical specifications |

## Filing workflow reference
The ZATCA Arabic *VAT Return Filing User Guide* (official guide) illustrates: choosing a return, taxpayer details, VAT sales and purchases, VAT summary, supporting attachments, optional notes, review/submission, and acknowledgment/download (pages 5–9). This guides usability, **not** a promise of portal equivalence or automated submission.

## Current references to verify
- https://zatca.gov.sa/ar/RulesRegulations/Taxes/Pages/VATImplementingRegulations.aspx
- https://zatca.gov.sa/ar/eServices/Documents/eServices_Manual_009.pdf
- https://www.zatca.gov.sa/en/HelpCenter/guidelines/Documents/Input%20Tax%20Deduction.pdf

## Release rule
For each feature store its source URL, publication and effective dates, exact verified section, reviewer, test cases, and verification status (Verified / Pending / Not applicable). Unverified tax rules remain gated from automatic approval.
