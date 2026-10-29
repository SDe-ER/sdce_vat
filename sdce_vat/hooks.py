app_name = "sdce_vat"
app_title = "SDCE VAT"
app_publisher = "SDCE VAT Contributors"
app_description = "Saudi VAT return preparation, review, approval and filing records for ERPNext"
app_email = ""
app_license = "gpl-3.0"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "sdce_vat",
# 		"logo": "/assets/sdce_vat/logo.png",
# 		"title": "SDCE VAT",
# 		"route": "/sdce_vat",
# 		"has_permission": "sdce_vat.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/sdce_vat/css/sdce_vat.css"
# app_include_js = "/assets/sdce_vat/js/sdce_vat.js"

# include js, css files in header of web template
# web_include_css = "/assets/sdce_vat/css/sdce_vat.css"
# web_include_js = "/assets/sdce_vat/js/sdce_vat.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "sdce_vat/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "sdce_vat/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "sdce_vat.utils.jinja_methods",
# 	"filters": "sdce_vat.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "sdce_vat.install.before_install"
after_install = "sdce_vat.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "sdce_vat.uninstall.before_uninstall"
# after_uninstall = "sdce_vat.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "sdce_vat.utils.before_app_install"
# after_app_install = "sdce_vat.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "sdce_vat.utils.before_app_uninstall"
# after_app_uninstall = "sdce_vat.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "sdce_vat.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "sdce_vat.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["sdce_vat.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"sdce_vat.tasks.all"
# 	],
# 	"daily": [
# 		"sdce_vat.tasks.daily"
# 	],
# 	"hourly": [
# 		"sdce_vat.tasks.hourly"
# 	],
# 	"weekly": [
# 		"sdce_vat.tasks.weekly"
# 	],
# 	"monthly": [
# 		"sdce_vat.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "sdce_vat.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "sdce_vat.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "sdce_vat.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "sdce_vat.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["sdce_vat.utils.before_request"]
# after_request = ["sdce_vat.utils.after_request"]

# Job Events
# ----------
# before_job = ["sdce_vat.utils.before_job"]
# after_job = ["sdce_vat.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"sdce_vat.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# Fixtures
# --------
# The separate VAT roles (keep in step with sdce_vat.constants.VAT_ROLES), the approval workflow of the Saudi
# VAT Return and the approval workflow of the Saudi VAT Rule Set.

fixtures = [
	{
		"dt": "Role",
		"filters": [["name", "in", ["VAT Preparer", "VAT Reviewer", "VAT Approver", "VAT Rule Maintainer"]]],
	},
	{
		"dt": "Workflow State",
		"filters": [
			[
				"name",
				"in",
				[
					"VAT Draft",
					"VAT Prepared",
					"VAT Reviewed",
					"VAT Approved",
					"VAT Cancelled",
					"Rule Draft",
					"Rule Verified",
					"Rule Published",
					"Rule Cancelled",
				],
			]
		],
	},
	{
		"dt": "Workflow Action Master",
		"filters": [
			[
				"name",
				"in",
				[
					"Prepare VAT Return",
					"Return to Preparer",
					"Review VAT Return",
					"Reject VAT Return",
					"Approve VAT Return",
					"Cancel VAT Return",
					"Verify Rule Set",
					"Return Rule Set to Draft",
					"Publish Rule Set",
					"Cancel Rule Set",
				],
			]
		],
	},
	{
		"dt": "Workflow",
		"filters": [["name", "in", ["Saudi VAT Return Approval", "Saudi VAT Rule Set Approval"]]],
	},
]
