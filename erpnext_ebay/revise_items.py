# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import sys
import os.path

import frappe
from frappe import msgprint
from frappe.utils import cstr


sys.path.insert(0, frappe.get_app_path('erpnext_ebay'))


from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading
from garage_sale import jtemplate, lookup_condition
import ugssettings


PATH_TO_YAML = os.path.join(os.sep, frappe.utils.get_bench_path(), 'sites', \
               frappe.get_site_path(), 'ebay.yaml')




@frappe.whitelist(allow_guest=True)
def revise_generic_items(item_code):
    """Generic Revise eBay listings"""

    print('HELLO')
    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id > 0:
        
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
        
        body = jtemplate(version, description, function_grade, grade_details, condition, \
                tech_details, delivery_type, accessories_extras, \
                power_cable_included, power_supply_included, remote_control_included, \
                case_included, warranty_period)
        body += "<br><br>The price includes VAT and we can provide VAT invoices."
        body += "<br><br>Universities and colleges - purchase orders accepted - please contact us."
        body += "<br><br>sku: " + item_code
        
        
        condition_description = '' #grade_details
        condition_id_text, condition_id = lookup_condition(condition, 0)

        new_gsp = (delivery_type == 'Standard Parcel')
        
        revision_str = \
            'ReviseItem', {'Item':{ \
            'ItemID': ebay_id, \
            'GlobalShipping': new_gsp, \
            'Title': item_name, \
            'Description': body, \
            'ConditionDescription': condition_description, \
            'ConditionID': condition_id \
            }}
        
        try:
            api_trading = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)
            api_trading.execute(revision_str)
            
        
        except ConnectionConfigError:
            frappe.msgprint("Config file ebay.yaml file not found")
            raise
        
        except StandardError:
            frappe.msgprint("There was a problem using the eBay Api")
            raise
        
        else:
            frappe.msgprint("Success eBay listing updated!", new_price_inc)
        



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
        it.warranty_period
    from `tabItem` it
    where item_code = '{}'
    """.format(item_code)
    
    records = frappe.db.sql(sql)
    
    return records[0][0], records[0][1], records[0][2], records[0][3], records[0][4], \
           records[0][5], records[0][6], records[0][7], records[0][8], records[0][9], \
           records[0][10], records[0][11], records[0][12]


@frappe.whitelist(allow_guest=True)
def revise_ebay_price(item_code, new_price):
    """Given item_code and price, revise the listing on eBay"""

    
    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        
        new_price_inc = float(new_price) * ugssettings.VAT
        
        try:
            api_trading = Trading(config_file=PATH_TO_YAML, warnings=True, timeout=20)
            api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, \
                                'StartPrice':new_price_inc}})
            
        except ConnectionConfigError:
            frappe.msgprint("Config file ebay.yaml file not found")
            raise
        
        except StandardError:
            frappe.msgprint("There was a problem using the eBay Api")
            raise
        
        else:
            frappe.msgprint("Success eBay listing updated!", new_price_inc)


