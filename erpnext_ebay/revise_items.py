# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

import json
import math
import sys
import os.path
from collections.abc import Sequence

import frappe

from erpnext_ebay.utils.general_utils import chunker
from erpnext_ebay.ebay_revise_requests import (
    revise_inventory_status, relist_item, end_items)

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


class eBayPartialFailure(frappe.ValidationError):
    pass


def revise_ebay_prices(price_data, print=print, item_codes=None, **kwargs):
    """Revises multiple eBay prices. Attempts to pack price updates into as few
    ReviseInventoryStatus calls as possible.
    Accepts a list of item codes which should match the length of price_data.
    Accepts a list of tuples, each of which contains:
      - ebay_id
      - new_price
      - optional extra values
    """

    if len(price_data) == 0:
        print('No prices to update!')
        return

    if not item_codes:
        item_codes = [None] * len(price_data)
    elif len(price_data) != len(item_codes):
        frappe.throw('price_data and item_codes must be the same length!')

    item_data = [
        (ebay_id, new_price, None)
        for (ebay_id, new_price, *_) in price_data
    ]

    revise_ebay_inventory(item_data, print=print,
                          item_codes=item_codes, **kwargs)


def revise_ebay_quantities(qty_data, print=print, item_codes=None, **kwargs):
    """Revises multiple eBay quantities. Attempts to pack quantity updates
    into as few ReviseInventoryStatus calls as possible.
    Accepts a list of item codes which should match the length of qty_data.
    Accepts a list of tuples, each of which contains:
      - ebay_id
      - new_qty
      - optional extra values
    """

    if len(qty_data) == 0:
        print('No quantities to update!')
        return

    if not item_codes:
        item_codes = [None] * len(qty_data)
    elif len(qty_data) != len(item_codes):
        frappe.throw('qty_data and item_codes must be the same length!')

    revise_listings = []
    revise_item_codes = []
    end_listings = []
    end_item_codes = []
    for (ebay_id, new_qty, *_), item_code in zip(qty_data, item_codes):
        if new_qty == 0:
            end_listings.append((ebay_id, 'NotAvailable'))
            end_item_codes.append(item_code)
        else:
            revise_listings.append((ebay_id, None, new_qty))
            revise_item_codes.append(item_code)

    # First revise listing quantities
    if revise_listings:
        revise_ebay_inventory(revise_listings, print=print,
                              item_codes=revise_item_codes, **kwargs)

    # Then end listings
    if end_listings:
        end_ebay_listings(end_listings, print=print,
                          item_codes=end_item_codes, **kwargs)


def revise_ebay_inventory(item_data, print=print, item_codes=None,
                          error_log=None, retries=1, **kwargs):
    """Revises multiple eBay prices and quantities. Attempts to pack
    price updates into as few ReviseInventoryStatus calls as possible.
    Accepts a list of tuples of the form (ebay_id, price, qty).
    Accepts a list of item codes being revised.
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
            item_dict['Quantity'] = int(qty)
        items.append(item_dict)

    prev_percent = -1000.0
    n_items = len(items)
    n_chunks = ((n_items - 1) // CHUNK_SIZE) + 1  # Number of chunks of 4 items
    print('n_chunks: ', n_chunks)

    # Filter out empty item_codes
    item_codes = [x for x in (item_codes or []) if x]
    if item_codes:
        run_before_hooks = frappe.get_hooks(
            "erpnext_ebay_before_revise_ebay_inventory") or []
        for method_name in run_before_hooks:
            frappe.get_attr(method_name)(item_codes)

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
            if i:
                print('Retrying transaction...')
            try:
                revise_inventory_status(chunked_items)
            except Exception as e:
                if error_log is not None:
                    error_log.append(f'revise_ebay_inventory exception: {e}')
                last_exc = e
            else:
                # Success
                break
        else:
            if error_log is not None:
                # Carry on
                error_log.append(
                    f'revise_ebay_inventory failed after {retries} retries')
            else:
                # Give up here
                raise last_exc

    print(' - 100% complete.')


@frappe.whitelist()
def client_revise_ebay_item(item_data, item_code=None):
    """Revise an item's price and/or qty from the JS front-end.
    Will end a listing if the qty is set to zero.
    """

    # Whitelisted function; check permissions
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('Need write permissions on eBay Manager!',
                     frappe.PermissionError)

    if isinstance(item_data, str):
        item_data = json.loads(item_data)
    if not isinstance(item_data, dict):
        frappe.throw('Invalid format for item_data!')

    qty = item_data.get('qty')
    if qty == 0:
        item = (item_data['ebay_id'], 'NotAvailable')
        end_ebay_listings([item], item_codes=[item_code])
    else:
        item = item_data['ebay_id'], item_data.get('price'), qty
        revise_ebay_inventory([item], item_codes=[item_code])


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


def end_ebay_listings(listings, print=print, item_codes=None, **kwargs):
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


    # Filter out empty item_codes
    item_codes = [x for x in (item_codes or []) if x]
    if item_codes:
        run_before_hooks = frappe.get_hooks(
            "erpnext_ebay_before_end_ebay_listings") or []
        for method_name in run_before_hooks:
            frappe.get_attr(method_name)(item_codes)

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
def client_end_ebay_listings(ebay_ids, item_codes=None):
    """End listings from the JS front-end."""

    # Whitelisted function; check permissions
    if not frappe.has_permission('eBay Manager', 'write'):
        frappe.throw('Need write permissions on eBay Manager!',
                     frappe.PermissionError)

    if isinstance(ebay_ids, str):
        ebay_ids = json.loads(ebay_ids)
    if not isinstance(ebay_ids, list):
        frappe.throw('Invalid ebay_ids format!')

    if isinstance(item_codes, str):
        item_codes = json.loads(item_codes)
    if not isinstance(item_codes, list):
        frappe.throw('Invalid item_codes format!')

    listings = [(x, 'NotAvailable') for x in ebay_ids]

    end_ebay_listings(listings, item_codes=item_codes)
