# -*- coding: utf-8 -*-
# Copyright (c) 2015, Ben Glazier and contributors
# For license information, please see license.txt


import frappe
from frappe.model.document import Document


@frappe.whitelist()
def clear_awaiting_garagesale():
    """Clear the 'Awaiting Garagesale' status from all items."""

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('You do not have permission to access eBay Manager',
                     frappe.PermissionError)

    frappe.db.sql("""
        UPDATE `tabItem`
        SET ebay_id = NULL
        WHERE ebay_id = 'Awaiting Garagesale';
        """)
    frappe.db.commit()

    return True


class eBayManager(Document):
    pass
