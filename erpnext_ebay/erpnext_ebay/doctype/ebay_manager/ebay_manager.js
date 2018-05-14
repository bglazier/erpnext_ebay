// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Manager', {
	refresh: function(frm) {
	
	}
});

// TEMPLATE
// frappe.ui.form.on('eBay Manager', 'button name', function(frm) {
	//  method: functionname

frappe.ui.form.on('eBay Manager', 'customer_sync', function(frm) {
	
	frappe.call({
			method: "erpnext_ebay.sync_customers.sync",
			args: {},
			callback: function(r){}
				//cur_frm.reload_doc();
			});

});



frappe.ui.form.on('eBay Manager', 'create_garagesale', function(frm) {
	//alert("Importing New Customers...");
	
	//if export_date > get_today()
	//	{frappe.msgprint("Invalid date")}
	
	frappe.call({
			method: "erpnext_ebay.garage_sale.run_cron_create_xml",
			args: {},
			callback: function(r){}
			});


});


frappe.ui.form.on('eBay Manager', 'price_sync', function(frm) {
	
    var r = ''
	frappe.call({
			method: "erpnext_ebay.ebay_price_sync.price_sync",
			args: {},
			callback: function(r){}
			});


});
