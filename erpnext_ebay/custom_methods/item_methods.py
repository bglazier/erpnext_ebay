# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""
from __future__ import unicode_literals

import frappe
from string import ascii_letters, digits

whitelist = set(ascii_letters + digits + '_')


def item_onload(doc, _method):
    """On item load docevent."""
    item_onload_platform(doc)


def item_update(doc, _method):
    """On item update docevent."""
    item_update_platform(doc)

# ********************************************************************
# eBay update for Online Selling Item
# ********************************************************************


def item_onload_platform(doc):
    """Get the latest active listings for this item."""
    from erpnext_ebay.online_selling import platform_dict

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


def item_update_platform(doc):
    """Check for updates in the document."""
    from erpnext_ebay.online_selling import platform_dict

    for online_selling_item in doc.online_selling_items:
        Platform = platform_dict[online_selling_item.selling_platform]
        subtype = online_selling_item.selling_subtype
        # Get fields that we check, in this Online Selling Platform
        platform_update_fields = frappe.get_value(
            'Online Selling Platform',
            online_selling_item.selling_platform,
            'update_fields')
        # Parse out update_fields against a whitelist of A..Za..z0..9_
        update_fields = [
            ''.join([c for c in x.strip() if c in whitelist])
            for x in platform_update_fields.split(',')]
        update_dict = {}
        # Check each field for changes
        for update_field in update_fields:
            db_field = frappe.db.get_value('Item', doc.name, update_field)
            doc_field = online_selling_item.get(update_field)
            if db_field != doc_field:
                update_dict[update_field] = doc_field

        if update_dict:
            try:
                Platform.item_update(doc, subtype, update_dict)
            except Exception:
                import traceback
                traceback.print_exc()
                frappe.msgprint(
                    'Error in Online Selling Platform\n' + traceback.format_exc())
