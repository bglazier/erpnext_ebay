# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import frappe
from frappe import msgprint
from frappe.utils import cstr

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


import sys
import os.path
sys.path.insert(0, frappe.get_app_path('erpnext_ebay'))


path_to_yaml = os.path.join(os.sep, frappe.utils.get_bench_path(), 'sites', \
               frappe.get_site_path(), 'ebay.yaml')




def get_item_revisions(item_code):

    sql = """
    select
        item_name,
        description
        function_grade,
        grade_details,
        condition,
        tech_details,
        delivery_type,
        accessories_extras,
        power_cable_included,
        power_supply_included,
        remote_control_included,
        case_included,
        warranty_period
    from `tabItem`
    where item_code = '{}'
    """.format(item_code)

    records = frappe.db.sql(sql)

    return records[0][0], records[0][1], records[0][2], records[0][3], records[0][4], \
           records[0][5], records[0][6], records[0][7], records[0][8], records[0][9], \
           records[0][10], records[0][11], records[0][12]



@frappe.whitelist(allow_guest=True)
def revise_generic(item_code):
    """Generic Revise eBay listings"""

    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:

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

        version = 1.0

        body = jtemplate(version, description, function_grade, grade_details, condition, \
                tech_details, delivery_type, accessories_extras, \
                power_cable_included, power_supply_included, remote_control_included, \
                case_included, warranty_period)
        body += "<br><br>The price includes VAT and we can provide VAT invoices."
        body += "<br><br>Universities and colleges - purchase orders accepted - please contact us."
        body += "<br><br>sku: " + item_code


        condition_description = ''
        condition_id_text, condition_id = lookup_condition(condition, 0)

        new_gsp = True

        revision_str = \
            'ReviseItem', {'Item':{'ItemID': ebay_id, \
            'GlobalShipping': new_gsp, \
            'Title': item_name, \
            'Description': body, \
            'ConditionDescription': condition_description, \
            'ConditionID': condition_id \
            }}
        try:
            api_trading = Trading(config_file=path_to_yaml, warnings=True, timeout=20)
            #api_trading.execute(revision_str)

            frappe.msgprint("eBay listing updated!")

        except:

            frappe.msgprint("Error updating eBay listing!")


@frappe.whitelist(allow_guest=True)
def revise_ebay_price(item_code, new_price):
    """Given item_code and price, revise the listing on eBay"""


    #get the ebay id given the item_code
    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:

        new_price_inc = float(new_price) * ugssettings.VAT

        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)
            api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, \
                                'StartPrice':new_price_inc}})

            frappe.msgprint("eBay price has also updated!")

        except:

            frappe.msgprint("Error updating eBay price!")

    return

'''
@frappe.whitelist(allow_guest=True)
def revise_ebay_description(item_code, new_description):
    """<Description> string </Description>
    <DescriptionReviseMode> DescriptionReviseModeCodeType </DescriptionReviseMode>"""

    ebay_id = frappe.get_value('Item', item_code, 'ebay_id')
    if ebay_id:
        try:
            api_trading = Trading(config_file='ebay.yaml', warnings=True, timeout=20)
            api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, \
                                'Description':new_description}})

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
            api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, 'GlobalShipping':new_gsp}})

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
            api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, 'Title':new_title}})

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
            api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, \
                                'ConditionDescription':new_condition}})

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
            api_trading.execute('ReviseItem', {'Item':{'ItemID':ebay_id, 'Quantity':new_qty}})

            frappe.msgprint("eBay qty has been updated!")

        except:

            frappe.msgprint("Error updating eBay price!")
'''