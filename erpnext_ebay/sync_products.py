


def sync_ebay_items(price_list, warehouse, shopify_item_list):
	shopify_settings = frappe.get_doc("Shopify Settings", "Shopify Settings")
	
	last_sync_condition = ""
	if shopify_settings.last_sync_datetime:
		last_sync_condition = "and modified >= '{0}' ".format(shopify_settings.last_sync_datetime)
	
	item_query = """select name, item_code, item_name, item_group,
		description, has_variants, stock_uom, image, shopify_product_id, shopify_variant_id, 
		sync_qty_with_shopify, net_weight, weight_uom, default_supplier from tabItem 
		where sync_with_shopify=1 and (variant_of is null or variant_of = '') 
		and (disabled is null or disabled = 0) %s """ % last_sync_condition
	
	for item in frappe.db.sql(item_query, as_dict=1):
		if item.shopify_product_id not in shopify_item_list:
			try:
				sync_item_with_shopify(item, price_list, warehouse)
				frappe.local.form_dict.count_dict["products"] += 1
				
			except ShopifyError, e:
				make_shopify_log(title=e.message, status="Error", method="sync_shopify_items", message=frappe.get_traceback(),
					request_data=item, exception=True)
			except Exception, e:
				make_shopify_log(title=e.message, status="Error", method="sync_shopify_items", message=frappe.get_traceback(),
					request_data=item, exception=True)