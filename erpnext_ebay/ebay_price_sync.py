# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins



import frappe
from frappe import msgprint,_
from frappe.utils import cstr
import csv
from datetime import date, datetime, time, timedelta



from ugscommon import *
from ugscommonsql import *
from ugssettings import *




def better_print(*args, **kwargs):
    with open ("/home/frappe/price-sync", "a") as f:
        builtins.print (file=f, *args, **kwargs)

print = better_print


@frappe.whitelist()
def price_sync():
    
    using_ebay_csv_update_prices()


def using_ebay_csv_update_prices():
    price = 0.0
    try:
        fieldnames = ['Item ID', 'Custom label', 'Product ID type','Product ID value', 'Product ID value 2', 'Quantity available', 'Purchases', 'Bids','Price']
        with open('/home/frappe/active_listings.csv','r') as csvfile:
            reader = csv.DictReader(csvfile,fieldnames=fieldnames, delimiter=str(","), quotechar=str('"'))
            for row in reader:
                price_str = row['Price']
                price_str = price_str.replace(",", "")
                price = float(price_str)
                
                item_code = row['Custom label']
                # Only process proper item codes
                if item_code[:5] == "ITEM-" and price > 0.0:
                    success = set_erp_price(item_code, price)
                    if success:
                        print("Updated item: " + item_code + " to price: " + str(price))
    
    except Exception as inst:
        print("Unexpected error reading csv file:", inst)
        raise
    
    return -1
    

# Simply updates Item Price given item code and price
def set_erp_price(item_code, price):
    
        
    sql = """update `tabItem Price` ip
            set ip.price_list_rate = %s 
            where ip.item_code = '%s' """ %(float(price), item_code) 
        
    try:
        frappe.db.sql(sql, as_dict=1)

    
    except Exception as inst:
        print("Unexpected error running price fix. Possible missing Item Price for item: ", item_code)
        raise
        return False
    
    return True
    
    
    
    
    
    
    
    
# ALTERNATIVE METHOD    
    
def compare_ebay_prices():
        
    try:
        sql = """select ip.item_code, ip.price_list_rate
        from `tabItem Price` ip
        inner join `tabBin` bin
        on  bin.item_code = ip.item_code
        where bin.actual_qty > 0
        """
        
        records = frappe.db.sql(sql, as_dict=1)
        for r in records:
            item = r.item_code
            price = r.price_list_rate
            ebay_price = get_ebay_price(item)
            
            if ebay_price == -1:
                print("Item " + item + " Not found on eBay")
            else:
                if price != ebay_price:
                    set_erp_price(item, ebay_price)            
    
    except Exception as inst:
        print("Unexpected error ebay prices:", inst)
        raise
        return -1

def get_ebay_price(item_code):
    
    try:
        fieldnames = ['Item ID', 'Custom label', 'Product ID type','Product ID value', 'Product ID value 2', 'Quantity available', 'Purchases', 'Bids','Price']
        with open('/home/frappe/active_listings.csv','r') as csvfile:
            reader = csv.DictReader(csvfile,fieldnames=fieldnames, delimiter=str(","), quotechar=str('"'))
            for row in reader:
                if row['Custom label'] == item_code:
                    return (row['Price'])
    
    except Exception as inst:
        print("Unexpected error:", inst)
        raise
    
    return -1
    
    
    
