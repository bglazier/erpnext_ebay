"""ebay active listings
run from: premium report, garagsale_xml
"""

import datetime

import frappe

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading

from .ebay_constants import EBAY_TRANSACTION_SITE_IDS
from .ebay_requests import get_seller_list, default_site_id, PATH_TO_YAML

OUTPUT_SELECTOR = [
    'ItemArray.Item.SKU',
    'ItemArray.Item.Quantity',
    'ItemArray.Item.SellingStatus.CurrentPrice',
    'ItemArray.Item.SellingStatus.QuantitySold']


#def update_sold_statusDONOTUSE():
    #sql = """
    #DONT DO THIS UNLESS ABSOLUTELT SURE ABOUT QTY BETTER TO DO VIA IMPORT???????
    #update set it.workflow_state = 'Sold'

    #select it.item_code, bin.actual_qty
    #from `tabItem` it
    #right join `tabBin` bin
    #on bin.item_code = it.item_code

    #right join `zeBayListings` el
    #on el.sku = it.item_code
    #where el.qty =0 and bin.actual_qty =0
    #"""


@frappe.whitelist()
def generate_active_ebay_data(drop_table=True, print=print,
                              multiple_error_sites=None):
    """Get all the active eBay listings for the selected eBay site
    and save them to the temporary data table.

    If multiple_error_sites is supplied, only multiple entries for those
    eBay sites are considered an error.
    """

    # This is a whitelisted function; check permissions.
    if not frappe.has_permission('eBay Manager'):
        frappe.throw('You do not have permission to access the eBay Manager',
                     frappe.PermissionError)

    print('Setting up zeBayListings table')
    # Set up the zeBayListings table
    if drop_table:
        frappe.db.sql("""DROP TABLE IF EXISTS `zeBayListings`;""", auto_commit=True)

        frappe.db.sql("""
        CREATE TABLE IF NOT EXISTS `zeBayListings` (
            sku VARCHAR(20) NOT NULL,
            ebay_id VARCHAR(38),
            qty INTEGER,
            price DECIMAL(18,6),
            site VARCHAR(40)
            );
        """, auto_commit=True)

    else:
        frappe.db.sql("""TRUNCATE TABLE `zeBayListings`;""", auto_commit=True)

    print('Getting data from eBay via GetSellerList call')
    # Get data from GetSellerList
    listings = get_seller_list(site_id=0,  # Use US site
                               output_selector=OUTPUT_SELECTOR,
                               granularity_level='Fine',
                               print=print)

    multiple_check = set()
    multiple_error = set()
    multiple_warnings = set()

    print('Updating table and checking data')
    for item in listings:
        # Loop over each eBay item on each site
        ebay_id = item['ItemID']
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

        # Insert eBay listings into the zeBayListings temporary table"""
        frappe.db.sql("""
            INSERT INTO `zeBayListings`
                VALUES (%s, %s, %s, %s, %s);
            """, (sku, ebay_id, qty, price, site),
            auto_commit=True)

    if multiple_error:
        msgs = []
        for sku, site in multiple_error:
            msgs.append(f'The item {sku} has multiple ebay listings on the '
                        + f'eBay site {site}!')
        frappe.throw('\n'.join(msgs))
    if multiple_warnings:
        msgs = []
        for sku, site in multiple_warnings:
            msgs.append(f'The item {sku} has multiple ebay listings on the '
                        + f'eBay site {site}!')
        frappe.msgprint('\n'.join(msgs))


# *********************************************
# ***********  EBAY ID SYNCING CODE ***********
# *********************************************


def update_ebay_data(multiple_error_sites=None):
    """Get eBay data, set eBay IDs and set eBay first listed dates."""
    generate_active_ebay_data(multiple_error_sites=multiple_error_sites)
    sync_ebay_ids()
    set_on_sale_from_date()
    return True


# if item is on ebay then set the ebay_id field
def set_item_ebay_id(item_code, ebay_id):
    """Given an item_code, sets the ebay_id field to the live eBay ID.
    Also, does not overwrite Awaiting Garagesale if ebay_id is blank.
    """

    awaiting_garagesale_filter = """AND it.ebay_id <> 'Awaiting Garagesale'"""

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


def sync_ebay_ids(site_id=default_site_id):
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
            AND ebay.sku <> ''
            AND item.ebay_id <> ebay.ebay_id

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
