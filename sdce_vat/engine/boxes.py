# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stable identifiers of the ZATCA VAT return fields.

Labels follow the ZATCA "Submit VAT Return" user guide (EN 2026-07-29, AR 2026-08-06). The identifiers never
change; labels may be updated if ZATCA renames a field.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
	id: str
	number: int | None
	label_ar: str
	label_en: str
	is_total: bool = False


SALES_STANDARD = "S01"
SALES_GOVERNMENT_BEARS = "S02"
SALES_ZERO_RATED = "S03"
SALES_EXPORTS = "S04"
SALES_EXEMPT = "S05"
SALES_TOTAL = "S06"
PURCHASES_STANDARD = "P07"
PURCHASES_IMPORT_CUSTOMS = "P08"
PURCHASES_IMPORT_REVERSE_CHARGE = "P09"
PURCHASES_ZERO_RATED = "P10"
PURCHASES_EXEMPT = "P11"
PURCHASES_TOTAL = "P12"
VAT_DUE = "T13"
CORRECTIONS = "T14"
VAT_CREDIT_CARRIED = "T15"
NET_VAT = "T16"

BOXES = (
	Box(SALES_STANDARD, 1, "المبيعات الخاضعة للنسبة الأساسية", "Standard Rated Sales"),
	Box(
		SALES_GOVERNMENT_BEARS,
		2,
		"المبيعات التي تتحمل الدولة ضريبتها",
		"Sales on which the government bears the VAT",
	),
	Box(SALES_ZERO_RATED, 3, "المبيعات المحلية الخاضعة للنسبة الصفرية", "Zero Rated Domestic Sales"),
	Box(SALES_EXPORTS, 4, "الصادرات", "Exports"),
	Box(SALES_EXEMPT, 5, "المبيعات المعفاة", "Exempt Sales"),
	Box(SALES_TOTAL, 6, "إجمالي المبيعات", "Total Sales", is_total=True),
	Box(PURCHASES_STANDARD, 7, "المشتريات الخاضعة للنسبة الأساسية", "Standard Rated Domestic Purchases"),
	Box(
		PURCHASES_IMPORT_CUSTOMS,
		8,
		"الاستيرادات الخاضعة لضريبة القيمة المضافة بالنسبة الأساسية والتي تدفع عند الاستيراد",
		"Imports subject to VAT paid on import",
	),
	Box(
		PURCHASES_IMPORT_REVERSE_CHARGE,
		9,
		"الاستيرادات الخاضعة لضريبة القيمة المضافة التي تطبق عليها آلية الاحتساب العكسي",
		"Imports subject to VAT accounted for through the reverse charge mechanism",
	),
	Box(PURCHASES_ZERO_RATED, 10, "المشتريات الخاضعة للنسبة الصفرية", "Zero Rated Purchases"),
	Box(PURCHASES_EXEMPT, 11, "المشتريات المعفاة", "Exempt Purchases"),
	Box(PURCHASES_TOTAL, 12, "إجمالي المشتريات", "Total Purchases", is_total=True),
	Box(
		VAT_DUE,
		13,
		"إجمالي ضريبة القيمة المضافة المستحقة عن الفترة الضريبية الحالية",
		"Total VAT due for current Period",
		is_total=True,
	),
	Box(
		CORRECTIONS,
		14,
		"تصحيحات من الفترات السابقة (بين ± 5000 ﷼)",
		"Corrections from previous period (between ± 5000)",
	),
	Box(
		VAT_CREDIT_CARRIED,
		15,
		"ضريبة القيمة المضافة التي تم ترحيلها من الفترة / الفترات السابقة",
		"VAT Credit from previous period(s)",
	),
	Box(NET_VAT, 16, "صافي الضريبة المستحقة (أو المستردة)", "Net VAT", is_total=True),
)

BOX_BY_ID = {box.id: box for box in BOXES}
SALES_LINE_BOXES = (SALES_STANDARD, SALES_GOVERNMENT_BEARS, SALES_ZERO_RATED, SALES_EXPORTS, SALES_EXEMPT)
PURCHASE_LINE_BOXES = (
	PURCHASES_STANDARD,
	PURCHASES_IMPORT_CUSTOMS,
	PURCHASES_IMPORT_REVERSE_CHARGE,
	PURCHASES_ZERO_RATED,
	PURCHASES_EXEMPT,
)
LINE_BOXES = SALES_LINE_BOXES + PURCHASE_LINE_BOXES
