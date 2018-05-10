
# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import frappe
from frappe import msgprint,
from frappe.utils import cstr

from jinja2 import Environment, PackageLoader
import jinja2

from ebay_active_listings import generate_active_ebay_data
import ugssettings


def better_print(*args, **kwargs):
    with open("price_sync_to_erpnext_log.log", "a") as f:
        builtins.print (file=f, *args, **kwargs)

print = better_print


@frappe.whitelist(allow_guest=True)
def price_sync():
    """Price sync is to be run if ErpNext prices are out of sync with eBay
    This should not happen going forward if prices are adjusted on ErpNext and then revised.
    """

    frappe.msgprint("Syncing. Note: Did you run ebay active listing?")
    #generate_active_ebay_data()
    sync_from_ebay_to_erpnext()

    frappe.msgprint("Finished price sync.")



def sync_from_ebay_to_erpnext():
    
    sql = """Ç
    select el.sku, ifnull(el.price, 0.0) as ebay_price from `zEbayListings` el
    """
    
    records = frappe.db.sql(sql, as_dict=True)
    
    for r in records:
        # Note: The eBay prices stored in zEbayListings are ex vat
        print('Syncing price for this item: ', r.sku)
        
        if r.ebay_price:
            new_price = r.ebay_price / ugssettings.VAT
            set_erp_price(r.sku, new_price)



# Simply updates Item Price given item code and price
def set_erp_price(item_code, price):
    
    '''
    # database contains two prices it.standard_rate and ip.price_list_rate
    select ip.item_code, ip.price_list_rate, ip.selling, it.standard_rate from 
    `tabItem Price` ip left join `tabItem` it on it.item_code = ip.item_code
    where ip.price_list_rate <> it.standard_rate;
    '''
    
    sql = """update `tabItem Price` ip
            set ip.price_list_rate = {}
            where ip.selling = 1 and ip.item_code = '{}' """.format(float(price), item_code)
   
    
    try:
        frappe.db.sql(sql, auto_commit = True)
    
    
    except Exception as inst:
        print("Unexpected error running price fix. Possible missing Item Price for item: ", item_code)

    
    
    
    sql2 = """update `tabItem` it
            set it.standard_rate = {}
            where it.item_code = '{}' """.format(float(price), item_code)
    
    
    try:
        frappe.db.sql(sql2, auto_commit = True)
    
    
    except Exception as inst:
        print("Unexpected error running price fix. Possible missing Price for item: ", item_code)

    
    return



