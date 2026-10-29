# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Rule books: the published tax rule sets of one rule-set code, resolved per date. Pure, no database access.

For one line:
1. The set in force on the posting date gives `tax_date_basis:<source>`: which document date is the tax date.
2. The tax date is that date. Posting, invoice and tax dates stay separate fields; a missing date, a date outside
   the return period, or an unverified basis is never guessed: the line gets a rule issue and needs review.
3. The set in force on the tax date gives the rules for classification. When it differs from the set of step 1
   and states another basis for the source, the line needs review (rule transition).
A date resolves to the normal version that covers it, then along its chain of published corrections.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from operator import attrgetter

VERIFIED = "Verified"
NOT_APPLICABLE = "Not applicable"
NORMAL, CORRECTIVE = "Normal", "Corrective"
TAX_DATE_BASES = ("posting_date", "invoice_date")
SOURCE_KEYS = {
	"Sales Invoice": "sales_invoice",
	"Purchase Invoice": "purchase_invoice",
	"Journal Entry": "journal_entry",
	"Expense Claim": "expense_claim",
}


@dataclass(frozen=True)
class Rule:
	key: str
	value: str
	status: str


@dataclass(frozen=True)
class RuleSet:
	name: str
	code: str
	version: int
	version_type: str
	effective_from: str
	effective_to: str | None
	content_hash: str
	rules: dict[str, Rule] = field(default_factory=dict)
	supersedes: str | None = None

	def rule(self, key: str) -> Rule | None:
		return self.rules.get(key)


class RuleBook:
	"""The published sets of one code. `for_date` returns (set, None) or (None, issue)."""

	def __init__(self, code: str | None, sets: list[RuleSet]):
		self.code = code
		self.sets = {s.name: s for s in sets}
		self._normals = sorted(
			(s for s in sets if s.version_type == NORMAL), key=attrgetter("effective_from")
		)

	def for_date(self, day: str) -> tuple[RuleSet | None, str | None]:
		if not self.code:
			return None, "rule_set_not_configured"
		covering = [s for s in self._normals if s.effective_from <= day <= (self._end(s) or day)]
		if not covering:
			return None, "rule_set_missing"
		if len(covering) > 1:
			return None, "rule_set_conflict"
		current, end = covering[0], self._end(covering[0])
		while True:
			corrections = [s for s in self.sets.values() if s.supersedes == current.name]
			if len(corrections) > 1:
				return None, "rule_set_conflict"
			if not corrections:
				return current, None
			correction = corrections[0]
			correction_end = correction.effective_to or end
			if not correction.effective_from <= day <= (correction_end or day):
				return current, None
			current, end = correction, correction_end

	def _end(self, rule_set: RuleSet) -> str | None:
		"""Last day of a normal version: its Effective To, or the day before the next normal version starts."""
		if rule_set.effective_to:
			return rule_set.effective_to
		later = [s.effective_from for s in self._normals if s.effective_from > rule_set.effective_from]
		return str(date.fromisoformat(min(later)) - timedelta(days=1)) if later else None


def resolve(line, book: RuleBook, from_date: str, to_date: str) -> RuleSet | None:
	"""Set the tax date and the rule set of a line; return the set to classify with, or None with
	`line.rule_issue` set."""
	source = SOURCE_KEYS.get(line.voucher_type)
	if not source:
		return _issue(line, "tax_date_source_unknown")
	posting_set, issue = book.for_date(line.posting_date)
	if issue:
		return _issue(line, issue)
	basis_key = f"tax_date_basis:{source}"
	basis, issue = verified_value(posting_set, basis_key)
	if issue:
		return _issue(line, issue)
	if basis not in TAX_DATE_BASES:
		return _issue(line, f"rule_invalid:{basis_key}")
	line.tax_date_basis = basis
	line.tax_date = getattr(line, basis) or None
	if not line.tax_date:
		return _issue(line, "tax_date_undetermined")
	if not from_date <= line.tax_date <= to_date:
		return _issue(line, "tax_date_outside_period")
	tax_set, issue = book.for_date(line.tax_date)
	if issue:
		return _issue(line, issue)
	if tax_set.name != posting_set.name and verified_value(tax_set, basis_key)[0] != basis:
		return _issue(line, "rule_transition_review")
	line.rule_set = tax_set.name
	return tax_set


def verified_value(rule_set: RuleSet, key: str) -> tuple[str | None, str | None]:
	"""The value of a Verified rule, or (None, issue) when it is missing or not verified."""
	rule = rule_set.rule(key)
	if not rule:
		return None, f"rule_missing:{key}"
	if rule.status != VERIFIED:
		return None, f"rule_unverified:{key}"
	return rule.value, None


def _issue(line, issue: str) -> None:
	"""Record why the line cannot be classified; the caller gets no rule set."""
	line.rule_issue = issue
	return None
