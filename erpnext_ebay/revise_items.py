# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

import json
import math
import sys
import os.path

import frappe

from erpnext_ebay.ebay_revise_requests import (
    revise_inventory_status, end_items)

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


def chunker(seq, size):
    """Collect data into fixed-length chunks. From answer by nosklo in
    https://stackoverflow.com/questions/434287/
    """
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def revise_ebay_prices(price_data, print=print):
    """Revises multiple eBay prices. Attempts to pack price updates into as few
    ReviseInventoryStatus calls as possible.
    Accepts a list of tuples, each of which contains:
      - ebay_id
      - new_price
      - optional extra values
    """

    if len(price_data) == 0:
        print('No prices to update!')
        return

    item_data = [
        (ebay_id, new_price, None)
        for (ebay_id, new_price, *_) in price_data
    ]

    revise_ebay_inventory(item_data, print=print)


def revise_ebay_quantities(qty_data, print=print):
    """Revises multiple eBay quantities. Attempts to pack quantity updates
    into as few ReviseInventoryStatus calls as possible.
    Accepts a list of tuples, each of which contains:
      - ebay_id
      - new_qty
      - optional extra values
    """

    if len(qty_data) == 0:
        print('No quantities to update!')
        return

    revise_listings = []
    end_listings = []
    for ebay_id, new_qty, *_ in qty_data:
        if new_qty == 0:
            end_listings.append((ebay_id, 'NotAvailable'))
        else:
            revise_listings.append((ebay_id, None, new_qty))

    # First revise listing quantities
    if revise_listings:
        revise_ebay_inventory(revise_listings, print=print)

    # Then end listings
    if end_listings:
        end_ebay_listings(end_listings, print=print)


def revise_ebay_inventory(item_data, print=print):
    """Revises multiple eBay prices and quantities. Attempts to pack
    price updates into as few ReviseInventoryStatus calls as possible.
    Accepts a list of tuples of the form (ebay_id, price, qty).
    If either price or qty is None, the price or qty, respectively,
    is not changed.
    """

    CHUNK_SIZE = 4

    items = []
    for ebay_id, price, qty in item_data:
        if price is None and qty is None:
            continue
        item_dict = {'ItemID': ebay_id}
        if price is not None:
            item_dict['StartPrice'] = price
        if qty is not None:
            item_dict['Quantity'] = qty
        items.append(item_dict)

    prev_percent = -1000.0
    n_items = len(items)
    n_chunks = ((n_items - 1) // CHUNK_SIZE) + 1  # Number of chunks of 4 items
    print('n_chunks: ', n_chunks)

    if n_items == 0:
        print('No items to update!')
        return

    for i, chunked_items in enumerate(chunker(items, CHUNK_SIZE)):
        percent = math.floor(100.0 * i / n_chunks)
        if percent - prev_percent > 9.9:
            print(f' - {int(percent)}% complete...')
        prev_percent = percent

        # Submit the updates for these items.
        revise_inventory_status(chunked_items)

    print(' - 100% complete.')


@frappe.whitelist()
def client_revise_ebay_item(item_data):
    """Revise an item's price and/or qty from the JS front-end."""

    # Whitelisted function; check permissions
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('Need write permissions on eBay Manager!',
                     frappe.PermissionError)

    item_data = json.loads(item_data)
    item = item_data['ebay_id'], item_data.get('price'), item_data.get('qty')
    revise_ebay_inventory([item])


def end_ebay_listings(listings, print=print):
    """Ends a number of eBay listings.

    Arguments:
      - listings: a sequence of (ItemID, EndingReason) tuples.

    EndingReasons can be:
      - Incorrect (start price or reserve price is incorrect)
      - LostOrBroken (item is lost or broken)
      - NotAvailable (item is no longer available for sale)
      - OtherListingError (error other than the start or reserve price)
      - SellToHighBidder (only for Auctions)
    """

    CHUNK_SIZE = 10

    items = [
        {'ItemID': ebay_id, 'EndingReason': reason}
        for ebay_id, reason in listings
    ]

    prev_percent = -1000.0
    n_items = len(items)
    n_chunks = ((n_items - 1) // CHUNK_SIZE) + 1  # Number of chunks of 4 items
    print('n_chunks: ', n_chunks)

    if n_items == 0:
        print('No listings to end!')
        return

    for i, chunked_items in enumerate(chunker(items, CHUNK_SIZE)):
        percent = math.floor(100.0 * i / n_chunks)
        if percent - prev_percent > 9.9:
            print(f' - {int(percent)}% complete...')
        prev_percent = percent

        # Submit the updates for these items.
        end_items(chunked_items)

    print(' - 100% complete.')
