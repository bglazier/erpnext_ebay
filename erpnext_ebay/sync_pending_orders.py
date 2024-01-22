# -*- coding: utf-8 -*-
"""Create entries for pending (active) orders. These are orders that are
neither Completed (paid) or Cancelled.
Uses the Trading API as the Fulfillment API only includes Completed orders.
"""

import datetime
import operator

import frappe

from .ebay_get_requests import (
    get_orders, get_shipping_service_descriptions, ConnectionError)
from .ebay_constants import (
    EBAY_TRANSACTION_SITE_IDS, EBAY_TRANSACTION_SITE_NAMES
)
from .sync_orders_rest import sanitize_country_code


# Maximum number of days that should be polled
MAX_DAYS = 90

# Fields to use to get addresses
ADDRESS_FIELDS = ('Name', 'Street1', 'Street2', 'CityName',
                  'StateOrProvince', 'PostalCode', 'CountryName')

@frappe.whitelist()
def sync_pending_orders(site_id=None, num_days=None):
    """
    Pulls the latest orders from eBay. Creates 'eBay Pending Order' for
    incomplete orders (OrderStatus 'Active'). These are orders that
    have neither been paid nor cancelled.
    By default (site_id = None or -1), checks orders from all eBay sites.
    If site_id is specified, only orders from that site are used.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)

    if not frappe.db.get_single_value('eBay Manager Settings', 'enable_ebay'):
        frappe.throw('eBay disabled')

    # Prepare parameters
    if site_id is None or int(site_id) == -1:
        ebay_site_name = None
    else:
        site_id = int(site_id)
        ebay_site_name = EBAY_TRANSACTION_SITE_IDS[site_id]

    if num_days is None:
        num_days = int(
            frappe.get_value('eBay Manager Settings', 'eBay Manager Settings',
                             'ebay_pending_sync_days')
        )

    frappe.msgprint('Syncing eBay orders...')

    # Load orders from Ebay (retry up to three times)
    i = 0
    while True:
        try:
            orders, num_days = get_orders(order_status='Active',
                                          num_days=num_days)
        except ConnectionError:
            if i > 2:
                raise
        else:
            break
        i = i + 1

    # Build list of existing eBay Pending Orders
    existing_order_dict = {
        x.ebay_order_id: x.name for x in frappe.get_all(
            'eBay Pending Order',
            fields=['name', 'ebay_order_id']
        )
    }

    for order in orders:
        # Identify the eBay site on which the item was listed.
        # Filter if we have a site_id set.
        order_site_name = order[
            'TransactionArray']['Transaction'][0]['Item']['Site']
        # If we have a site_id, skip if not this site_id
        if ebay_site_name and (ebay_site_name != order_site_name):
            continue

        ebay_order_id = order['OrderID']
        existing_order = existing_order_dict.get(ebay_order_id, False)

        ship_add = order['ShippingAddress']
        shipping = order['ShippingServiceSelected']
        if all(x is None for x in ship_add.values()):
            # No address
            shipping_address = 'No shipping address'
        else:
            shipping_address = '\n'.join(
                    (ship_add.get(k) or '')
                    for k in ADDRESS_FIELDS if ship_add.get(k))

        # Get shipping strings
        order_site_id = EBAY_TRANSACTION_SITE_NAMES[order_site_name]
        shipping_string = get_shipping_service_descriptions(order_site_id).get(
            shipping['ShippingService'], shipping['ShippingService']
        )
        if 'ShippingServiceCost' in shipping:
            shipping_cost = float(shipping['ShippingServiceCost']['value'])
        else:
            shipping_cost = 0.0

        order_dict = {
            'last_modified': datetime.datetime.strptime(
                order['CheckoutStatus']['LastModifiedTime'],
                '%Y-%m-%dT%H:%M:%S.%fZ'),
            'created_time': datetime.datetime.strptime(
                order['CreatedTime'], '%Y-%m-%dT%H:%M:%S.%fZ'),
            'ebay_order_id': ebay_order_id,
            'ebay_site': order_site_name,
            'buyer_username': order['BuyerUserID'],
            'shipping_address': shipping_address,
            'country': sanitize_country_code(ship_add.get('Country')),
            'currency': order['AmountPaid']['_currencyID'],
            'shipping_type': shipping_string,
            'shipping_cost': shipping_cost,
            'total_cost': float(order['Total']['value']),
        }

        # Now add items
        items = []
        transactions = order['TransactionArray']['Transaction']
        for transaction in transactions:
            sku = transaction['Item'].get('SKU', None)
            if not frappe.db.exists('Item', sku):
                # This is not a valid item code; skip this item
                continue
            items.append({
                'item_code': sku,
                'qty': int(transaction['QuantityPurchased']),
                'price': float(transaction['TransactionPrice']['value']),
                'ebay_id': transaction['Item']['ItemID']
            })

        if not items:
            # No valid items on this pending order; skip it
            continue

        # Sort item codes for later comparisons
        items.sort(key=operator.itemgetter('item_code'))

        if existing_order:
            # If there is an existing order, see if the quantities or item
            # codes have changed.
            existing_doc = frappe.get_doc('eBay Pending Order',
                                          existing_order)
            order_details = [(x.item_code, x.qty) for x in existing_doc.items]
            item_details = [(x['item_code'], x['qty']) for x in items]
            if order_details == item_details:
                # The existing orders match. Update any values that
                # have changed.
                changed = False
                for key, value in order_dict.items():
                    if getattr(existing_doc, key) != value:
                        setattr(existing_doc, key, value)
                        changed = True
                for existing_item, order_item in zip(existing_doc.items, items):
                    for key, value in order_item.items():
                        if getattr(existing_item, key) != value:
                            setattr(existing_item, key, value)
                            changed = True
                if changed:
                    existing_doc.save()
                # We have dealt with the existing order, so remove it from
                # the dictionary
                del existing_order_dict[ebay_order_id]
            else:
                # The item codes and quantities do not match
                # Delete the existing doc
                frappe.delete_doc('eBay Pending Order', existing_order)
                del existing_order_dict[ebay_order_id]
                existing_order = False

        if not existing_order:
            # Either there was no existing doc, or we deleted/updated it
            # Create a new eBay Pending Order
            order_dict['items'] = items
            order_dict['doctype'] = 'eBay Pending Order'
            pending_order_doc = frappe.get_doc(order_dict)
            pending_order_doc.insert()

    # Remove any remaining eBay Pending Order documents
    for docname in existing_order_dict.values():
        frappe.delete_doc('eBay Pending Order', docname)

    frappe.msgprint('Finished.')
