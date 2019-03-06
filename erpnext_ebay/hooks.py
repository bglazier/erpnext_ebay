# -*- coding: utf-8 -*-
from __future__ import unicode_literals

app_name = "erpnext_ebay"
app_title = "Erpnext Ebay"
app_publisher = "Ben Glazier"
app_description = "Ebay Integration"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "ben@benjaminglazier.com"
app_version = "0.0.1"
app_license = "MIT"

#fixtures = ["Custom Field", "Custom Script", "Property Setter", "Print Format"]
# This is only needed for core doctypes
#fixtures = ["Print Format", {
#    "doctype": "Print Format",
#    "filters":    {
#        "name": ["in", ("Receipt of Goods Uni Version", "Data Destruction Certificate")]
#    }
#}]
#fixtures = [
    #"Property Setter", {
        #"doctype": "Property Setter",
        #"filters": {
            #"name": ["in", ("Receipt of Goods-default_print_format",)]}}
#]
fixtures = [
    {
        "doctype": "Online Selling Platform",
        "filters": {"name": "eBay"}
    },
    {
        "doctype": "Online Selling Subtype",
        "filters": {"name": ["LIKE", ("eBay%")]}
    },
    {
        "doctype": "Role",
        "filters": {
            "name": "eBay Manager"
        }
    }
    ]
# Add custom scripts
doctype_js = {
    "Item": "custom_scripts/item.js"
}

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpnext_ebay/css/erpnext_ebay.css"
app_include_js = "/assets/erpnext_ebay/js/erpnext_ebay.js"

# include js, css files in header of web template
# web_include_css = "/assets/erpnext_ebay/css/erpnext_ebay.css"
# web_include_js = "/assets/erpnext_ebay/js/erpnext_ebay.js"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#    "Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "erpnext_ebay.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "erpnext_ebay.install.before_install"
# after_install = "erpnext_ebay.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpnext_ebay.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#     "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#     "Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Sales Invoice": {
        "before_insert":
            "erpnext_ebay.custom_methods.sales_invoice_methods.sales_invoice_before_insert"
    }
}

# Override the 'write_file' event so that we can modify images as
# they are uploaded

write_file = "erpnext_ebay.auto_slideshow.ugs_save_file_on_filesystem_hook"

# Scheduled Tasks
# ---------------

scheduler_events = {
    "all": [
        #"erpnext_ebay.tasks.all"
    ],
    "hourly": [
        #"erpnext_ebay.tasks.hourly"
        "erpnext_ebay.erpnext_ebay.sync_orders.sync"
    ],
    "daily": [
        #"erpnext_ebay.tasks.daily"
        "erpnext_ebay.erpnext_ebay.ebay_active_listings.set_item_ebay_first_listed_date",
        "erpnext_ebay.ebay_categories.category_sync"
    ],
    "weekly": [
        #"erpnext_ebay.tasks.weekly"
    ],
    "monthly": [
        #"erpnext_ebay.tasks.monthly"
    ]
}

# Testing
# -------

# before_tests = "erpnext_ebay.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
#     "frappe.desk.doctype.event.event.get_events": "erpnext_ebay.event.get_events"
# }

