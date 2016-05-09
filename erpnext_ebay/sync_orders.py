

from __future__ import unicode_literals
import frappe
from frappe import _
from .exceptions import ShopifyError
from .utils import make_shopify_log
from .sync_products import make_item
from .sync_customers import create_customer
from frappe.utils import cstr, flt, nowdate
from .shopify_requests import get_request, get_shopify_orders
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice






def create_sales_order(shopify_order, shopify_settings, company=None):
	so = frappe.db.get_value("Sales Order", {"shopify_order_id": shopify_order.get("id")}, "name")
	if not so:
		so = frappe.get_doc({
			"doctype": "Sales Order",
			"naming_series": shopify_settings.sales_order_series or "SO-Shopify-",
			"shopify_order_id": shopify_order.get("id"),
			"customer": frappe.db.get_value("Customer", {"shopify_customer_id": shopify_order.get("customer").get("id")}, "name"),
			"delivery_date": nowdate(),
			"selling_price_list": shopify_settings.price_list,
			"ignore_pricing_rule": 1,
			"apply_discount_on": "Net Total",
			"discount_amount": get_discounted_amount(shopify_order),
			"items": get_order_items(shopify_order.get("line_items"), shopify_settings),
			"taxes": get_order_taxes(shopify_order, shopify_settings)
		})
		
		if company:
			so.update({
				"company": company,
				"status": "Draft"
			})

		so.save(ignore_permissions=True)
		so.submit()

	else:
		so = frappe.get_doc("Sales Order", so)
		
	frappe.db.commit()
	return so
    
def create_sales_invoice(shopify_order, shopify_settings, so):
	if not frappe.db.get_value("Sales Invoice", {"shopify_order_id": shopify_order.get("id")}, "name") and so.docstatus==1 \
		and not so.per_billed:
		si = make_sales_invoice(so.name)
		si.shopify_order_id = shopify_order.get("id")
		si.naming_series = shopify_settings.sales_invoice_series or "SI-Shopify-"
		si.is_pos = 1
		si.cash_bank_account = shopify_settings.cash_bank_account
		si.submit()
		frappe.db.commit()

def create_delivery_note(shopify_order, shopify_settings, so):
	for fulfillment in shopify_order.get("fulfillments"):
		if not frappe.db.get_value("Delivery Note", {"shopify_order_id": fulfillment.get("id")}, "name") and so.docstatus==1:
			dn = make_delivery_note(so.name)
			dn.shopify_order_id = fulfillment.get("order_id")
			dn.shopify_fulfillment_id = fulfillment.get("id")
			dn.naming_series = shopify_settings.delivery_note_series or "DN-Shopify-"
			dn.items = get_fulfillment_items(dn.items, fulfillment.get("line_items"), shopify_settings)
			dn.save()
			frappe.db.commit()