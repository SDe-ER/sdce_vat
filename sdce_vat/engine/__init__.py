# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saudi VAT calculation engine.

`compute()` reads the documents of one company and period, classifies every VAT line, places it in a return
field, reconciles it with GL Entry and returns a traceable result. It never writes to the database.

The site entry point is `sdce_vat.engine.run.compute`; the other modules are pure and import no frappe code,
so they also run on exported rows.
"""
