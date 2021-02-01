# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

import math
import sys
import os.path

import frappe

from erpnext_ebay.ebay_requests import get_trading_api, revise_inventory_status

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading
#from .garage_sale import jtemplate, lookup_condition


#PATH_TO_YAML = os.path.join(os.sep, frappe.utils.get_bench_path(), 'sites',
                            #frappe.get_site_path(), 'ebay.yaml')


#def revise_generic_items(item_code):
    #"""Generic Revise eBay listings"""

    ##get the ebay id given the item_code
    #ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    #if ebay_id and item_code:
        #frappe.msgprint('This Item is on eBay. Please wait while the listing is revised...')

        #(item_name,
         #description,
         #function_grade,
         #grade_details,
         #condition_grade,
         #tech_details,
         #delivery_type,
         #accessories_extras,
         #power_cable_included,
         #power_supply_included,
         #remote_control_included,
         #case_included,
         #warranty_period
         #) = get_item_revisions(item_code)

        #version = 0

        #body = """<![CDATA["""
        #body += jtemplate(
            #version, description, function_grade, grade_details, condition_grade,
            #tech_details, delivery_type, accessories_extras,
            #power_cable_included, power_supply_included,
            #remote_control_included, case_included, warranty_period)
        #body += "<br></br>The price includes VAT and we can provide VAT invoices."
        #body += "<br></br>Universities and colleges - purchase orders accepted - please contact us."
        #body += "<br></br>sku: " + item_code
        #body += """]]>"""

        #condition_description = ''  # grade_details
        #condition_id_text, condition_id = lookup_condition(condition_grade, 0)

        #new_gsp = (delivery_type == 'Standard Parcel')

        #try:
            #api_trading = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)

            ##EXAMPLE api.execute('ReviseItem',{'Item':{'ItemID':ItemID},'Title':words}
            #api_trading.execute('ReviseItem', {
                #'Item': {'ItemID': ebay_id},
                #'GlobalShipping': new_gsp,
                #'Title': item_name,
                #'Description': body,
                #'ConditionDescription': condition_description,
                #'ConditionID': condition_id
                #})

        #except ConnectionError:
            #frappe.msgprint("Config file ebay.yaml file not found")
            #raise

        #except Exception:
            #frappe.msgprint("There was a problem using the eBay Api")
            #raise

        #else:
            #frappe.msgprint("Success eBay listing updated!")
    #else:
        #frappe.msgprint("There was a problem getting the data")


#def get_item_revisions(item_code):

    #sql = """
    #select
        #it.item_name,
        #it.description,
        #it.function_grade,
        #it.grade_details,
        #it.condition_grade,
        #it.tech_details,
        #it.delivery_type,
        #it.accessories_extras,
        #it.power_cable_included,
        #it.power_supply_included,
        #it.remote_control_included,
        #it.case_included,
        #it.warranty_period,
        #it.is_auction
    #from `tabItem` it
    #where item_code = '{}'
    #""".format(item_code)

    #records = frappe.db.sql(sql)

    #return tuple(records[0][0:13])


#def revise_ebay_price(item_code, new_price, is_auction=False):
    #"""Given item_code and (inc vat) price, revise the listing on eBay"""

    ## get the ebay id given the item_code
    #ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    #if not ebay_id and item_code and new_price:
        #raise ValueError(
            #'Price Sync Error: There was a problem getting with the '
            #+ 'item_code, price or eBay ID')

        #new_price_inc = float(new_price)
        #api_trading = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)

        #if is_auction:
            #api_trading.execute(
                #'ReviseItem',
                #{'Item':
                    #{'ItemID': ebay_id, 'StartPrice': new_price_inc}})
        #else:
            ## ReviseInventoryStatus enables change to price and/or quantity
            ## of an active, fixed-price listing. 
            ## The fixed-price listing is identified with the ItemID of the
            ## listing or the SKUvalue of the item
            #api_trading.execute(
                #'ReviseInventoryStatus',
                #{'InventoryStatus':
                    #{'ItemID': ebay_id, 'StartPrice': new_price_inc}})


def revise_ebay_prices(price_data, print=print):
    """Revises multiple eBay prices. Attempts to pack price updates into as few
    ReviseInventoryStatus calls as possible.
    Accepts a list of tuples, each of which contains:
      - ebay_id
      - new_price
      - optional extra values
    """

    trading_api = get_trading_api()

    items = []

    prev_percent = -1000.0
    n_items = len(price_data)

    if n_items == 0:
        print('No prices to update!')
        return

    for i, (ebay_id, new_price, *_) in enumerate(price_data):
        percent = math.floor(100.0 * i / n_items)
        if percent - prev_percent > 9.9:
            print(f' - {int(percent)}% complete...')
        prev_percent = percent

        items.append({'ItemID': ebay_id,
                      'StartPrice': new_price})
        if len(items) == 4:
            # We have four items; submit the price updates.
            revise_inventory_status(items)
            items = []

    if items:
        # If there are unsubmitted items, submit them now.
        revise_inventory_status(items)
    print(' - 100% complete.')
