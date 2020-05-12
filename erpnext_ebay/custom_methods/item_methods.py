# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""

import frappe


def item_onload(doc, _method):
    """On item load docevent."""
    item_onload_ebay(doc)

# ********************************************************************
# Platform (eBay) update for Online Selling Item
# ********************************************************************


def item_onload_ebay(doc):
    """Get the latest active listings for this item."""
    from erpnext_ebay.online_selling import platform_dict

    # Check if we have a role that should not run the platform onload event
    if frappe.session.user != 'Administrator':
        # Administrator has all roles
        roles = frappe.get_roles(frappe.session.user)
        excluded_roles = frappe.get_hooks('no_online_selling_roles') or []
        for excluded_role in excluded_roles:
            if excluded_role in roles:
                return

    online_selling_platforms = frappe.get_all(
        'Online Selling Platform', fields=['name', 'selling_platform'])

    for online_selling_platform in online_selling_platforms:
        Platform = platform_dict[online_selling_platform['selling_platform']]

        subtypes = frappe.get_all(
                'Online Selling Subtype',
                fields=['name', 'selling_subtype'],
                filters={'selling_platform': online_selling_platform['name']})

        if Platform.delete_entries_on_item_onload:
            delete_list = []
            for i, si_item in enumerate(doc.online_selling_items):
                if si_item.selling_platform == online_selling_platform['name']:
                    delete_list.append((i, si_item.name))
            for i, si_name in reversed(delete_list):
                frappe.delete_doc('Online Selling Item', si_name,
                                  ignore_permissions=True)
                del doc.online_selling_items[i]

        try:
            Platform.item_onload(doc, subtypes)
        except Exception:
            import traceback
            traceback.print_exc()
            frappe.msgprint(
                'Error in Online Selling Platform\n' + traceback.format_exc())
            doc.online_selling_items = []
