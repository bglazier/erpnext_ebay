
from __future__ import unicode_literals
from __future__ import print_function


import sys
sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/ebaysdk-2.1.4-py2.7.egg")

sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/lxml-3.6.4-py2.7-linux-i686.egg")


import datetime
from types import MethodType
import string

import frappe
from frappe import msgprint,_
from frappe.utils import cstr

#from ebay_requests import get_orders
from ebaysdk.exception import ConnectionError
#from ebaysdk.finding import Connection as Finding
from ebaysdk.trading import Connection as Trading

import MySQLdb

#import os




@frappe.whitelist()
def show_list():
	
	create_ebay_table()
	
	page = 1
	listings_dict = find_listings(page)
	pages = int(listings_dict['PaginationResult']['TotalNumberOfPages'])
	totalEntries = int(listings_dict['PaginationResult']['TotalNumberOfEntries'])
	i = 0

	while pages >= page:

		for item in listings_dict['ItemArray']['Item']:
			ebay_id = item['ItemId']
			qty = item['Quantity']
			sku = item['SKU']
			price = item['BuyItNowPrice']
			description = item['Description']
			hit_count = item['HitCount']
			site = item['Site']
			title = item['Title']
			#conv_title = title.encode('ascii', 'ignore').decode('ascii')
			#insert_ebay_table(ebay_id, qty, price, MySQLdb.escape_string(conv_title))

			i += 1

		page += 1
		listings_dict = find_listings(page)

	#print(totalEntries, i, duplicate_count)



	
def find_listings(page):
	
	# python -c "import certifi; print certifi.old_where()"
	#os.environ['REQUESTS_CA_BUNDLE'] = '/usr/local/lib/python2.7/dist-packages/certifi/cacert.pem'	
	
	try:
		api_trading = Trading(config_file='/home/frappe/ebay.yaml', warnings=True, timeout=20)
		
		api_request = {
			'EndTimeFrom': "2018-01-30T00:00:00",
			'EndTimeTo': "2018-05-01T00:00:00",
			"Pagination": {
				"EntriesPerPage": 100,
				"PageNumber": page
			},
		'DetailLevel': 'ReturnAll'
		}

		api_trading.execute('GetSellerList', api_request)
		#products = products.dict()
		products = api_trading.response.dict()
	

	except ConnectionError as e:
		print(e)
		print(e.response.dict())
		raise e
		
	return products





def create_ebay_table():
	
	sql = """
		create table if not exists `zEbayListings` (
		`sku` varchar(20),
		`ebay_id` integer,
		`qty` integer,
		`price` float
		)
	"""

	frappe.db.sql(sql, auto_commit = True)
	
	sql = """truncate table `zEbayListings` """
	
	frappe.db.sql(sql, auto_commit = True)
	

def insert_ebay_table(sku, ebay_id, qty, price):
	
	sql = """
	insert into `zEbayListings`
	values('{sku}', {ebay_id}, {qty}, {price})
	""".format(sku=sku, ebay_id=ebay_id, qty=qty, price=price)
	
	
	frappe.db.sql(sql, auto_commit = True)
	
	



