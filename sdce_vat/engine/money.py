# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Money helpers: every amount in the engine is a Decimal; floats never enter a total."""

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value) -> Decimal:
	"""Convert a database or user value to Decimal without binary float error."""
	if value is None or value == "":
		return ZERO
	if isinstance(value, Decimal):
		return value
	if isinstance(value, float):
		# repr gives the shortest string that round-trips, e.g. 0.1 -> "0.1"
		return Decimal(repr(value))
	return Decimal(str(value))


def q2(value) -> Decimal:
	"""Round to halalas (0.01), half up."""
	return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def total(values) -> Decimal:
	return q2(sum((q2(v) for v in values), ZERO))
