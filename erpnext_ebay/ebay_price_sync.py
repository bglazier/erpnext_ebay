
# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import frappe
from frappe import msgprint
from frappe.utils import cstr

#from jinja2 import Environment, PackageLoader
#import jinja2

from ebay_active_listings import generate_active_ebay_data
import ugssettings


def better_print(*args, **kwargs):
    with open("price_sync_log.log", "a") as f:
        builtins.print (file=f, *args, **kwargs)

print = better_print




@frappe.whitelist(allow_guest=True)
def price_sync():
    """Price sync is to be run if ErpNext prices are out of sync with eBay
    This should not happen going forward if prices are adjusted on ErpNext and then revised.
    
    Note: el.price is price on eBay (ie. inc vat)
    """

    generate_active_ebay_data()
    sync_ebay_prices_to_sys()
    frappe.msgprint("Finished price sync.")

    """
    percent_price_reduction(-5)
    frappe.msgprint("System price reduction completed")
    
    generate_active_ebay_data()
    sync_prices_to_ebay()
    frappe.msgprint("Finished price sync. to eBay")
    """

    return 1



def make_all_item_prices_equal_to_std():
    """
    update table so prices are in sync with standard_rate
    """

    sql = """
    update `tabItem Price` ip
    left join `tabItem` it
    on it.item_code = ip.item_code
    set ip.price_list_rate = it.standard_rate
    where ip.selling = 1
    and ip.price_list_rate <> it.standard_rate
    and it.standard_rate > 0
    """

    sql = """
    update `tabItem` it
    left join `tabItem Price` ip
    on it.item_code = ip.item_code
    set it.vat_inclusive_price = it.standard_rate * 1.2
    where it.standard_rate > 0
    """
    
    sql = """
    update `tabItem` it
    left join `tabItem Price` ip
    on it.item_code = ip.item_code
    
    set it.standard_rate = ip.price_list_rate
    where it.standard_rate =0
    and ip.selling = 1
    and ip.price_list_rate <> it.standard_rate
    and ip.price_list_rate > 0
    """

def sync_ebay_prices_to_sys():
    """
    update database tables with el.price
    el.price is actual eBay price (i.e. inc vat)
    
    only do this for selling prices, items with an ebay id, and an eBay price
    
    where ip.price_list = 'Standard Selling'
    """

    sql_update="""
    update `tabItem Price` ip
    
    left join `tabItem` it
    on it.item_code = ip.item_code
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    set ip.price_list_rate = (el.price / 1.2)
    
    where ip.selling = 1
    and it.ebay_id > 0
    and el.price > 0
    """
    
    sql="""
    update `tabItem` it
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    set it.standard_rate = el.price /1.2, 
    it.vat_inclusive_price = el.price
    
    where 
    it.ebay_id > 0
    and el.price > 0
    """




def percent_price_reduction(change):
    """
    Change all system price by change %
    
    Only update records with an eBay ID and
    records where the standard_rate = price_list rate (NOTE this should be resolved first)

    TODO investigate audit trail via ErpNext. Best to change price via a Frappe call so the changes are logged?
    """
    
    # Report on the upcoming changes
    sql = """
    select it.item_code, it.ebay_id, ip.price_list_rate, ip.price_list_rate - (ip.price_list_rate * %s / 100.0) as new_price
    from `tabItem` it
    
    left join `tabItem Price` ip
    on ip.item_code = it.item_code
    
    where it.ebay_id > 0
    and ip.price_list_rate = it.standard_rate
    
    """%(change)

    changes = frappe.db.sql(sql, as_dict=1)
    for c in changes:
        print("Proposed System Price changes: {} {} to {}").format(c.item_code, c.price_list_rate, c.new_price)

    # TODO do you wish to continue?

    sql_update = """
    update ip.item_price
    set ip.price_list_rate = ip.price_list_rate + (ip.price_list_rate * %s / 100.0),
    it.standard_rate = ip.standard_rate + (ip.standard_rate * %s / 100.0),
    it.vat_inclusive_price = ip.vat_inclusive_price + (ip.vat_inclusive_price * %s / 100.0)
    where it.ebay_id > 0
    and ip.price_list_rate = it.standard_rate
    
    """%(change, change, change)

    frappe.db.sql(sql_update, auto_commit=True)


def sync_prices_to_ebay():
    """
    Mass update eBay prices to match the system price
    # TODO alternative is to set up an event driven solution similar to the custom script
    
    NOTE: el.price is actual eBay price (ie. inc VAT)
    """

    # TODO
    website_discount_to_ebay = 10

    # First get the mis-matched prices
    sql = """
    select it.item_code,
    ifnull(ip.price_list_rate, 0.0), 
    it.standard_rate, 
    it.vat_inclusive_price, 
    el.price as ebay_inc_vat
    
    from `tabItem Price` ip
    
    left join `tabItem` it
    on it.item_code = ip.item_code
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    where it.ebay_id > 0
    and it.standard_rate <> (el.price/1.2)
    """

    records = frappe.db.sql(sql, as_dict=1)

    # Call the revise price function
    for r in records:
        # TODO need to add in is_auction functionality
        # revise_ebay_price takes exc vat pricing
        revise_ebay_price(r.item_code, r.standard_rate, False)
        print("Item {} price revised from {} to {}").format(item_code, r.ebay_ex_vat



###### PRICE REPORTING  ##########
###### PRICE REPORTING  ##########
###### PRICE REPORTING  ##########
###### PRICE REPORTING  ##########
###### PRICE REPORTING  ##########



def report_inconsistent_system_pricing():
    """
    Query shows either items live on ebay or showing on website
    where either there is no price_list_rate or where price_list_rate <> standard_rate
    """

    sql = """
    select it.item_code, it.ebay_id, ip.price_list_rate, it.standard_rate
    from `tabItem` it
    
    left join `tabItem Price` ip
    on ip.item_code = it.item_code
    
    where (it.ebay_id > 0 or it.show_in_website = 1)
    and (ip.price_list_rate <> it.standard_rate
    or ip.price_list_rate is NULL)
    
    """




    
def report_all_pricing_no_filters():
    
    sql= """
    select it.item_code, 
    ip.price_list_rate as ip_price, 
    it.standard_rate as st_price, 
    el.price as ebay_ex, 
    (el.price * 1.2) as ebay_inc,
    it.vat_inclusive_price
    
    from `tabItem` it
    
    left join `tabItem Price` ip
    on it.item_code = ip.item_code
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    """


def report_inconsistent_pricing_all():
    
    sql = """
    select it.item_code, 
    ip.price_list_rate as ip_price, 
    it.standard_rate as st_price, 
    (el.price / 1.2) as ebay_exc,
    el.price as ebay_inc, 
    it.vat_inclusive_price
    
    from `tabItem Price` ip
    
    left join `tabItem` it
    on it.item_code = ip.item_code
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    where ip.selling = 1
    and ip.price_list_rate <> it.standard_rate 
    and it.standard_rate <> (el.price/1.2)
    and it.standard_rate <> 0
    and it.ebay_id > 0
    """
