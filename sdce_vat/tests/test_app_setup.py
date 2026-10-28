# Copyright (c) 2026, SDCE VAT Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

import frappe
from frappe.tests import IntegrationTestCase

from sdce_vat import hooks
from sdce_vat.constants import MODULE, VAT_ROLES


class TestAppSetup(IntegrationTestCase):
	"""Phase 1: the app installs as a standard Frappe app with its module and roles."""

	def test_module_belongs_to_app(self):
		self.assertEqual(frappe.db.get_value("Module Def", MODULE, "app_name"), "sdce_vat")

	def test_requires_erpnext(self):
		self.assertIn("erpnext", hooks.required_apps)

	def test_vat_roles_exist_with_desk_access(self):
		for role in VAT_ROLES:
			with self.subTest(role=role):
				self.assertTrue(frappe.db.exists("Role", role))
				self.assertEqual(frappe.db.get_value("Role", role, ["desk_access", "disabled"]), (1, 0))

	def test_fixture_roles_match_constants(self):
		fixture = hooks.fixtures[0]
		self.assertEqual(fixture["dt"], "Role")
		self.assertEqual(sorted(fixture["filters"][0][2]), sorted(VAT_ROLES))

	def test_no_desk_scripts_owned_by_app(self):
		# the app ships code in its repository, never as Client/Server Scripts in the database
		self.assertFalse(frappe.get_all("Client Script", filters={"module": MODULE}, limit=1))
		self.assertFalse(frappe.get_all("Server Script", filters={"module": MODULE}, limit=1))
