# -*- coding: utf-8 -*-

import operator
from datetime import datetime, timedelta

import bleach

import frappe

from .ebay_get_requests import (
    ebay_logger, get_seller_list, get_item, get_shipping_service_descriptions
)
from .ebay_constants import (LISTING_DURATION_TOKEN_DICT, EBAY_SITE_IDS,
                             EBAY_TRANSACTION_SITE_NAMES,
                             EBAY_SITE_DOMAINS, HOME_SITE_ID)

from collections.abc import Sequence

OUTPUT_SELECTOR = [
    'ItemArray.Item.ListingDetails.StartTime',
    'ItemArray.Item.ListingDetails.EndTime',
    'ItemArray.Item.ListingDetails.ViewItemURL',
    'ItemArray.Item.ListingDuration',
    'ItemArray.Item.ListingType',
    'ItemArray.Item.Quantity',
    'ItemArray.Item.QuestionCount',  # not GetSellerList
    'ItemArray.Item.SellingStatus.CurrentPrice',
    'ItemArray.Item.SellingStatus.QuantitySold',
    'ItemArray.Item.SKU',
    'ItemArray.Item.Title',
    'ItemArray.Item.WatchCount',  # include IncludeWatchCount for GetSellerList
]
OUTPUT_SELECTOR += [
    f'ItemArray.Item.ShippingDetails.ShippingServiceOptions.{x}' for x in [
        'ShippingService', 'ShippingServicePriority', 'ShippingServiceCost',
        'ShippingServiceAdditionalCost', 'ShippingTimeMin', 'ShippingTimeMax',
        'FreeShipping', 'ExpeditedService', 'ShipToLocation']]
OUTPUT_SELECTOR += [
    f'ItemArray.Item.ShippingDetails.InternationalShippingServiceOption.{x}'
    for x in [
        'ShippingService', 'ShippingServicePriority', 'ShippingServiceCost',
        'ShippingServiceAdditionalCost', 'ShippingTimeMin', 'ShippingTimeMax',
        'FreeShipping', 'ExpeditedService', 'ShipToLocation']]

GET_ITEM_OUTPUT_SELECTOR = [
    x.replace('ItemArray.Item', 'Item') for x in OUTPUT_SELECTOR]


def get_subtype_site_ids():
    """Get all the supported eBay site IDs."""
    subtypes = frappe.get_all(
        'Online Selling Subtype',
        fields=['subtype_id'],
        filters={'selling_platform': 'eBay'})
    return set(x['subtype_id'] for x in subtypes)


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


def format_shipping_options(options, shipping_option_descriptions):
    """Format a single dict or a list of dicts of shipping options.
    Accepts ShippingServiceOption and InternationalShippingServiceOption types.
    """
    return_list = []
    # If there is only one option, wrap in a list
    if not isinstance(options, Sequence):
        options = [options]

    # Sort options by priority
    for option in options:
        if 'ShippingServicePriority' not in option:
            option['ShippingServicePriority'] = 9999
    options.sort(key=operator.itemgetter('ShippingServicePriority'))

    # Format options for display
    for option in options:
        shipping_code = option['ShippingService']
        extra_opts = []
        if option.get('FreeShipping', False):
            extra_opts.append('Free Shipping')
        if option.get('ExpeditedService', False):
            extra_opts.append('Expedited Service')
        if 'ShipToLocation' in option:
            if isinstance(option['ShipToLocation'], str):
                ship_to_location = option['ShipToLocation']
            else:
                ship_to_location = ', '.join(option['ShipToLocation'])
            extra_opts.append(f'Ships to: {ship_to_location}')
        extra_opt_text = (' ({})'.format(', '.join(extra_opts))
                          if extra_opts else '')
        # Shipping cost
        shipping_cost = option.get('ShippingServiceCost', None)
        if shipping_cost is not None:
            amount = shipping_cost['value']
            currency = shipping_cost['_currencyID']
            cost = frappe.utils.data.fmt_money(amount, currency=currency)
            cost = cost.replace(' ', '&nbsp;')
        else:
            cost = '(uncalculated cost)'
        # Shipping costs for additional items
        addt_ship_cost = option.get(
            'ShippingServiceAdditionalCost', None)
        if addt_ship_cost is not None:
            amount = addt_ship_cost['value']
            currency = addt_ship_cost['_currencyID']
            addt_cost = ' (extra cost per additional item: {})'.format(
                frappe.utils.data.fmt_money(amount, currency=currency))
            addt_cost = addt_cost.replace(' ', '&nbsp;')
        else:
            addt_cost = ''
        # Delivery time
        if 'ShippingTimeMin' in option or 'ShippingTimeMax' in option:
            min_days = option.get('ShippingTimeMin', '?')
            max_days = option.get('ShippingTimeMax', '?')
            if min_days == max_days:
                days = ' ({} day delivery)'.format(max_days)
            else:
                days = ' ({} - {} days delivery)'.format(min_days, max_days)
        else:
            days = ''
        # Construct text for option
        text = "{desc}{extra}: {cost}{addt_cost}{days}".format(
            desc=shipping_option_descriptions.get(shipping_code, shipping_code),
            extra=extra_opt_text, cost=cost, addt_cost=addt_cost,
            days=days)

        return_list.append(text)

    return return_list


