// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Manager', {
	refresh: function(frm) {

	}
});



frappe.ui.form.on('eBay Manager', 'customer_sync', function(frm) {
    //alert("Importing New Customers...");
	
	frappe.call({
			method: "erpnext_ebay.sync_customers.sync",
			args: {},
			callback: function(r){}
				//cur_frm.reload_doc();
			});
			
	

	
});



frappe.ui.form.on('eBay Manager', 'create_garagesale', function(frm) {
    //alert("Importing New Customers...");


	frappe.call({
			method: "erpnext_ebay.garage_sale.run_cron_create_xml",
			args: {},
			callback: function(r){}
			});
			

});