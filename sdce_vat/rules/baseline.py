# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Baseline rule files shipped with the app (`sdce_vat/rules/*.json`).

A baseline file lists the official references and proposes rule values with their source. It is never tax advice:
importing it creates a Draft rule set in which every rule is Pending. Each organization's verifier, a person other
than the one who prepared the set, checks every rule against the source before the set can be published.
"""

import json
import re
from pathlib import Path

import frappe
from frappe import _

from sdce_vat.constants import VAT_RULE_MAINTAINER
from sdce_vat.saudi_vat.doctype.saudi_vat_rule_set.saudi_vat_rule_set import (
	HEADER_FIELDS,
	LABEL_FIELDS,
	REFERENCE_FIELDS,
	RULE_FIELDS,
)

RULES_DIR = Path(__file__).parent
NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,60}$")
PENDING = "Pending"
FILE_ONLY_KEYS = (
	"baseline_file",
	"notice_en",
	"notice_ar",
)  # documentation in the file, not rule set content


def baseline_names() -> list[str]:
	return sorted(path.stem for path in RULES_DIR.glob("*.json"))


def read_baseline(name: str) -> dict:
	"""The content of one shipped file. Only names of files in this folder are accepted."""
	if not isinstance(name, str) or not NAME_PATTERN.match(name) or name not in baseline_names():
		frappe.throw(_("Unknown baseline rule file {0}").format(name))
	return json.loads((RULES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def as_rule_set(data: dict) -> dict:
	"""The rule set document of a baseline file: Draft, and every rule Pending whatever the file says."""
	return {
		"doctype": "Saudi VAT Rule Set",
		**{field: data.get(field) for field in HEADER_FIELDS if field in data},
		"references": [{f: row.get(f) for f in REFERENCE_FIELDS} for row in data.get("references", [])],
		"rules": [
			{**{f: row.get(f) for f in RULE_FIELDS}, "verification_status": PENDING}
			for row in data.get("rules", [])
		],
		"field_labels": [{f: row.get(f) for f in LABEL_FIELDS} for row in data.get("field_labels", [])],
	}


@frappe.whitelist(methods=["POST"])
def import_baseline(name: str) -> str:
	"""Create a Draft rule set from a shipped baseline file (VAT Rule Maintainer). Every rule is Pending.

	Importing again changes nothing: a rule set with the same code and version, whatever its state, is returned
	as it is and never replaced, so a draft in progress or a published set is never overwritten.
	"""
	if VAT_RULE_MAINTAINER not in frappe.get_roles():
		frappe.throw(_("Only a VAT Rule Maintainer can import a baseline rule file"), frappe.PermissionError)
	data = read_baseline(name)
	existing = frappe.db.get_value(
		"Saudi VAT Rule Set",
		{"rule_set_code": data.get("rule_set_code"), "version": data.get("version")},
		"name",
		for_update=True,
	)
	if existing:
		frappe.msgprint(
			_("Rule set {0} already exists; it was not changed").format(existing),
			indicator="blue",
			alert=True,
		)
		return existing
	try:
		return frappe.get_doc(as_rule_set(data)).insert().name
	except frappe.DuplicateEntryError:
		# a parallel import created the same set first; the failed insert wrote nothing, so return that set
		return frappe.db.get_value(
			"Saudi VAT Rule Set", {"rule_set_code": data.get("rule_set_code"), "version": data.get("version")}
		)


@frappe.whitelist(methods=["GET"])
def list_baselines() -> list[dict]:
	"""The shipped baseline files and the rule set each one creates (read only)."""
	if VAT_RULE_MAINTAINER not in frappe.get_roles():
		frappe.throw(_("Only a VAT Rule Maintainer can import a baseline rule file"), frappe.PermissionError)
	return [
		{"name": name, "rule_set_code": data.get("rule_set_code"), "version": data.get("version")}
		for name, data in ((name, read_baseline(name)) for name in baseline_names())
	]
