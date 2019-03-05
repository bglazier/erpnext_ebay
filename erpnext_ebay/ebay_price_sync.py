# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import frappe
from frappe import msgprint
from frappe.utils import cstr
from datetime import date


from ebay_active_listings import generate_active_ebay_data, sync_ebay_ids
import ugssettings
from revise_items import revise_ebay_price


def better_print(*args, **kwargs):
    with open("price_sync_log.log", "a") as f:
        builtins.print (file=f, *args, **kwargs)

print = better_print




@frappe.whitelist()
def price_sync():
    """
    Initiates automated price reduction
    and sync to eBay
    Note: el.price is price on eBay (ie. inc vat)
    """

    print("Price sync to eBay run on ", date.today())

    generate_active_ebay_data()
    sync_ebay_ids()
    sync_prices_to_ebay()
    frappe.msgprint("Price revision completed")

    return 1



def sync_prices_to_ebay():
    """
    Mass update eBay prices to match the system price
    # TODO alternative is to set up an event driven solution similar to the custom script
    
    NOTE: el.price is actual eBay price (ie. inc VAT)
    """


    # First get the mis-matched prices
    records = get_mismatched_prices()
    
    # Call the revise price function
    for r in records:
        # revise_ebay_price takes exc vat pricing
        result = revise_ebay_price(r.item_code, r.price_list_rate, False)
        print(result)



def get_mismatched_prices():
    """
    return items where ebay price <> system price
    """

    sql = """
    select distinct(it.item_code), it.ebay_id,
    round(ifnull(ip.price_list_rate, 0.0),2) as price_list_rate, 
    ip.price_list,
    round(ifnull(it.standard_rate,0.0),2) as standard_rate,
    round(ifnull(it.vat_inclusive_price,0.0),2) as vat_inclusive_price,
    round(ifnull(el.price,0.0),2) as ebay_inc_vat
    
    from `tabItem Price` ip
    
    left join `tabItem` it
    on it.item_code = ip.item_code
    
    left join `zEbayListings` el
    on el.sku = it.item_code
    
    where it.ebay_id REGEXP '[0-9]'
    and round(ifnull(it.vat_inclusive_price, 0.0),2) <> round(ifnull(el.price, 0.0),2)
    and it.standard_rate > 0.0
    and ifnull(el.price,0.0) > 0
    and ip.price_list = 'eBay Selling'
    """
    records = frappe.db.sql(sql, as_dict=1)
    
    return records



