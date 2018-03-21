
from __future__ import unicode_literals
from __future__ import print_function


import __builtin__ as builtins


import sys
sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/ebaysdk-2.1.4-py2.7.egg")

sys.path.insert(0, "/usr/local/lib/python2.7/dist-packages/lxml-3.6.4-py2.7-linux-i686.egg")


import datetime
from types import MethodType
import string

import frappe
from frappe import msgprint,_
from frappe.utils import cstr

from ebaysdk.exception import ConnectionError
#from ebaysdk.finding import Connection as Finding
from ebaysdk.trading import Connection as Trading

import MySQLdb


# Utility function
def better_print(*args, **kwargs):
    with open ("/home/frappe/runoutput", "a") as f:
        builtins.print (file=f, *args, **kwargs)

print = better_print


@frappe.whitelist()
def show_list():
	
	vat = 1.2
	create_ebay_listings_table()
	
	page = 1
	listings_dict = get_myebay_selling_request(page)
	pages = int(listings_dict['ActiveList']['PaginationResult']['TotalNumberOfPages'])
	#timestamp = listings_dict['Timestamp']
	
	while pages >= page:

		for item in listings_dict['ActiveList']['ItemArray']['Item']:
			ebay_id = item['ItemID']
			qty = item['QuantityAvailable']
			try:
				sku = item['SKU']
			except:
				sku = ''
			#price = item['BuyItNowPrice']['value']
			#THSI IS 0    	print(item['BuyItNowPrice']['value'])
			#Example: {'_currencyID': 'USD', 'value': '0.0'}   print(item['BuyItNowPrice'])
			curr_price = item['SellingStatus']['CurrentPrice']['value']
			currency = item['SellingStatus']['CurrentPrice']['_currencyID']  # or ['Currency']
			print(currency)
			#converted_price = item['ListingDetails]['ConvertedBuyItNowPrice']['value']
			#description = item['Description']
			hit_count = 0 #item['HitCount']
			watch_count = 0 #item['WatchCount']
			question_count = 0 #item['TotalQuestionCount']
			site = '' #item['Site']
			#title = item['Title']
			#conv_title = title.encode('ascii', 'ignore').decode('ascii')
			#new_title = MySQLdb.escape_string(conv_title)
			insert_ebay_listing(sku, ebay_id, qty, (curr_price/vat), site, hit_count, watch_count, question_count)

		page += 1
		if pages >= page:
			listings_dict = get_myebay_selling_request(page)
		else:
			break

@frappe.whitelist()
def show_listOLD():
	
	create_ebay_listings_table()
	
	page = 1
	listings_dict = get_seller_list(page)
	pages = int(listings_dict['PaginationResult']['TotalNumberOfPages'])
	#timestamp = listings_dict['Timestamp']
	
	while pages >= page:

		for item in listings_dict['ItemArray']['Item']:
			ebay_id = item['ItemID']
			qty = item['Quantity']
			try:
				sku = item['SKU']
			except:
				sku = ''
			price = item['BuyItNowPrice']['value']
			#THSI IS 0    	print(item['BuyItNowPrice']['value'])
			#Example: {'_currencyID': 'USD', 'value': '0.0'}   print(item['BuyItNowPrice'])
			curr_price = item['SellingStatus']['CurrentPrice']['value']
			currency = item['SellingStatus']['CurrentPrice']['_currencyID']  # or ['Currency']
			print(currency)
			#converted_price = item['ListingDetails]['ConvertedBuyItNowPrice']['value']
			#description = item['Description']
			hit_count = 0 #item['HitCount']
			watch_count = 0 #item['WatchCount']
			question_count = 0 #item['TotalQuestionCount']
			site = item['Site']
			#title = item['Title']
			#conv_title = title.encode('ascii', 'ignore').decode('ascii')
			#new_title = MySQLdb.escape_string(conv_title)
			insert_ebay_listing(sku, ebay_id, qty, curr_price, site, hit_count, watch_count, question_count)

		page += 1
		if pages >= page:
			listings_dict = get_seller_list(page)
		else:
			break




def get_myebay_selling_request(page):
	
	# python -c "import certifi; print certifi.old_where()"
	#os.environ['REQUESTS_CA_BUNDLE'] = '/usr/local/lib/python2.7/dist-packages/certifi/cacert.pem'	
	
	try:
		api_trading = Trading(config_file='/home/frappe/ebay.yaml', warnings=True, timeout=20)
		
		#datetime.today().format('yyyy-mm-ddThh:mm:ss')
		
		api_request = {
		"ActiveList":{
			"Include": True,
			"Pagination": {
				"EntriesPerPage": 100,
				"PageNumber": page
			}
		},
		'DetailLevel': 'ReturnAll'
		}
		
		
		# activelist = api.execute('GetMyeBaySelling', {'ActiveList': True,'DetailLevel': 'ReturnAll','PageNumber': page})

		api_trading.execute('GetMyeBaySelling', api_request)
		products = api_trading.response.dict()
	

	except ConnectionError as e:
		print(e)
		print(e.response.dict())
		raise e
		
	return products




	
def get_seller_list(page):
	
	# python -c "import certifi; print certifi.old_where()"
	#os.environ['REQUESTS_CA_BUNDLE'] = '/usr/local/lib/python2.7/dist-packages/certifi/cacert.pem'	
	
	try:
		api_trading = Trading(config_file='/home/frappe/ebay.yaml', warnings=True, timeout=20)
		
		#datetime.today().format('yyyy-mm-ddThh:mm:ss')
		
		api_request = {
			'EndTimeFrom': "2018-03-22T00:00:00",
			'EndTimeTo': "2018-05-01T00:00:00",
			"Pagination": {
				"EntriesPerPage": 100,
				"PageNumber": page
			},
		'DetailLevel': 'ReturnAll'
		}
		
		
		# activelist = api.execute('GetMyeBaySelling', {'ActiveList': True,'DetailLevel': 'ReturnAll','PageNumber': page})

		api_trading.execute('GetSellerList', api_request)
		#products = products.dict()
		products = api_trading.response.dict()
	

	except ConnectionError as e:
		print(e)
		print(e.response.dict())
		raise e
		
	return products





def create_ebay_listings_table():
	
	sql = """
		create table if not exists `zEbayListings` (
		`sku` varchar(20),
		`ebay_id` varchar(38),
		`qty` integer,
		`price` decimal(18,6),
		`site` varchar(6),
		`hit_count` integer,
		`watch_count` integer,
		`question_count` integer
		)
	"""

	frappe.db.sql(sql, auto_commit = True)
	
	sql2 = """truncate table `zEbayListings` """
	
	frappe.db.sql(sql2, auto_commit = True)
	

def insert_ebay_listing(sku, ebay_id, qty, price, site, hits, watches, questions):
	
	sql = """
	insert into `zEbayListings`
	values('{sku}', '{ebay_id}', {qty}, {price}, '{site}', {hit_count}, {watch_count}, {question_count})
	""".format(sku=sku, ebay_id=ebay_id, qty=qty, price=price, site=site, hit_count=hits, watch_count=watches, question_count=questions)
	
	
	frappe.db.sql(sql, auto_commit = True)
	
	



