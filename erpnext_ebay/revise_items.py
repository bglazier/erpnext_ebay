# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import frappe
from frappe import msgprint,_
from frappe.utils import cstr

import sys
sys.path.insert(0,frappe.get_app_path('erpnext_ebay')) 


# Need to add path to sites1.local where ebay.yaml resides
sys.path.insert(0, os.path.join(frappe.utils.get_bench_path(),'sites',frappe.get_site_path()))

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


def get_item_revisions():

    sql = """
    select it.item_name, it.delivery_type, it.description, it.condition, it.function_grade,
    0
    from `tabItem` it
    where it.item_code = '{}'
    """.format(item_code)
    
    records = frappe.db.sql(sql)

    delivery_type = records[0][1]
    
    return records[0][0], records[0][1], records[0][2], records[0][3], records[0][4], records[0][5]



@frappe.whitelist(allow_guest=True)
def revise_generic(item_code):
    """Generic Revise eBay listings
    TODO consider query for all the data instead of passing in?????????????????"""
    
    new_description, new_gsp, new_title, new_description, new_condition, new_qty = get_item_revisions(item_code)
    
    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        new_price_inc = float(new_price) * VAT

        revision_str = \
            'ReviseItem',{'Item':{'ItemID':ebay_id, \
            'Description':new_description, \
            'GlobalShipping':new_gsp, \
            'Title':new_title, \
            'Description':new_description, \
            'ConditionDescription':new_condition, \
            'Quantity':new_qty \
        }}
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)    
            api_trading.execute(revision_str)
            
            frappe.msgprint("eBay listing updated!")
            
        except:
            
            frappe.msgprint("Error updating eBay listing!")


@frappe.whitelist(allow_guest=True)
def revise_ebay_price(item_code, new_price):
    """Given item_code and price, revise the listing on eBay"""
    
    
    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
    
        new_price_inc = float(new_price) * VAT
    
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)    
            api_trading.execute('ReviseItem',{'Item':{'ItemID':ebay_id,'StartPrice':new_price_inc}})
            
            frappe.msgprint("eBay price has also updated!")
            
        except:
            
            frappe.msgprint("Error updating eBay price!")
    
    return

@frappe.whitelist(allow_guest=True)
def revise_ebay_description(item_code, new_description):
    """<Description> string </Description>
    <DescriptionReviseMode> DescriptionReviseModeCodeType </DescriptionReviseMode>"""
    
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)    
            api_trading.execute('ReviseItem',{'Item':{'ItemID':ebay_id,'Description':new_description}})
            
            frappe.msgprint("eBay description has been updated!")
        except:
            
            frappe.msgprint("Error updating eBay price!")

@frappe.whitelist(allow_guest=True)
def revise_ebay_gsp(item_code, new_gsp):
    """<GlobalShipping> boolean </GlobalShipping>"""
    
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)    
            api_trading.execute('ReviseItem',{'Item':{'ItemID':ebay_id,'GlobalShipping':new_gsp}})
            
            frappe.msgprint("eBay GSP has been updated!")
        except:
            
            frappe.msgprint("Error updating eBay price!")

@frappe.whitelist(allow_guest=True)
def revise_ebay_title(item_code, new_title):
    """<Title> string </Title>"""
    
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)    
            api_trading.execute('ReviseItem',{'Item':{'ItemID':ebay_id,'Title':new_title}})
            
            frappe.msgprint("eBay title has been updated!")
        except:
            
            frappe.msgprint("Error updating eBay price!")

@frappe.whitelist(allow_guest=True)
def revise_ebay_condition(item_code, new_condition):    
    """<ConditionDescription> string </ConditionDescription>
    <ConditionID> int </ConditionID>"""
    
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)    
            api_trading.execute('ReviseItem',{'Item':{'ItemID':ebay_id,'ConditionDescription':new_condition}})
            
            frappe.msgprint("eBay condition has been updated!")
        except:
            
            frappe.msgprint("Error updating eBay price!")

@frappe.whitelist(allow_guest=True)
def revise_ebay_qty(item_code, new_qty):
    """<Quantity> int </Quantity>"""
    
    
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)    
            api_trading.execute('ReviseItem',{'Item':{'ItemID':ebay_id,'Quantity':new_qty}})
            
            frappe.msgprint("eBay qty has been updated!")
            
        except:
            
            frappe.msgprint("Error updating eBay price!")
