
# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import frappe
from frappe import msgprint
from frappe.utils import cstr
from datetime import date

#from jinja2 import Environment, PackageLoader
#import jinja2

from ebay_active_listings import generate_active_ebay_data
import ugssettings
from revise_items import revise_ebay_price


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
    print("Script run on ", date.today())
    #generate_active_ebay_data()
    #sync_ebay_prices_to_sys()
    #frappe.msgprint("Finished price sync.")

    #percent_price_reduction(-5)
    frappe.msgprint("System price reduction completed")
    
    generate_active_ebay_data()
    sync_prices_to_ebay()
    frappe.msgprint("Price revision completed")


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
    and it.ebay_id REGEXP '[0-9]'
    and el.price > 0
    """
    
    sql="""
    update `tabItem` it
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    set it.standard_rate = el.price /1.2, 
    it.vat_inclusive_price = el.price
    
    where 
    it.ebay_id REGEXP '[0-9]'
    and el.price > 0
    """







def upcoming_price_changes(change):
    
    sql = """
    select it.item_code, it.ebay_id, 
    it.standard_rate, 
    it.standard_rate + (it.standard_rate * %s / 100.0) as new_price
    
    from `tabItem` it
    
    left join `tabItem Price` ip
    on ip.item_code = it.item_code
    
    where it.ebay_id REGEXP '[0-9]'
    and it.modified < (now() - interval 30 day)
    and ((it.standard_rate >25 and it.delivery_type = 'Standard Parcel')
    or (it.standard_rate >75 and it.delivery_type = 'Pallet'))
    and (select count(sii.name) from `tabSales Invoice Item` sii where sii.item_code = it.item_code and sii.docstatus=1) = 0
    order by it.standard_rate
    """%(change)

    changes = frappe.db.sql(sql, as_dict=1)
    for c in changes:
        print("System Price changes: {} {} to {}".format(c.item_code, c.standard_rate, c.new_price))



    # Items not suitable for price drop (to be ended)
    sql2 = """
    select it.item_code, it.ebay_id, 
    it.standard_rate
    
    from `tabItem` it
    
    left join `tabItem Price` ip
    on ip.item_code = it.item_code
    
    where it.ebay_id REGEXP '[0-9]'
    and it.modified < (now() - interval 30 day)
    and ((it.standard_rate <=25 and it.delivery_type = 'Standard Parcel')
    or (it.standard_rate <=75 and it.delivery_type = 'Pallet'))
    and (select count(sii.name) from `tabSales Invoice Item` sii where sii.item_code = it.item_code and sii.docstatus=1) = 0
    order by it.standard_rate
    """
    no_changes = frappe.db.sql(sql2, as_dict=1)
    for c in no_changes:
        print("No changes: {} {} to {}".format(c.item_code, c.standard_rate, c.standard_rate))






def percent_price_reduction(change):
    """
    Change all system price by change %
    
    Only update records with an eBay ID and

    TODO investigate audit trail via ErpNext. Best to change price via a Frappe call so the changes are logged or create logs?
    """
    
    upcoming_price_changes(change)

    # TODO do you wish to continue?

    sql_update = """
    update `tabItem Price` ip
    
    left join `tabItem` it
    on ip.item_code = it.item_code
    
    set ip.price_list_rate = ip.price_list_rate + (ip.price_list_rate * %s / 100.0)

    where ip.selling = 1
    and it.ebay_id REGEXP '[0-9]'
    
    and it.modified < now() - interval 10 day
    
    and ((it.standard_rate >25 and it.delivery_type = 'Standard Parcel')
    or (it.standard_rate >75 and it.delivery_type = 'Pallet'))
    and (select count(sii.name) from `tabSales Invoice Item` sii where sii.item_code = it.item_code and sii.docstatus=1) = 0
    
    """%(change)

    frappe.db.sql(sql_update, auto_commit=True)
    
    sql_update_it = """
    update `tabItem` it

    set 
    it.standard_rate = it.standard_rate + (it.standard_rate * %s / 100.0),
    it.vat_inclusive_price = it.vat_inclusive_price + (it.vat_inclusive_price * %s / 100.0)
    
    where 
    it.ebay_id REGEXP '[0-9]'
    and it.modified < now() - interval 30 day
    
    and ((it.standard_rate >25 and it.delivery_type = 'Standard Parcel')
    or (it.standard_rate >75 and it.delivery_type = 'Pallet'))
    and (select count(sii.name) from `tabSales Invoice Item` sii where sii.item_code = it.item_code and sii.docstatus=1) = 0
    
    """%(change, change)

    frappe.db.sql(sql_update_it, auto_commit=True)

    print("Price reduction completed")



def get_custom_discounts():
    """
    Use Pricing Rules functionality to enable us to get custom discounting functionality
    """

    sql = """
    
    """



def sync_prices_to_ebay():
    """
    Mass update eBay prices to match the system price
    # TODO alternative is to set up an event driven solution similar to the custom script
    
    NOTE: el.price is actual eBay price (ie. inc VAT)
    """


    # First get the mis-matched prices
    sql = """
    select it.item_code, it.ebay_id,
    ifnull(ip.price_list_rate, 0.0) as price_list_rate, 
    ifnull(it.standard_rate,0.0),
    ifnull(it.vat_inclusive_price,0.0),
    ifnull(el.price,0.0) as ebay_inc_vat
    
    from `tabItem Price` ip
    
    left join `tabItem` it
    on it.item_code = ip.item_code
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    where it.ebay_id REGEXP '[0-9]'
    and ifnull(it.vat_inclusive_price, 0.0) <> ifnull(el.price, 0.0)
    and it.standard_rate > 0.0
    and ifnull(el.price,0.0) > 0
    """

    records = frappe.db.sql(sql, as_dict=1)

    # Call the revise price function
    for r in records:
        # revise_ebay_price takes exc vat pricing
        result = revise_ebay_price(r.item_code, r.standard_rate, False)
        print(result)


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
    select it.item_code, 
    it.ebay_id, 
    ip.price_list_rate, 
    it.standard_rate
    from `tabItem` it
    
    left join `tabItem Price` ip
    on ip.item_code = it.item_code
    
    where (it.ebay_id REGEXP '[0-9]' or it.show_in_website = 1)
    and (ip.price_list_rate <> it.standard_rate
    or ip.price_list_rate is NULL)
    
    """




    
def report_all_pricing_no_filters():
    
    sql= """
    select it.item_code, it.ebay_id,
    ip.price_list_rate as ip_price, 
    it.standard_rate as st_price, 
    (el.price / 1.2) as ebay_exc,
    it.vat_inclusive_price,
    el.price as ebay_inc
    
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
    it.vat_inclusive_price,
    el.price as ebay_inc
    
    from `tabItem Price` ip
    
    left join `tabItem` it
    on it.item_code = ip.item_code
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    where it.vat_inclusive_price <> (el.price)
    and it.ebay_id REGEXP '[0-9]'
    """



def check_item_state_change():
    
    
    sql="""
    select ref_doctype, docname, creation, data 
    from `tabVersion` 
    where ref_doctype ='Item' 
    and creation > '2018-04-15' 
    and data like '%item_status%' 
    """
    
    
    