from __future__ import unicode_literals
import frappe
from frappe import _
import json, math, time
#from .exceptions import ShopifyError
from frappe.utils import get_request_session




import os
import sys
import datetime
import csv
from optparse import OptionParser

#sys.path.insert(0, '%s/../' % os.path.dirname(__file__))

from common import dump

#sys.path.insert(0, "/Users/macmini/frappe-bench/apps/unigreenscheme/ebaysdk-python-master")
#sys.path.append("/Users/macmini/frappe-bench/apps/unigreenscheme/ebaysdk-python-master")
#sys.path.append("/Users/macmini/Documents/dev/ebaysdk-python-master")
sys.path.append("/home/frappe/frappe-bench/apps/erpnext_ebay/ebaysdk-python-master")
sys.path.append("/Library/Python/2.7/site-packages")

import ebaysdk
from ebaysdk.utils import getNodeText
from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


def get_ebay_customers(ignore_filter_conditions=False):
	ebay_customers = []
	filter_condition = ''
	
	if not ignore_filter_conditions:
		filter_condition = None #get_filtering_condition()
    
        ebay_customers = get_orders()
	return ebay_customers
    
    


def get_orders():
    
    orders = None
    ebay_customers = []
    
    CreateTimeFrom = str(datetime.date.today())
    CreateTimeFrom = CreateTimeFrom+'T0:0:0.000Z'
    CreateTimeTo = str(datetime.datetime.now())
    CreateTimeTo = CreateTimeTo[0:len(CreateTimeTo)-3]+'Z'
    
    try:
        #api = Trading(debug=opts.debug, config_file=opts.yaml, appid=opts.appid,
        #              certid=opts.certid, devid=opts.devid, warnings=True, timeout=20)
        
        
        api = Trading(appid='Q20967060-98d1-42f3-8870-95ac890c9dc',devid='abc5d5bb-4394-4b2e-b587-d5f1f1aa9784', certid='3a530102-f035-4215-8c0b-6e81f54b655c',token='AgAAAA**AQAAAA**aAAAAA**2Q3WVg**nY+sHZ2PrBmdj6wVnY+sEZ2PrA2dj6wNloGkCZCDoAudj6x9nY+seQ**FegAAA**AAMAAA**wXWh4nAKbWaTigoWvCN1zxd18pMiJPNhL3eCRYKYDvJticp7UJIwcI8ruTeuyRSVAIPREd4E2f56vIvz84u9Q5mMxUYD5OKI+g8E0yPY3/onyc621vAVcMzi9GGZMvA5Yti45m+eK9NbsuZ40N6rA+AYICkYrYoH72+auU1VzuNrY95NhEkoe79hoa+MWBTXBc6OyGlRoQYPmL2LLpSILdmaYuoc14qBJyyjHIHpmBStA11G6fmrpw4pHxWNUfn434OFjvApXBbShgE7cmhV2HseaDV/jBOU7K1RkpUFXeev4RF2zPl+LSR/+sfsgHwfzRd0XK3mM4s8FIoXwlB27KkzIQCxvVIu2/rAMvasC/PUMSNo07cVYVuj3DG4tYLHywoKod0TM/TlwhqTd4k1kxvyoE7oNzde3hpo8Drhyl6ayzLPu4J97X3B+2I7SiVYVoBpFqHKxsbmGlQznZqxba1QyO/T2yEXORABQ4sOnb+neSnyQLTELEvYwWye6oKAW1Rg9PtAHxEpKuQpEvOUxkmIKEzXc0AEv5Z/lsnR8kNY5uJp9UAHv3p6whbgG3ntnGG/I7fFWETuNdwHJk1EhdOMLTCyRwT6oE630EtdjIYM86kGufeqBUEVG0VZGBUK1rJkEpmzHCaZoOm2+EtYim+HRZq964TkMc0EugLTlu3EvZPDybwSMyZdbP9f/HD+zrDm6KbuNayuzDfQ2XaVV1IplcbAddLQOC5NEo7ao5xlRjxmls7Zx5h+Nl0E5Mhu', config_file=None)
        
        api.execute('GetOrders', {'NumberOfDays': 30})
        #dump(api, full=False)
        
        dom    = api.response_dom()
        orders = api.response_dict()
        myobj  = api.response_obj()
        #orders = dom.getElementsByTagName('OrderArray')
        #orders = mydict['OrderArray']['Order']
        #print 'num of orders %s' % len(orders)
        #for order in orders:
            #print nodeText(item.getElementsByTagName('Order')[0])
            #print order['CheckoutStatus']['Status']['value']
        
        '''if int(orders.ReturnedOrderCountActual) > 0:
            if isinstance(orders.OrderArray.Order,list):
                for order in orders.OrderArray.Order:
                    ebay_customers.append([order.BuyerUserID, order.ShippingAddress.CityName, order.ShippingAddress.CountryName, order.ShippingAddress.Name, order.ShippingAddress.Phone, order.ShippingAddress.PostalCode, order.ShippingAddress.StateOrProvince, order.ShippingAddress.Street1, order.ShippingAddress.Street2])
    
    # order.OrderID, order.orderStatus, order.CheckoutStatus.Status, order.PaidTime, order.CreatedTime, order.Total, order.TransactionArray, order.TransactionArray.Transaction.ItemID, order.TransactionArray.Transaction.Item.SKU
        '''
    except ConnectionError as e:
        print(e)
        print(e.response.dict())
    
    if int(orders.ReturnedOrderCountActual) > 0:
        return orders
    else:
        return None
        
        
        
        
        
