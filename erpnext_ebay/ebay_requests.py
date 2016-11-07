"""Functions to retrieve data from eBay via ebaysdk module and TradingAPI"""

from __future__ import unicode_literals
from __future__ import print_function

import os
import sys
#import datetime

sys.path.insert(0, "/home/frappe/")


import frappe
from frappe import _

from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading


def get_orders():
    """Returns a list of recent orders from the Ebay TradingAPI"""

    orders = None
    ebay_customers = []

    #CreateTimeFrom = str(datetime.date.today())
    #CreateTimeFrom = CreateTimeFrom+'T0:0:0.000Z'
    #CreateTimeTo = str(datetime.datetime.now())
    #CreateTimeTo = CreateTimeTo[0:len(CreateTimeTo)-3]+'Z'

    orders = []
    page = 1
    num_days = frappe.db.get_value(
        'eBay Manager Settings', filters=None, fieldname='ebay_sync_days')
    try:
        if num_days < 1:
            frappe.msgprint('Invalid number of days: ' + str(num_days))
    except TypeError:
        raise ValueError('Invalid type in ebay_sync_days')

    try:
        # Initialize TradingAPI; default timeout is 20.
        api = Trading(config_file='/home/frappe/ebay.yaml', warnings=True, timeout=20)
        while True:
            # TradingAPI results are paginated, so loop until
            # all pages have been obtained
            api.execute('GetOrders', {'NumberOfDays': num_days,
                                      'Pagination': {'EntriesPerPage': 100,
                                                     'PageNumber': page}})

            orders_api = api.response.dict()

            if int(orders_api['ReturnedOrderCountActual']) > 0:
                orders.extend(orders_api['OrderArray']['Order'])
            if orders_api['HasMoreOrders'] == 'false':
                break
            page += 1

    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e

    return orders, num_days


def get_order_transactions(order_id):
    
    order_trans = None
    order_trans = []
    
    try:
        
        api = Trading(config_file='/home/frappe/ebay.yaml', warnings=True, timeout=20)
        
        while True:
            
            api.execute('GetOrderTransactions', {'OrderID': order_id})
            order_trans_api = api.response.dict()
            
            #if int(order_trans_api['ReturnedOrderCountActual']) > 0:
            orders.extend(order_trans_api['TransactionArray']) #['OrderTransactions'])
                


    except ConnectionError as e:
        print(e)
        print(e.response.dict())
        raise e


    return order_trans
    
    
    
    
    
#Ebay Sales Orders
#Code example



# -*- coding: utf-8 -*-
'''
Hank Marquardt
May 26, 2014

Magic -- not really documented properly by *ebay*, the IncludeItemSpecifics is needed to get UPC back in feed 
api.execute('GetItem',{'ItemID': '321394881000','DetailLevel': 'ReturnAll','IncludeItemSpecifics': 'True'})


'''

import os
import sys
import datetime
import cx_Oracle
from optparse import OptionParser

sys.path.insert(0, '%s/../' % os.path.dirname(__file__))

from common import dump

import ebaysdk
from ebaysdk.utils import getNodeText
from ebaysdk.exception import ConnectionError
from ebaysdk.trading import Connection as Trading
version = 1.0

def init_options():
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)

    parser.add_option("-d", "--debug",
                      action="store_true", dest="debug", default=False,
                      help="Enabled debugging [default: %default]")

    (opts, args) = parser.parse_args()
    return opts, args

def getUPCFromItem(ItemID):
    api.execute('GetItem',{'ItemID': ItemID, 'DetailLevel': 'ReturnAll','IncludeItemSpecifics': 'True'})
    item = api.response_dict()
    for attribute in item.Item.ItemSpecifics.NameValueList:
        if attribute.Name == 'UPC':
            return attribute.Value

    return False

def checkDuplicate(orderID):
    cursor.execute('select order_number from amz_order_header where order_number = :ord_no', ord_no = orderID)
    if cursor.fetchone():
        return True

    return False

def processItems(items):
    rtnItems = []
    if isinstance(items.Transaction,list):
        # Multiple items I hope are in array, guess we'll find out eventually
        print "Array Process"
        for item in items.Transaction:
            localItem = {}
            localItem['item_no'] = getUPCFromItem(item.Item.ItemID)[6:11]
            localItem['qty_ord'] = item.QuantityPurchased
            localItem['listprice'] = item.TransactionPrice.value
            localItem['sellprice'] = item.TransactionPrice.value
            localItem['sellcurr'] = '' 
            rtnItems.append(localItem)

    else:
        localItem = {}
        localItem['item_no'] = getUPCFromItem(items.Transaction.Item.ItemID)[6:11]
        localItem['qty_ord'] = items.Transaction.QuantityPurchased
        localItem['listprice'] = items.Transaction.TransactionPrice.value
        localItem['sellprice'] = items.Transaction.TransactionPrice.value
        localItem['sellcurr'] = '' 
        rtnItems.append(localItem)

    return rtnItems

