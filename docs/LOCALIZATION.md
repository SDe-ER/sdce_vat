# Localization (Arabic and English)

Status: mandatory policy. Full Arabic and English support is a release gate, not an optional feature. No release
is approved while any string owned by `sdce_vat` is untranslated.

Checked against the Frappe Framework 16 source (`frappe/gettext/`, `frappe/commands/gettext.py`,
`frappe/translate.py`, `frappe/public/js/frappe/translate.js`).

## 1. Rules
- English is the source language in code. Arabic is a translation.
- Use only the Frappe gettext system: `sdce_vat/locale/main.pot` (template), `sdce_vat/locale/ar.po`
  (Arabic), compiled to `.mo` by bench. No parallel dictionary, no custom i18n code, no JSON translation files.
- Python: `from frappe import _` and `_("Text")`. For module-level constants use `_lt("Text")` (lazy).
- JavaScript: `__("Text")`.
- Jinja (print formats, templates): `{{ _("Text") }}`.
- Placeholders: `_("Row {0}: account {1} is listed twice").format(idx, account)`. Never build a sentence by
  joining translated fragments; never put variables inside the msgid with f-strings.
- Context: when one English word has different meanings, give a context:
  Python `_("Return", context="VAT return document")`, JavaScript `__("Return", null, "VAT return document")`.
- Scope: only strings owned by `sdce_vat`. `hooks.py` sets
  `ignore_translatable_strings_from = ["frappe", "erpnext"]` so the app POT does not copy (and the app PO does not
  override) Frappe or ERPNext strings.
- Users see the language set in their ERPNext profile. The app never forces Arabic or English on a user.

## 2. What must be translatable
| Area | Mechanism |
|---|---|
| App name, app tile, Desktop Icon | `hooks.py` `add_to_apps_screen` title; `desktop_icon/*.json` (Frappe extractor) |
| Workspace and Sidebar | `workspace/*/*.json`, `workspace_sidebar/*.json` (Frappe extractors) |
| DocTypes, fields, options, descriptions | DocType JSON (Frappe extractor) |
| Workflow states and actions | fixtures are not covered by a Frappe extractor → app extractor `sdce_vat/gettext/extractors/workflow_fixture.py` registered in `babel_extractors.csv` (standard Frappe extension point, as ERPNext does) |
| Module Onboarding, onboarding steps | Frappe extractors |
| Setup Wizard page, buttons, help texts | `__()` / `_()` |
| Errors, warnings, alerts, validation messages | `_()` / `__()`; alert codes map to translatable messages |
| Reports (names, columns, filters) | report JSON (Frappe extractor) + `_()` in the report `.py` |
| Print formats | print formats in the app are standard JSON with an HTML template; Frappe has no print-format extractor → app extractor `sdce_vat/gettext/extractors/print_format.py` reads `{{ _("…") }}` from the `html` field |
| Excel / CSV export headers | `_()` at export time |
| In-app user guidance | `_()` / `__()` |

Tax rule texts: the official ZATCA return field labels are published by ZATCA in Arabic and English. They are stored
in each published rule set as regulatory reference data (both official texts, versioned with the rule). They are not
UI translations. Every other text around them (headings, buttons, help) uses gettext.

## 3. Commands (run on a development bench; never on production)
```bash
# 1. extract all app strings into sdce_vat/locale/main.pot
bench generate-pot-file --app sdce_vat
# 2. first time only: create the Arabic catalog
bench create-po-file ar --app sdce_vat
# 3. sync ar.po with the new template (adds new msgids, marks changed ones)
bench update-po-files --app sdce_vat --locale ar
# 4. translate the new or fuzzy entries in sdce_vat/locale/ar.po (any PO editor)
# 5. compile and check
bench compile-po-to-mo --app sdce_vat --locale ar --force
bench --site <site> clear-cache
```
Commit `main.pot` and `ar.po`. Do not commit `.mo` files (they are built into `sites/assets/locale/`).
Note: `compile-po-to-mo` writes to the bench-wide `sites/assets/locale/`, which all sites on that bench share.

## 4. Right-to-left and left-to-right
- Arabic is fully RTL, English fully LTR; Frappe sets the direction from the user language.
- CSS uses logical properties only (`margin-inline-start`, `padding-inline-end`, `text-align: start`,
  `inset-inline-*`). No `left`/`right` hard-coded for layout.
- Numbers, VAT numbers, dates, amounts and document names inside Arabic text are wrapped so they keep LTR order
  (`<bdi>` / `dir="ltr"` on the value element).
- Currency and date formatting use Frappe formatters (`frappe.format`, `format_value`); no manual formatting.

## 5. Printing
- Every print format works in Arabic and English. Language can differ from the user: choose it in the print view
  language selector or with the `_lang` parameter; a print format may set `default_print_language`.
- Print formats read only stored values / the approved snapshot. There is one template; it does not recalculate.
  The same return printed in Arabic and English shows identical numbers.
- PDF: test with the bench PDF generator; Arabic letters must stay joined and numbers keep their order.

## 6. Acceptance criteria (release gate)
1. `main.pot` is up to date with the code (regenerating it gives no diff).
2. `ar.po`: 100 % of msgids translated, 0 fuzzy entries.
3. Placeholders (`{0}`, `{name}`, `%s`, `%(name)s`) are the same set in each msgid and its msgstr.
4. `compile-po-to-mo` succeeds.
5. No user-visible literal outside the translation functions (guard test on Python, JS and print templates).
6. An Arabic user sees no untranslated `sdce_vat` English string on any app screen; an English user sees no Arabic
   app string except official ZATCA labels shown in Arabic by design.
7. Forms, lists, tables, dialogs, buttons, menus, dates and currency render correctly in Arabic RTL and English LTR.
8. Reports, Excel exports and every print format (HTML and PDF) are checked in both languages with identical values.

## 7. Tests
| Check | Where |
|---|---|
| 1–5 | GitHub CI job "Localization" (bench on a fresh site) |
| 6–8 | QA site with one Arabic and one English test user (never change the Administrator language); browser checks and screenshots; report/print/Excel tests also as server tests comparing values in both languages |