''''        
def get_ebay_items(ignore_filter_conditions=False):
	ebay_products = []
	
	filter_condition = ''
	if not ignore_filter_conditions:
		filter_condition = get_filtering_condition()
	
	for page_idx in xrange(0, get_total_pages("products", ignore_filter_conditions) or 1):
		ebay_products.extend(get_request('/admin/products.json?limit=250&page={0}&{1}'.format(page_idx+1, 
			filter_condition))['products'])
            
    
			
	return ebay_products
    
'''

    

    

def verifyAddItemErrorCodes(opts):
    """http://www.utilities-online.info/xmltojson/#.UXli2it4avc
    """

    try:
        api = Trading(debug=opts.debug, config_file=opts.yaml, appid=opts.appid,
                      certid=opts.certid, devid=opts.devid, warnings=False)

        myitem = {
            "Item": {
                "Title": "Harry Potter and the Philosopher's Stone",
                "Description": "This is the first book in the Harry Potter series. In excellent condition!",
                "PrimaryCategory": {"CategoryID": "377aaaaaa"},
                "StartPrice": "1.0",
                "CategoryMappingAllowed": "true",
                "Country": "US",
                "ConditionID": "3000",
                "Currency": "USD",
                "DispatchTimeMax": "3",
                "ListingDuration": "Days_7",
                "ListingType": "Chinese",
                "PaymentMethods": "PayPal",
                "PayPalEmailAddress": "tkeefdddder@gmail.com",
                "PictureDetails": {"PictureURL": "http://i1.sandbox.ebayimg.com/03/i/00/30/07/20_1.JPG?set_id=8800005007"},
                "PostalCode": "95125",
                "Quantity": "1",
                "ReturnPolicy": {
                    "ReturnsAcceptedOption": "ReturnsAccepted",
                    "RefundOption": "MoneyBack",
                    "ReturnsWithinOption": "Days_30",
                    "Description": "If you are not satisfied, return the item for a refund.",
                    "ShippingCostPaidByOption": "Buyer"
                },
                "ShippingDetails": {
                    "ShippingType": "Flat",
                    "ShippingServiceOptions": {
                        "ShippingServicePriority": "1",
                        "ShippingService": "USPSMedia",
                        "ShippingServiceCost": "2.50"
                    }
                },
                "Site": "US"
            }
        }

        api.execute('VerifyAddItem', myitem)

    except ConnectionError as e:
        # traverse the DOM to look for error codes
        for node in api.response.dom().findall('ErrorCode'):
            print("error code: %s" % node.text)

        # check for invalid data - error code 37
        if 37 in api.response_codes():
            print("Invalid data in request")

        print(e)
        print(e.response.dict())


        
        


  
  
  