def processOrder(order):
    ordHdr = {}
    ordHdr['ord_no'] = order.OrderID
    # ordHdr['purchase_date'] = order.CreatedTime[0:10]
    ordHdr['ship_customer'] = order.ShippingAddress.Name.upper()
    ordHdr['ship_address1'] = order.ShippingAddress.Street1.upper()
    ordHdr['ship_address2'] = order.ShippingAddress.Street2.upper() if isinstance(order.ShippingAddress.Street2,str) else ''
    ordHdr['ship_address3'] = ''
    ordHdr['ship_city'] = order.ShippingAddress.CityName.upper()
    ordHdr['ship_state'] = order.ShippingAddress.StateOrProvince.upper()
    ordHdr['ship_zip'] = order.ShippingAddress.PostalCode.upper()
    ordHdr['ship_country'] = order.ShippingAddress.Country.upper()
    ordHdr['ship_phone'] = order.ShippingAddress.Phone if isinstance(order.ShippingAddress.Phone,str) else ''
    ordHdr['payment'] = order.MonetaryDetails.Payments.Payment.PaymentAmount.value
    ordHdr['ship_handle'] = '0.00'
    ordHdr['payment_curr'] = 'USD'
    ordHdr['lstatus'] = 'A'
    ordHdr['ship_method'] = ''
    ordHdr['err_flag'] = ''
    
    ordItems = processItems(order.TransactionArray)
    for item in ordItems:
        print "Item Data:"
        item['ord_no'] = ordHdr['ord_no']
        print item
        sql = '''
              insert into amz_order_line (order_number, item_id, qty, item_list_price, item_selling_price,
                selling_price_cur_code, created_by,create_date,last_updated_by,last_update_date) values (
                :ord_no,:item_no,:qty_ord,:listprice,:sellprice,:sellcurr,'EBYIMPORT',SYSDATE,'EBYIMPORT',
                SYSDATE)
        '''
        cursor.execute(sql,item)
        for datum in item:
            print "%s:\t\t%s" % (datum,item[datum])

    sql = '''
               insert into amz_order_header (order_number,purchase_date, shipping_and_handling, ship_customer,
                ship_address1, ship_address2, ship_address3, ship_city, ship_state, ship_country, 
                ship_postal_code, ship_phone_number, payment_amount, payment_currency, created_by,
                create_date,last_updated_by, last_update_date, order_status,ship_method,error_flag,lead_source_code) values (
                :ord_no,SYSDATE,:ship_handle,:ship_customer,:ship_address1,:ship_address2,:ship_address3,:ship_city,
                :ship_state,:ship_country,:ship_zip,:ship_phone,:payment,:payment_curr,'EBYIMPORT',
                SYSDATE,'EBYIMPORT',SYSDATE,:lstatus,:ship_method,:err_flag,'EBAY')
    '''
    print ordHdr
    cursor.execute(sql,ordHdr)
    for datum in ordHdr:
        print "%s:\t\t%s" % (datum, ordHdr[datum])
    tycus.commit()

def getOrders(opts):

    try:
        global api
        api = Trading(debug=opts.debug,config_file = 'ebay.yaml', warnings=True, timeout=20)

        global tycus, cursor 
        tycus = cx_Oracle.connect('<PUT YOUR ORACLE CREDENTIALS HERE>')
        cursor = tycus.cursor()
        cursor.execute("alter session set nls_date_format='YYYY-MM-DD'")

        # Time set to GMT with the +5 offset
        currentTime = datetime.datetime.now()+datetime.timedelta(hours = 5)
        startTime = currentTime + datetime.timedelta(hours = -2)
        api.execute('GetOrders', {'CreateTimeFrom': str(startTime)[0:19], 'CreateTimeTo': str(currentTime)[0:19], 
            'DetailLevel': 'ReturnAll', 'OrderStatus': 'Completed'})
        orders = api.response_dict()
        if int(orders.ReturnedOrderCountActual) > 0:
            print "There are %s orders to process" % orders.ReturnedOrderCountActual
            if isinstance(orders.OrderArray.Order,list):
                for order in orders.OrderArray.Order:
                    if not checkDuplicate(order.OrderID):
                        print order.OrderID
                        processOrder(order)
                    else:
                        print "Order %s already processed and in amz_ tables" % order.OrderID
            else:
                order = orders.OrderArray.Order
                if not checkDuplicate(order.OrderID):
                    print order.OrderID
                    processOrder(order)
                else:
                    print "Order %s already processed and in amz_ tables" % order.OrderID

        cursor.close()
        tycus.close()

    except ConnectionError as e:
        print e


if __name__ == "__main__":
    (opts, args) = init_options()

    print("Ty Ebay fetch order script ver %s" % version )

    getOrders(opts)