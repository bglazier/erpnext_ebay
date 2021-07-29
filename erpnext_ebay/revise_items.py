# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

import json
import math
import sys
import os.path
from collections.abc import Sequence

import frappe

from erpnext_ebay.ebay_revise_requests import (
    revise_inventory_status, relist_item, end_items)

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


class eBayPartialFailure(frappe.ValidationError):
    pass


def chunker(seq, size):
    """Collect data into fixed-length chunks. From answer by nosklo in
    https://stackoverflow.com/questions/434287/
    """
    return (seq[pos:pos + size] for pos in range(0, len(seq), size))


def revise_ebay_prices(price_data, print=print, **kwargs):
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

    revise_ebay_inventory(item_data, print=print, **kwargs)


def revise_ebay_quantities(qty_data, print=print, **kwargs):
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
        revise_ebay_inventory(revise_listings, print=print, **kwargs)

    # Then end listings
    if end_listings:
        end_ebay_listings(end_listings, print=print, **kwargs)


def revise_ebay_inventory(item_data, print=print, error_log=None,
                          retries=1, **kwargs):
    """Revises multiple eBay prices and quantities. Attempts to pack
    price updates into as few ReviseInventoryStatus calls as possible.
    Accepts a list of tuples of the form (ebay_id, price, qty).
    If either price or qty is None, the price or qty, respectively,
    is not changed.
    Tries each transaction 'retries' times.
    If error_log is supplied, then the process continues on error,
    appending to the error_log.
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
        for i in range(retries):
            try:
                revise_inventory_status(chunked_items)
            except Exception as e:
                error_log.append('revise_ebay_inventory exception: {e}')
            else:
                # Success
                break
            print('Retrying transaction...')
        else:
            if error_log:
                # Carry on
                error_log.append(
                    f'revise_ebay_inventory failed after {retries} retries')
            else:
                # Give up here
                raise

    print(' - 100% complete.')


@frappe.whitelist()
def client_revise_ebay_item(item_data):
    """Revise an item's price and/or qty from the JS front-end.
    Will end a listing if the qty is set to zero.
    """

    # Whitelisted function; check permissions
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('Need write permissions on eBay Manager!',
                     frappe.PermissionError)

    item_data = json.loads(item_data)
    qty = item_data.get('qty')
    if qty == 0:
        item = (item_data['ebay_id'], 'NotAvailable')
        end_ebay_listings([item])
    else:
        item = item_data['ebay_id'], item_data.get('price'), qty
        revise_ebay_inventory([item])


def relist_ebay_item(ebay_id, item_dict=None):
    """Relist an eBay listing."""

    relist_item(ebay_id, item_dict=item_dict)


@frappe.whitelist()
def client_relist_ebay_item(ebay_id, item_dict=None):
    """Relist a fixed-price eBay list from the JS front-end."""

    # Whitelisted function; check permissions
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('Need write permissions on eBay Manager!',
                     frappe.PermissionError)

    if isinstance(item_dict, str):
        item_dict = json.loads(item_dict)

    if not isinstance(item_dict, dict):
        frappe.throw('Invalid format for item_dict!')

    relist_item(ebay_id, item_dict=item_dict)


def end_ebay_listings(listings, print=print, **kwargs):
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
    n_chunks = ((n_items - 1) // CHUNK_SIZE) + 1  # Number of chunks of items
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
        response = end_items(chunked_items)
        print(response)

        print('response[Ack] = ', response['Ack'])
        if response['Ack'] != 'Success':
            print('response not success')
            messages = []
            response_items = response['EndItemResponseContainer']
            if not isinstance(response_items, Sequence):
                response_items = [response_items]
            for item in response_items:
                if 'Errors' not in item:
                    continue
                elif isinstance(item['Errors'], Sequence):
                    errors = item['Errors']
                else:
                    errors = [item['Errors']]
                messages = []
                for e in errors:
                    messages.append(
                        f'{e["SeverityCode"]} code {e["ErrorCode"]} (Item ID '
                        + f'{item["CorrelationID"]}): {e["LongMessage"]}'
                    )
            frappe.throw('\n'.join(messages),
                         exc=eBayPartialFailure)

    print(' - 100% complete.')


@frappe.whitelist()
def client_end_ebay_listings(ebay_ids):
    """End listings from the JS front-end."""

    if isinstance(ebay_ids, str):
        ebay_ids = json.loads(ebay_ids)
    if not isinstance(ebay_ids, list):
        frappe.throw('Invalid ebay_ids format!')

    listings = [(x, 'NotAvailable') for x in ebay_ids]

    end_ebay_listings(listings)
