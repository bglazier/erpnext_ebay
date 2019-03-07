# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function

import bleach
from datetime import datetime, timedelta

import pytz
import frappe

from ebay_requests import get_listings, default_site_id
from ebay_constants import LISTING_DURATION_TOKEN_DICT


def get_active_listings():
    """Returns a list of active listings from the eBay TradingAPI."""

    outer_opts = {}  # {'DetailLevel': 'ReturnAll'}
    inner_opts = {'Include': 'true',
                  'IncludeWatchCount': 'true'}

    listings, summary = get_listings('ActiveList', outer_opts, inner_opts)

    return listings


def get_subtype_dicts(site_id):
    """Get the subtype_dict of listing types and the subtype_tax_dict
    of tax rates for this site_id.
    """
    subtypes = frappe.get_all(
        'Online Selling Subtype',
        fields=['name', 'subtype_code', 'tax_rate'],
        filters={'selling_platform': 'eBay',
                 'subtype_id': site_id})

    subtype_dict = {x['subtype_code']: x['name'] for x in subtypes}
    subtype_tax_dict = {x['name']: x['tax_rate'] for x in subtypes}

    return subtype_dict, subtype_tax_dict


@frappe.whitelist()
def sync(site_id=default_site_id):
    """
    Updates Online Selling Items for eBay across the site.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay listings...')
    # Load orders from Ebay
    listings = get_active_listings()

    # Get subtype dicts for this site_id
    subtype_dict, subtype_tax_dict = get_subtype_dicts(site_id)

    # Find our BuyItNow and Auction subtypes

    # Find all existing Online Selling Items that match eBay and our subtypes
    all_selling_items = []
    for subtype in subtype_dict.values():
        subtype_items = frappe.get_all('Online Selling Item', filters={
            'selling_platform': 'eBay',
            'selling_subtype': subtype})
        all_selling_items.extend([x['name'] for x in subtype_items])

    # Delete all old listing entries matching eBay with this site_id
    for selling_item in all_selling_items:
        frappe.delete_doc('Online Selling Item', selling_item)

    # Get a list of all item codes
    item_codes = set(x['name'] for x in frappe.get_all('Item'))

    no_SKU_items = []
    not_found_SKU_items = []
    unsupported_listing_type = []

    for listing in listings:
        # Loop over all listings
        if 'SKU' not in listing:
            # This item has no SKU
            no_SKU_items.append(listing)
            continue
        item_code = listing['SKU']
        if item_code not in item_codes:
            # This item does not exist!
            not_found_SKU_items.append(listing)
            continue
        if listing['ListingType'] not in subtype_dict:
            # This listing type is not supported?
            unsupported_listing_type.append(listing)
            continue

        print(item_code)
        new_listing = create_ebay_online_selling_item(
            listing, item_code, site_id, subtype_dict, subtype_tax_dict)
        new_listing.insert()

    frappe.msgprint('{} listings had no SKU'.format(len(no_SKU_items)))
    frappe.msgprint('{} listings had an SKU that could not be found'.format(
        len(not_found_SKU_items)))
    frappe.msgprint('{} listings had an unsupported listing type'.format(
        len(unsupported_listing_type)))

    frappe.db.commit()


def create_ebay_online_selling_item(listing, item_code=None,
                                    site_id=None,
                                    subtype_dict=None,
                                    subtype_tax_dict=None):
    """Convert results from GetMyeBaySelling or GetItem to an
    Online Selling Item which is ready for insertion.
    """

    if subtype_dict is None or subtype_tax_dict is None:
        if site_id is None:
            raise ValueError('Must provide a site_id if not providing '
                             + 'subtype_dict and subtype_tax_dict!')
        subtype_dict, subtype_tax_dict = get_subtype_dicts(site_id)

    # Find subtype
    try:
        subtype = subtype_dict[listing['ListingType']]
    except KeyError:
        frappe.msgprint(
            'eBay listing of type {} is not handled by '.format(
                listing['ListingType'])
            + 'the currently available subtypes')
        return None

    # Get price and currency
    price = float(listing['SellingStatus']['CurrentPrice']['value'])
    price_currency = listing['SellingStatus']['CurrentPrice']['_currencyID']

    # Calculate dates and times
    days, duration_description = LISTING_DURATION_TOKEN_DICT[
        listing['ListingDuration']]
    gmt_start_datetime = datetime.strptime(
        listing['ListingDetails']['StartTime'],
        '%Y-%m-%dT%H:%M:%S.%fZ')
    # Convert eBay GMT time to local time zone:
    # - convert naive datetime to GMT-aware datetime
    # - change timezone to local
    # - convert local-aware datetime to naive datetime again
    start_datetime = (
        pytz.timezone('GMT')
        .localize(gmt_start_datetime)
        .astimezone(
            pytz.timezone(frappe.utils.get_time_zone()))
        .replace(tzinfo=None)
        )
    if days is not None:
        end_datetime = start_datetime + timedelta(days=days)
    else:
        end_datetime = None

    # Sanitize URL
    selling_url = '<a href="{link}">{link}</a>'.format(
        link=listing['ListingDetails']['ViewItemURL'])
    selling_url = bleach.clean(
        selling_url, tags=['a'], attributes={'a': ['href']}, styles=[],
        strip=True, strip_comments=True)

    # HitCount if available (only GetItem, not GetMyeBaySelling)
    hit_count = listing.get('HitCount', 0)

    # Quantity (listed) and quantity sold
    qty_listed = int(listing['Quantity'])
    qty_sold = int(listing['SellingStatus'].get('QuantitySold', 0))

    # Create listing
    new_listing = {
        'selling_platform': 'eBay',
        'selling_subtype': subtype,
        'selling_id': listing['ItemID'],
        'qty_listed': qty_listed,
        'qty_available': qty_listed - qty_sold,
        'price_rate': price,
        'price_currency': price_currency,
        'tax_rate': subtype_tax_dict[subtype],
        'start_datetime': start_datetime,
        'end_datetime': end_datetime,
        'title': listing['Title'],
        'ebay_listing_duration': duration_description,
        'ebay_watch_count': int(listing.get('WatchCount', 0)),
        'ebay_question_count': int(listing.get('QuestionCount', 0)),
        'ebay_hit_count': hit_count,
        'selling_url': selling_url}

    # If we have been given an item code, add doctype/parent fields to allow
    # direct insertion into the database, and create the document
    if item_code is not None:
        new_listing.update({
            'doctype': 'Online Selling Item',
            'parent': item_code,
            'parentfield': 'online_selling_items',
            'parenttype': 'Item'})
        new_listing = frappe.get_doc(new_listing)

    return new_listing
