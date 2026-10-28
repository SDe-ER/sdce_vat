# Architecture decision record — draft

- **Deployment:** Standalone Frappe app `sdce_vat`; no modifications to ERPNext or ksa_compliance core.
- **Boundaries:** Source adapters -> tax classification -> calculation/reconciliation -> immutable return snapshot -> workflow -> presentation/exports.
- **Classification:** Based on transaction tax metadata and explicit documented rules; GL used for completeness and matching, not automatic tax classification.
- **Data sources:** Invoice and tax rows, returns, expense claims and approved JE categories. Tax zero is not synonymous with exempt or outside scope.
- **Financial integrity:** Decimal, currency precision rules, stable box identifiers, versioned rule sets and document provenance.
- **Multiple companies:** Explicit company permission checks in every server-side reader and action.
- **Print/export:** Single snapshot-derived source; no parallel calculations in UI or templates.
- **Integration:** Optional ksa_compliance adapter with dedicated test matrix when installed.
- **No automatic external submission:** Filing records represent human-entered proof unless a future separately reviewed integration is added.
