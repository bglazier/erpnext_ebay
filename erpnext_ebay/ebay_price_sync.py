#
# Gets the current active listings on ebay and syncs the prices to ErpNext
#


# Copyright (c) 2013, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins



import frappe
from frappe import msgprint,_
from frappe.utils import cstr
#from datetime import date, datetime, time, timedelta



#from ugscommon import *
#from ugscommonsql import *
#from ugssettings import *

import sys
sys.path.insert(0, "/home/frappe/frappe-bench/apps/erpnext_ebay/erpnext_ebay")
from ebay_active_listings import generate_active_ebay_data




@frappe.whitelist()
def price_sync():
    
    generate_active_ebay_data()
    sync_from_ebay_to_erpnext()




def create_user_task(user, item_code, type, task_details):
    
    frappe.msgbox('Creating task now...')
    
    subject = item_code + """ LISTING AMENDMENT REQUEST"""
    today = datetime.today()
    status = "Open"
    
    if type == "Tested":
        description = "The item did not pass QC and requires amendment as follows:" + task_details
    if type == "QC Fail"
        description = "The item has now been tested and requires amendment as follows:" + task_details
    
    
    task = frappe.new_doc("Task")
    #task.project = self.name

    task.update({
            "subject": subject,
            "status": status,
            "exp_start_date": today,
            "exp_end_date": today,
            "description": description
    })

    task.flags.ignore_links = True
    task.flags.from_project = True
    task.save(ignore_permissions = True)
    task_names.append(task.name)    
    # Need to lot to appraisals also



def sync_from_ebay_to_erpnext():
    
    sql = """
    select sku, price from `zEbayListings`
    """
    
    records = frappe.db.sql(sql, as_dict=True)

    for r in records:
        set_erp_price(r.sku, r.price)




# Simply updates Item Price given item code and price
def set_erp_price(item_code, price):
    
    '''
    # database contains two prices it.standard_rate and ip.price_list_rate
    select ip.item_code, ip.price_list_rate, ip.selling, it.standard_rate from `tabItem Price` ip left join `tabItem` it on it.item_code = ip.item_code
    where ip.price_list_rate <> it.standard_rate;
    '''
    
    sql = """update `tabItem Price` ip
            set ip.price_list_rate = %s 
            where ip.selling = 1 and ip.item_code = '%s' """ %(float(price), item_code) 

    
    try:
        frappe.db.sql(sql, auto_commit = True)

    
    except Exception as inst:
        print("Unexpected error running price fix. Possible missing Item Price for item: ", item_code)
        raise
        return False
    
    
    
    sql2 = """update `tabItem` it
            set it.standard_rate = %s 
            where it.item_code = '%s' """ %(float(price), item_code)
    
    
    try:
        frappe.db.sql(sql2, auto_commit = True)

    
    except Exception as inst:
        print("Unexpected error running price fix. Possible missing Item Price for item: ", item_code)
        raise
        return False
    
    
    return True



