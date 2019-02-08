# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import sys
import os.path

import frappe
from frappe import msgprint
#from frappe.utils import cstr


sys.path.insert(0, frappe.get_app_path('erpnext_ebay'))
sys.path.insert(0, "/Users/ben/dev/ebaysdk-python/dist/ebaysdk-2.1.5-py2.7.egg")
sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/ebaysdk-2.1.4-py2.7.egg")
sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/lxml-3.6.4-py2.7-linux-i686.egg")

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading
from garage_sale import jtemplate, lookup_condition
import ugssettings


PATH_TO_YAML = os.path.join(os.sep, frappe.utils.get_bench_path(), 'sites', \
               frappe.get_site_path(), 'ebay.yaml')




@frappe.whitelist(allow_guest=True)
def revise_generic_items(item_code):
    """Generic Revise eBay listings
    
    """

    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id and item_code:
        frappe.msgprint('This Item is on eBay. Please wait while the listing is revised...')

        item_name,\
        description,\
        function_grade,\
        grade_details,\
        condition,\
        tech_details,\
        delivery_type,\
        accessories_extras,\
        power_cable_included,\
        power_supply_included,\
        remote_control_included,\
        case_included,\
        warranty_period\
         = get_item_revisions(item_code)

        version = 0

        body = """<![CDATA["""
        body += jtemplate(version, description, function_grade, grade_details, condition, \
                tech_details, delivery_type, accessories_extras, \
                power_cable_included, power_supply_included, remote_control_included, \
                case_included, warranty_period)
        body += "<br></br>The price includes VAT and we can provide VAT invoices."
        body += "<br></br>Universities and colleges - purchase orders accepted - please contact us."
        body += "<br></br>sku: " + item_code
        body += """]]>"""

        condition_description = '' #grade_details
        condition_id_text, condition_id = lookup_condition(condition, 0)

        new_gsp = (delivery_type == 'Standard Parcel')



        try:
            api_trading = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)

            #EXAMPLE api.execute('ReviseItem',{'Item':{'ItemID':ItemID},'Title':words}
            api_trading.execute('ReviseItem',{
                'Item':{'ItemID': ebay_id},
                'GlobalShipping': new_gsp,
                'Title': item_name,
                'Description': body,
                'ConditionDescription': condition_description,
                'ConditionID': condition_id
                }
                )


        except ConnectionError:
            frappe.msgprint("Config file ebay.yaml file not found")
            raise

        except Exception:
            frappe.msgprint("There was a problem using the eBay Api")
            raise

        else:
            frappe.msgprint("Success eBay listing updated!")
    else:
        frappe.msgprint("There was a problem getting the data")


def get_item_revisions(item_code):

    sql = """
    select
        it.item_name,
        it.description,
        it.function_grade,
        it.grade_details,
        it.condition,
        it.tech_details,
        it.delivery_type,
        it.accessories_extras,
        it.power_cable_included,
        it.power_supply_included,
        it.remote_control_included,
        it.case_included,
        it.warranty_period,
        it.is_auction
    from `tabItem` it
    where item_code = '{}'
    """.format(item_code)

    records = frappe.db.sql(sql)

    return records[0][0], records[0][1], records[0][2], records[0][3], records[0][4], \
           records[0][5], records[0][6], records[0][7], records[0][8], records[0][9], \
           records[0][10], records[0][11], records[0][12]


@frappe.whitelist(allow_guest=True)
def revise_ebay_price(item_code, new_price, is_auction):
    """Given item_code and (ex vat) price, revise the listing on eBay"""


    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id and item_code and new_price:

        try:
            new_price_inc = float(new_price) * ugssettings.VAT
            api_trading = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)

            if is_auction:
                api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, \
                                'StartPrice':new_price_inc}})
            else:
                # ReviseInventoryStatus enables change to price and/or quantity of an active, fixed-price listing. 
                # The fixed-price listing is identified with the ItemID of the listing or the SKUvalue of the item
                api_trading.execute('ReviseInventoryStatus', {'InventoryStatus':{'ItemID':ebay_id, \
                                    'StartPrice':new_price_inc}})

        except ConnectionError:
            return ("Connection Error - possibly ebay.yaml file not found")

        except Exception:
            return ("Price sync. There was a problem using the eBay Api")
            #raise

        else:
            return ("Price sync success - eBay listing updated!")
    else:
        return ("Price Sync Error: There was a problem getting with the item_code, price or ebayid")
