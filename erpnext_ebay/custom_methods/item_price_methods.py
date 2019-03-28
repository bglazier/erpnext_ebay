# -*- coding: utf-8 -*-
"""Custom methods for Item Price doctype"""
from __future__ import unicode_literals

import frappe


def item_price_on_update(doc, _method):
    """On Item Price load docevent."""
    item_price_on_update_platform(doc)


# ********************************************************************
# eBay update for Online Selling Item
# ********************************************************************

def item_price_on_update_platform(doc):
    """Check for updates in the Item Price."""
    from erpnext_ebay.online_selling import platform_dict

    item_doc = frappe.get_doc('Item', doc.item_code)
    for online_selling_item in item_doc.online_selling_items:
        # Check if we do price updates and we are the right kind of price list
        platform_updates_prices = frappe.get_value(
            'Online Selling Platform',
            online_selling_item.selling_platform,
            'price_list')
        if not platform_updates_prices:
            # This platform does not update prices
            continue
        platform_price_list_rate = frappe.get_value(
            'Online Selling Platform',
            online_selling_item.selling_platform,
            'price_list')
        if doc.price_list != platform_price_list_rate:
            # This is not the right kind of price list
            continue
        Platform = platform_dict[online_selling_item.selling_platform]
        subtype = online_selling_item.selling_subtype
        update_dict = {}
        # Check our price for changes
        db_field = frappe.db.get_value(
            'Item Price', doc.name, 'price_list_rate')
        doc_field = online_selling_item.get('price_rate')
        if db_field != doc_field:
            update_dict['price_list_rate'] = doc_field

        if update_dict:
            try:
                Platform.item_price_update(doc, subtype, update_dict)
            except Exception:
                import traceback
                traceback.print_exc()
                frappe.msgprint(
                    'Error in Online Selling Platform\n'
                    + traceback.format_exc())