def format_shipping_services(site_id, shipping):
    """Create a formatted string detailing the different
    shipping services available.
    """

    if shipping is None:
        # No shipping methods available
        shipping = {}

    shipping_strings = []

    shipping_option_descriptions = get_shipping_service_descriptions(
        site_id=site_id)

    # Standard shipping services
    shipping_strings.append('Standard shipping services (priority order):')
    if 'ShippingServiceOptions' in shipping:
        shipping_strings.extend(
            format_shipping_options(shipping['ShippingServiceOptions'],
                                    shipping_option_descriptions))
    else:
        shipping_strings.append('No standard shipping services found')

    # International shipping options
    shipping_strings.append(
        '\nInternational shipping services (priority order):')

    if 'InternationalShippingServiceOption' in shipping:
        shipping_strings.extend(
            format_shipping_options(
                shipping['InternationalShippingServiceOption'],
                shipping_option_descriptions))
    else:
        shipping_strings.append('No international shipping services found')

    shipping_strings.append('\nSome services may not be available for selection'
                            + ' and can have incorrect prices.')

    return '\n'.join(shipping_strings)


@frappe.whitelist()
def sync(site_id=HOME_SITE_ID, update_ebay_id=False):
    """
    Updates Online Selling Items for eBay across the site.
    Also updates ebay_id for all items to the UK eBay ID.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)
    frappe.msgprint('Syncing eBay listings...')

    # Cast site_id to integer (in case passed from JS)
    site_id = int(site_id)

    # Create site-specific dictionary cache for subtype dicts
    subtype_cache = {}

    # Get valid site IDs
    valid_site_ids = get_subtype_site_ids()

    # Find all existing Online Selling Items that match eBay
    all_selling_items = [x['name'] for x in frappe.get_all(
        'Online Selling Item',
        filters={'selling_platform': 'eBay'})]

    # Delete all old listing entries matching eBay
    for selling_item in all_selling_items:
        frappe.delete_doc('Online Selling Item', selling_item)

    # Get a list of all item codes
    item_codes = set(x['name'] for x in frappe.get_all('Item'))

    ebay_id_dict = {}
    no_SKU_items = []
    not_found_SKU_items = []
    unsupported_listing_type = []
    multiple_listings = []

    # Get data from GetSellerList
    listings = get_seller_list(site_id=0,  # Use US site
                               output_selector=OUTPUT_SELECTOR,
                               granularity_level='Fine')

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

        item_site_id = EBAY_TRANSACTION_SITE_NAMES[listing['Site']]
        if item_site_id not in valid_site_ids:
            # This site ID is not supported?
            unsupported_listing_type.append(listing)
            continue
        # Get subtype dicts for this site_id, if necessary
        if item_site_id not in subtype_cache:
            subtype_cache[item_site_id] = get_subtype_dicts(item_site_id)
        subtype_dict, subtype_tax_dict = subtype_cache[item_site_id]
        if listing['ListingType'] not in subtype_dict:
            # This listing type is not supported?
            unsupported_listing_type.append(listing)
            continue

        new_listing = create_ebay_online_selling_item(
            listing, item_code, item_site_id, subtype_dict, subtype_tax_dict)
        new_listing.insert(ignore_permissions=True)

        if item_site_id == site_id:
            if item_code in ebay_id_dict:
                multiple_listings.append(item_code)
            else:
                ebay_id_dict[item_code] = listing['ItemID']

    if update_ebay_id:
        item_list = [x.item_code for x in
                     frappe.get_all('Item', fields=['item_code'])]
        for item_code in item_list:
            # Loop over every item in the system
            current_id = frappe.get_value('Item', item_code, 'ebay_id')
            ebay_id = ebay_id_dict.get(item_code, None)

            if current_id and (not current_id.isdigit()) and not ebay_id:
                # Current eBay ID is a placeholder; do not remove
                continue
            frappe.db.set_value('Item', item_code, 'ebay_id', ebay_id)

    messages = [
        f'{len(no_SKU_items)} listings had no SKU',
        f'{len(not_found_SKU_items)} listings had an unknown SKU',
        f'{len(unsupported_listing_type)} listings had an unsupported listing '
        + 'type',
        f'{len(multiple_listings)} listings had multiple eBay '
        + f'{EBAY_SITE_IDS[site_id]} listings',
        ]
    if multiple_listings:
        messages.append(', '.join(sorted(multiple_listings)))

    messages = '\n'.join(messages)
    frappe.msgprint(messages)
    ebay_logger().debug(messages)

    frappe.db.commit()


def create_ebay_online_selling_item(listing, item_code,
                                    site_id=None,
                                    subtype_dict=None,
                                    subtype_tax_dict=None):
    """Convert results from GetSellerList or GetItem to an
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
    utc_start_datetime = datetime.strptime(
        listing['ListingDetails']['StartTime'],
        '%Y-%m-%dT%H:%M:%S.%fZ')
    utc_end_datetime = datetime.strptime(
        listing['ListingDetails']['EndTime'],
        '%Y-%m-%dT%H:%M:%S.%fZ')
    # Convert eBay UTC time to local time zone:
    start_datetime = (
        frappe.utils.convert_utc_to_system_timezone(utc_start_datetime))
    end_datetime = frappe.utils.convert_utc_to_system_timezone(utc_end_datetime)

    # Sanitize URL
    selling_url = '<a href="{link}">{link}</a>'.format(
        link=listing['ListingDetails']['ViewItemURL'])
    selling_url = bleach.clean(
        selling_url, tags=['a'], attributes={'a': ['href']}, styles=[],
        strip=True, strip_comments=True)
    site_domain = EBAY_SITE_DOMAINS[site_id]
    selling_url = selling_url.replace('ebay.com', f'ebay.{site_domain}')

    # Quantity (listed) and quantity sold
    qty_listed = int(listing['Quantity'])
    qty_sold = int(listing['SellingStatus'].get('QuantitySold', 0))

    # Get formatted shipping string
    shipping_string = format_shipping_services(
        site_id, listing['ShippingDetails'])

    # Create listing
    # QuestionCount not available through GetSellerList
    new_listing = frappe.get_doc({
        'doctype': 'Online Selling Item',
        'parent': item_code,
        'parentfield': 'online_selling_items',
        'parenttype': 'Item',
        'status': listing['SellingStatus']['ListingStatus'],
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
        'selling_url': selling_url,
        'shipping_options': shipping_string})

    return new_listing
