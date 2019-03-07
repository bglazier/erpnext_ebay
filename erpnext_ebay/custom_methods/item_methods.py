# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""
from __future__ import unicode_literals

import frappe


def item_onload(doc, _method):
    """On item load docevent."""
    item_onload_ebay(doc)

# ********************************************************************
# eBay update for Online Selling Item
# ********************************************************************


def item_onload_ebay(doc):
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
                    delete_list.append(i)
            for i in reversed(delete_list):
                del doc.online_selling_items[i]

        Platform.item_onload(doc, subtypes)

        try:
            doc.save()
        except frappe.ValidationError:
            frappe.msgprint(
                'Item does not validate - unable to save eBay updates')
