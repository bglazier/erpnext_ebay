// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Manager', {
    refresh: function(frm) {},


    customer_sync: function(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_customers.sync",
            args: {},
            callback: function(r){}
                //cur_frm.reload_doc();
        });
    },


    create_garagesale: function(frm) {
        if (confirm('Have you relisted ended eBay listings?')) {
            // Run it!
            frappe.call({
                method: "erpnext_ebay.garage_sale.run_cron_create_xml",
                args: {},
                callback: function(r){}
            });
        }
    },


    price_sync: function(frm) {
        frappe.call({
            method: "erpnext_ebay.ebay_price_sync.price_sync",
            args: {},
            callback: function(r) {}
        });
    },


    category_sync: function(frm) {
        frappe.call({
            method: "erpnext_ebay.ebay_categories.category_sync",
            args: {},
            callback: function(r){}
        });
    }
});
