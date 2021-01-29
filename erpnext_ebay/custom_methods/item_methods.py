# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""

import frappe


def item_onload(doc, _method):
    """On item load docevent."""
    item_onload_ebay(doc)


def item_before_save(doc, _method):
    """On item before save docevent."""
    item_before_save_ebay(doc)


# ********************************************************************
# Platform (eBay) update for Online Selling Item
# ********************************************************************


def item_before_save_ebay(doc):
    """Remove any online selling items before selling for platforms
    where this is specified.
    """
    from erpnext_ebay.online_selling import platform_dict

    online_selling_platforms = frappe.get_all(
        'Online Selling Platform', fields=['name', 'selling_platform'])

    platform_set = set()
    for online_selling_platform in online_selling_platforms:
        Platform = platform_dict[online_selling_platform['selling_platform']]
        if Platform.delete_entries_on_item_save:
            platform_set.add(online_selling_platform.name)

    delete_list = []
    for i, osi_item in enumerate(doc.online_selling_items):
        if osi_item.selling_platform in platform_set:
            delete_list.append((i, osi_item.name))
    for i, osi_name in reversed(delete_list):
        frappe.delete_doc('Online Selling Item', osi_name,
                          ignore_permissions=True)
        del doc.online_selling_items[i]


def item_onload_ebay(doc):
    """Get the latest active listings for this item."""
    from erpnext_ebay.online_selling import platform_dict

    # Check if we have a role that should not run the platform onload event
    excluded_roles = frappe.get_hooks('no_online_selling_roles') or []

    if frappe.session.user == 'Administrator':
        # Administrator has all roles; only exclude if 'Administrator'
        # explicitly in excluded roles
        if 'Administrator' in excluded_roles:
            return
    else:
        # Not administrator: check if we have _any_ excluded roles
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
                filters={'selling_platform': online_selling_platform.name})

        if Platform.delete_entries_on_item_onload:
            delete_list = []
            for i, osi_item in enumerate(doc.online_selling_items):
                if osi_item.selling_platform == online_selling_platform.name:
                    delete_list.append((i, osi_item.name))
            for i, osi_name in reversed(delete_list):
                frappe.delete_doc('Online Selling Item', osi_name,
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


@frappe.whitelist()
def item_platform_async(item_code):
    """Return any Online Selling Items for this item code acquired
    asynchronously via JS.
    """
    from erpnext_ebay.online_selling import platform_dict

    # Whitelisted function; check permissions
    if not frappe.has_permission('Item', 'read'):
        frappe.throw('Need read permissions on Item!',
                     frappe.PermissionError)

    # Check if we have a role that should not run the platform async event
    excluded_roles = frappe.get_hooks('no_online_selling_roles') or []

    if frappe.session.user == 'Administrator':
        # Administrator has all roles; only exclude if 'Administrator'
        # explicitly in excluded roles
        if 'Administrator' in excluded_roles:
            return
    else:
        # Not administrator: check if we have _any_ excluded roles
        roles = frappe.get_roles(frappe.session.user)
        excluded_roles = frappe.get_hooks('no_online_selling_roles') or []
        for excluded_role in excluded_roles:
            if excluded_role in roles:
                return

    online_selling_platforms = frappe.get_all(
        'Online Selling Platform', fields=['name', 'selling_platform'])

    entries = []
    for online_selling_platform in online_selling_platforms:
        Platform = platform_dict[online_selling_platform['selling_platform']]

        subtypes = frappe.get_all(
                'Online Selling Subtype',
                fields=['name', 'selling_subtype'],
                filters={'selling_platform': online_selling_platform.name})

        try:
            entries.extend(Platform.item_async_entries(item_code, subtypes))
        except Exception:
            import traceback
            traceback.print_exc()
            frappe.msgprint(
                'Error in Online Selling Platform\n' + traceback.format_exc())
            return

    return entries
