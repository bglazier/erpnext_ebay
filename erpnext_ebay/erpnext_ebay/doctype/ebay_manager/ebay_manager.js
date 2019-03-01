// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Manager', {
    sync_orders_button: function(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_orders.sync",
            args: {
                site_id: 3
            },
            freeze: true,
            freeze_message: "Syncing eBay UK customers and orders; this may take some time..."
        });
    },

    sync_listings_button: function(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_listings.sync",
            args: {
                site_id: 3
            },
            freeze: true,
            freeze_message: "Syncing eBay UK listings; this may take some time..."
        });
    },

    sync_categories_button: function(frm) {
        frappe.call({
            method: "erpnext_ebay.ebay_categories.category_sync",
            args: {
                site_id: 3,
                force_override_categories: true,
                force_override_features: true
            },
            freeze: true,
            freeze_message: "Loading eBay UK categories; this may take some time..."
        });
    },

    price_sync_button: function(frm) {
        frappe.call({
            method: "erpnext_ebay.ebay_price_sync.price_sync",
            args: {},
        });
    },

    create_garagesale_button: function(frm) {
        //var r == (confirm('Have you relisted ended eBay listings?')) 
        //if (r == true){
        frappe.call({
                method: "erpnext_ebay.garage_sale.run_cron_create_xml",
                args: {}
            });
        //}
    }
});
