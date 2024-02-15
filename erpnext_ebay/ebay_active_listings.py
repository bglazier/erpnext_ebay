"""ebay active listings
run from: premium report, garagsale_xml
"""

import datetime
import json

import frappe

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading

from .ebay_constants import EBAY_TRANSACTION_SITE_IDS, HOME_SITE_ID
from .ebay_get_requests import ebay_logger, get_seller_list

from erpnext_ebay.erpnext_ebay.doctype.ebay_manager_settings.ebay_manager_settings import (
    use_sandbox)

OUTPUT_SELECTOR = [
    'ItemArray.Item.SKU',
    'ItemArray.Item.Quantity',
    'ItemArray.Item.ListingType',
    'ItemArray.Item.SellingStatus.CurrentPrice',
    'ItemArray.Item.SellingStatus.QuantitySold',
    'ItemArray.Item.ListingDetails.EndTime'
]


@frappe.whitelist()
def generate_active_ebay_data(print=None, multiple_error_sites=None,
                              extra_output_selector=None,
                              multiple_skip_only=False):
    """Get all the active eBay listings for the selected eBay site
    and save them to the temporary data table.

    If multiple_error_sites is supplied, only multiple entries for those
    eBay sites are considered an error. If multiple_skip_only is True,
    the item is skipped but no error is returned (only a warning).

    Data in the table will not be over-written in the event of error.
    """

    if print is None:
        print = ebay_logger().debug

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)

    if not frappe.db.get_single_value('eBay Manager Settings', 'enable_ebay'):
        frappe.throw('eBay disabled')

    # Convert from JSON (for calls from front end)
    if isinstance(multiple_error_sites, str):
        multiple_error_sites = json.loads(multiple_error_sites)
    if isinstance(extra_output_selector, str):
        extra_output_selector = json.loads(extra_output_selector)
    if isinstance(multiple_skip_only, str):
        multiple_skip_only = json.loads(multiple_skip_only)

    # Extra fields
    if extra_output_selector:
        output_selector = OUTPUT_SELECTOR + extra_output_selector
    else:
        output_selector = OUTPUT_SELECTOR

    if not frappe.db.sql("""SHOW TABLES LIKE 'zeBayListings';"""):
        print('Setting up zeBayListings table')
        # Set up the zeBayListings table if it does not exist

        frappe.db.sql("""
        CREATE TABLE IF NOT EXISTS `zeBayListings` (
            sku VARCHAR(20) NOT NULL,
            ebay_id VARCHAR(38),
            listing_type VARCHAR(20),
            end_time DATETIME,
            qty INTEGER,
            price DECIMAL(18,6),
            site VARCHAR(40)
            );
        """, auto_commit=True)

    # Before we get the table lock, get the sandbox value (we can't access
    # any other table once we have a table lock, unless we lock that table
    # as well)
    force_sandbox_value = use_sandbox('GetSellerList')

    print('Getting table lock')
    # Try and get table lock. If we fail (due to timeout), throw an error
    # message. Unlock the tables in any circumstance except success.
    success = False
    try:
        frappe.db.sql("""LOCK TABLES `zeBayListings` WRITE WAIT 60;""")
        success = True
    except frappe.db.InternalError:
        frappe.db.sql("""UNLOCK TABLES;""")
        frappe.throw('Unable to lock eBay update; may already be running.')
    finally:
        if not success:
            frappe.db.sql("""UNLOCK TABLES;""")

    # Now that we have a table lock, make sure we unlock it in the event of
    # an exception.
    try:

        # If the data has been pulled down in the last 60 seconds, don't
        # update it again, unless we have been passed extra_output_selector
        if not extra_output_selector:
            last_update = frappe.cache().get_value('erpnext_ebay.last_update')
            if last_update:
                seconds_ago = (
                    (datetime.datetime.now() - last_update).total_seconds()
                )
                if seconds_ago < 60:
                    print('Last update was completed less than 60s ago.')
                    # Table will be unlocked by finally clause
                    return

        print('Getting data from eBay via GetSellerList call')
        # Get data from GetSellerList
        listings = get_seller_list(site_id=0,  # Use US site
                                   output_selector=output_selector,
                                   granularity_level='Fine',
                                   force_sandbox_value=force_sandbox_value,
                                   print=print)

        multiple_check = set()
        multiple_error = set()
        multiple_warnings = set()

        print('Updating table and checking data')
        records = []
        for item in listings:
            # Loop over each eBay item on each site
            ebay_id = item['ItemID']
            listing_type = item['ListingType']
            end_time = datetime.datetime.strptime(
                item['ListingDetails']['EndTime'],
                '%Y-%m-%dT%H:%M:%S.%fZ')
            original_qty = int(item['Quantity'])
            qty_sold = int(item['SellingStatus']['QuantitySold'])
            sku = item.get('SKU', '')
            price = float(item['SellingStatus']['CurrentPrice']['value'])
            site = item['Site']

            if sku:
                # Check that this item appears only once
                mult_tuple = (sku, site)
                if mult_tuple in multiple_check:
                    if (not multiple_error_sites
                            or (site in multiple_error_sites)):
                        multiple_error.add(mult_tuple)
                    else:
                        multiple_warnings.add(mult_tuple)
                    continue
                multiple_check.add(mult_tuple)

            qty = original_qty - qty_sold
            records.append(
                (sku, ebay_id, listing_type, end_time, qty, price, site)
            )

        msgs = []
        if multiple_error:
            for sku, site in multiple_error:
                msgs.append(f'The item {sku} has multiple ebay listings on the '
                            + f'eBay site {site}!')
            if not multiple_skip_only:
                frappe.throw('\n'.join(msgs))
        if multiple_warnings:
            for sku, site in multiple_warnings:
                msgs.append(f'The item {sku} has multiple ebay listings on the '
                            + f'eBay site {site}!')
        if msgs:
            frappe.msgprint('\n'.join(msgs))

        # Truncate table now we have good data
        frappe.db.sql("""TRUNCATE TABLE `zeBayListings`;""", auto_commit=True)

        for record in records:
            # Insert eBay listings into the zeBayListings temporary table"""
            frappe.db.sql("""
                INSERT INTO `zeBayListings`
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, record, auto_commit=True)

        frappe.cache().set_value('erpnext_ebay.last_update',
                                 datetime.datetime.now())
    finally:
        frappe.db.sql("""UNLOCK TABLES;""")

    return listings


# *********************************************
# ***********  EBAY ID SYNCING CODE ***********
# *********************************************


@frappe.whitelist()
def update_ebay_data(multiple_error_sites=None, multiple_skip_only=False):
    """Get eBay data, set eBay IDs and set eBay first listed dates."""

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)

    if not frappe.db.get_single_value('eBay Manager Settings', 'enable_ebay'):
        frappe.throw('eBay disabled')

    generate_active_ebay_data(multiple_error_sites=multiple_error_sites,
                              multiple_skip_only=multiple_skip_only)
    sync_ebay_ids()
    set_on_sale_from_date()
    frappe.cache().set_value('erpnext_ebay.last_full_update',
                             datetime.datetime.now())
    return True


# if item is on ebay then set the ebay_id field
def set_item_ebay_id(item_code, ebay_id):
    """Given an item_code, sets the ebay_id field to the live eBay ID.
    Also, does not overwrite Awaiting Garagesale if ebay_id is blank.
    """

    try:
        # Try to set ebay_id properly
        item_doc = frappe.get_doc('Item', item_code)
        if not ebay_id and item_doc.ebay_id == 'Awaiting Garagesale':
            return
        item_doc.ebay_id = ebay_id
        item_doc.save(ignore_permissions=True)

    except Exception as e:
        # Set eBay ID using DB
        ebay_logger().debug(
            f'Could not set ebay_id "{ebay_id}" on item {item_code} properly:'
            + f'\n{e}'
        )
        awaiting_garagesale_filter = "AND it.ebay_id <> 'Awaiting Garagesale'"

        frappe.db.sql(f"""
            UPDATE `tabItem` AS it
                SET it.ebay_id = %s
                WHERE it.item_code = %s
                    {'' if ebay_id else awaiting_garagesale_filter};
            """, (ebay_id, item_code),
            auto_commit=True)


def set_on_sale_from_date():
    """
    For all items with a numeric eBay ID and no on_sale_from_date,
    set the on_sale_from date to today.
    """

    date_today = datetime.date.today()

    frappe.db.sql("""
        UPDATE `tabItem` it
            SET it.on_sale_from_date = %s
            WHERE it.on_sale_from_date is NULL
                AND it.ebay_id REGEXP '^[0-9]+$';
        """, (datetime.date.today().isoformat()),
        auto_commit=True)


def sync_ebay_ids(site_id=HOME_SITE_ID):
    """Synchronize system eBay IDs from the temporary table"""

    site_name = EBAY_TRANSACTION_SITE_IDS[site_id]

    # This is a (slightly tweaked) full outer join of the eBay data and the
    # current Item data filtered to identify only changes.
    # Each (non-empty) SKU is guaranteed (by earlier checks) only to appear
    # once per site.
    records = frappe.db.sql("""
        SELECT item.item_code,
            ebay.ebay_id AS live_ebay_id,
            item.ebay_id AS dead_ebay_id
        FROM `zeBayListings` AS ebay
        LEFT JOIN `tabItem` AS item
            ON ebay.sku = item.item_code
        WHERE ebay.site = %(site_name)s
            AND IFNULL(ebay.sku, '') <> ''
            AND IFNULL(item.ebay_id, '') <> IFNULL(ebay.ebay_id, '')

        UNION ALL

        SELECT item.item_code,
            ebay.ebay_id AS live_ebay_id,
            item.ebay_id AS dead_ebay_id
        FROM `zeBayListings` AS ebay
        RIGHT JOIN `tabItem` AS item
            ON ebay.sku = item.item_code
                AND ebay.site = %(site_name)s
        WHERE ebay.ebay_id IS NULL
            AND IFNULL(item.ebay_id, '') <> ''
        """, {'site_name': site_name}, as_dict=True)

    for r in records:
        if r.live_ebay_id:
            if r.item_code:
                # Item is live but eBay IDs don't match
                # Update system with live version
                set_item_ebay_id(r.item_code, r.live_ebay_id)
            else:
                # eBay item does not appear on system
                frappe.msgprint(
                    'eBay item cannot be found in the system; '
                    + f'unable to record eBay id {r.live_ebay_id}')
        else:
            # No live eBay ID; clear any value on system
            # (unless Awaiting Garagesale)
            set_item_ebay_id(r.item_code, None)
