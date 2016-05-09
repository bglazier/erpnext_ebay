
from __future__ import unicode_literals
import frappe
from frappe import msgprint,_
from frappe.utils import flt
from datetime import date, datetime


import requests.exceptions
from ebay_requests import get_ebay_customers
from ebay_requests import get_orders

#from .utils import make_ebay_log

''''
Order Fields
order.BuyerUserID, order.ShippingAddress.CityName, order.ShippingAddress.CountryName, order.ShippingAddress.Name, order.ShippingAddress.Phone, order.ShippingAddress.PostalCode, order.ShippingAddress.StateOrProvince, order.ShippingAddress.Street1, order.ShippingAddress.Street2])order.BuyerUserID, order.ShippingAddress.CityName, order.ShippingAddress.CountryName, order.ShippingAddress.Name, order.ShippingAddress.Phone, order.ShippingAddress.PostalCode, order.ShippingAddress.StateOrProvince, order.ShippingAddress.Street1, order.ShippingAddress.Street2
'''


@frappe.whitelist()
def sync_new():
    
    orders = get_orders()
    for order in orders.OrderArray.Order:
        create_customer(order)
        
        
def create_customer(order):
	#ebay_settings = frappe.get_doc("Shopify Settings", "Shopify Settings")
	
	#cust_name = (ebay_customer.get("first_name") + " " + (ebay_customer.get("last_name") \
	#	and  ebay_customer.get("last_name") or "")) if ebay_customer.get("first_name")\
	#	else ebay_customer.get("email")
    
    
    try:
        msgprint(order.BuyerUserID)
        customer = frappe.get_doc({
		    "doctype": "Customer",
		    "name": order.BuyerUserID,
		    "customer_name" : order.ShippingAddress.Name,
		    #"ebay_customer_id": ebay_customer.get("id"),
		    #"sync_with_ebay": 1,
		    "customer_group": _("Individual"),
		    "territory": _("All Territories"),
		    "customer_type": _("Individual")
        }).insert()
        
        if customer:
		    create_customer_address(customer, order)
        
        #ebay_customer_list.append(ebay_customer.get("id"))
        frappe.db.commit()
    
    except Exception, e:
        msgprint('Exception on customer creation')
        if e.args[0] and e.args[0].startswith("402"):
			raise e
		#else:
			#make_ebay_log(title=e.message, status="Error", method="create_customer", message=frappe.get_traceback(),
			#	request_data=ebay_customer, exception=True)

        


def create_customer_address(customer, order):
	#for i, address in enumerate(ebay_customer.get("addresses")):
	#	address_title, address_type = get_address_title_and_type(customer.customer_name, i)
    address_title = customer.name
    try:
        msgprint(address_title)
        msgprint(order.ShippingAddress.Street1)
        #msgprint(order.TransactionArray.Transaction.Buyer.Email)
        msgprint(customer.customer_name)
        frappe.get_doc({
			"doctype": "Address",
			#"ebay_address_id": address.get("id"),
			"address_title": address_title,
			"address_type": _("Shipping"),
			"address_line1": order.ShippingAddress.Street1,
			"address_line2": order.ShippingAddress.Street2,
			"city": order.ShippingAddress.CityName,
			"state": order.ShippingAddress.StateOrProvince,
			"pincode": order.ShippingAddress.PostalCode,
			"country": order.ShippingAddress.CountryName,
			"phone": order.ShippingAddress.Phone,
			#"email_id": order.TransactionArray.Transaction.Buyer.Email,
			"customer": customer.name,
			"customer_name":  customer.customer_name
	    }).insert()
    except Exception, e:
        msgprint('Exception on address creation')
		#make_ebay_log(title=e.message, status="Error", method="create_customer_address", message=frappe.get_traceback(),
		#	request_data=ebay_customer, exception=True)
        
        
        
