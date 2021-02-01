// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Manager', {
    sync_orders_button(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_orders.sync",
            args: {
                site_id: 3
            },
            freeze: true,
            freeze_message: "Syncing eBay customers and orders; this may take some time..."
        });
    },

    sync_listings_button(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_listings.sync",
            args: {
                site_id: 3
            },
            freeze: true,
            freeze_message: "Syncing eBay UK listings; this may take some time..."
        });
    },

    sync_categories_button(frm) {
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

    update_ebay_data(frm) {
        frappe.call({
            method: "erpnext_ebay.ebay_active_listings.update_ebay_data",
            args: {multiple_error_sites: ["UK"]},
            freeze: true,
            freeze_message: "Updating eBay data..."
        });
    },

});
