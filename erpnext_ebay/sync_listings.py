# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import print_function

import bleach
from datetime import datetime, timedelta

import pytz
import frappe

from ebay_requests import get_listings
from ebay_constants import LISTING_DURATION_TOKEN_DICT


def get_active_listings():
    """Returns a list of active listings from the eBay TradingAPI."""

    outer_opts = {}  # {'DetailLevel': 'ReturnAll'}
    inner_opts = {'Include': 'true',
                  'IncludeWatchCount': 'true'}

    listings, summary = get_listings('ActiveList', outer_opts, inner_opts)

    return listings


@frappe.whitelist()
def sync(site_id=3):
    """
    Updates Online Selling Items for eBay across the site.
    """

    # This is a whitelisted function; check permissions.
    roles = ('System Manager', 'Accounts Manager')
    user_roles = frappe.get_roles(frappe.session.user)
    if not any([x in user_roles for x in roles]):
        return frappe.PermissionError(
            'Only Account Managers/System Managers '
            + 'can update the eBay categories.')
    frappe.msgprint('Syncing eBay listings...')
    # Load orders from Ebay
    listings = get_active_listings()

    # Find what subtypes we support for this siteid
    subtypes = frappe.get_all(
        'Online Selling Subtype',
        fields=['name', 'subtype_code', 'tax_rate'],
        filters={'selling_platform': 'eBay',
                 'subtype_id': site_id})

    subtype_dict = {x['subtype_code']: x['name'] for x in subtypes}
    subtype_tax_dict = {x['name']: x['tax_rate'] for x in subtypes}

    # Find our BuyItNow and Auction subtypes

    print('finding listings')
    # Find all existing Online Selling Items that match eBay and our subtypes
    all_selling_items = []
    for subtype in subtype_dict.values():
        subtype_items = frappe.get_all('Online Selling Item', filters={
            'selling_platform': 'eBay',
            'selling_subtype': subtype})
        all_selling_items.extend([x['name'] for x in subtype_items])

    print('deleting listings')
    # Delete all old listing entries matching eBay with this siteid
    for selling_item in all_selling_items:
        frappe.delete_doc('Online Selling Item', selling_item)

    print('getting list of item codes')
    # Get a list of all item codes
    item_codes = set(x['name'] for x in frappe.get_all('Item'))

    no_SKU_items = []
    not_found_SKU_items = []
    unsupported_listing_type = []

    print('looping over items')
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
        # Find subtype
        subtype = subtype_dict[listing['ListingType']]

        # Get price and currency
        price = listing['SellingStatus']['CurrentPrice']['value']
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

        # Sanitize web link
        web_link = '<a href="{link}">{link}</a>'.format(
            link=listing['ListingDetails']['ViewItemURL'])
        web_link = bleach.clean(
            web_link, tags=['a'], attributes={'a': ['href']}, styles=[],
            strip=True, strip_comments=True)

        # Create listing
        new_listing = frappe.get_doc({
            'doctype': 'Online Selling Item',
            "parent": item_code,
            "parentfield": "online_selling_items",
            "parenttype": "Item",
            'selling_platform': 'eBay',
            'selling_subtype': subtype,
            'selling_id': listing['ItemID'],
            'qty_listed': listing['Quantity'],
            'qty_available': listing['QuantityAvailable'],
            'price': price,
            'price_currency': price_currency,
            'tax_rate': subtype_tax_dict[subtype],
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
            'title': listing['Title'],
            'ebay_listing_duration': duration_description,
            'ebay_watch_count': listing.get('WatchCount', 0),
            'ebay_question_count': listing.get('QuestionCount', 0),
            'ebay_hit_count': None,  # we can only get this through GetItem
            'website_link': web_link})
        new_listing.insert()
        print('inserted listing')

    frappe.msgprint('{} listings had no SKU'.format(len(no_SKU_items)))
    frappe.msgprint('{} listings had an SKU that could not be found'.format(
        len(not_found_SKU_items)))
    frappe.msgprint('{} listings had an unsupported listing type'.format(
        len(unsupported_listing_type)))

    frappe.db.commit()
    print('done')
