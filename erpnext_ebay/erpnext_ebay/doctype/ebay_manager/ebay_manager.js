// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Manager', {
//     sync_orders_button(frm) {
//         frappe.call({
//             method: "erpnext_ebay.sync_orders.sync",
//             args: {
//                 site_id: 3
//             },
//             freeze: true,
//             freeze_message: "Syncing eBay customers and orders; this may take some time..."
//         });
//     },

    sync_orders_rest_button(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_orders_rest.sync_orders",
            args: {},
            freeze: true,
            freeze_message: "Syncing eBay customers and orders; this may take some time..."
        });
    },

    sync_transactions_button(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_mp_transactions.sync_mp_transactions",
            args: {},
            freeze: true,
            freeze_message: "Syncing eBay transactions; this may take some time..."
        });
    },

    sync_payouts_button(frm) {
        frappe.call({
            method: "erpnext_ebay.sync_mp_transactions.sync_mp_payouts",
            args: {},
            freeze: true,
            freeze_message: "Syncing eBay payouts; this may take some time..."
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

    sync_shipping_carriers_button(frm) {
        frappe.call({
            method: "erpnext_ebay.erpnext_ebay.doctype.ebay_shipping_carrier."
            + "ebay_shipping_carrier.client_sync_shipping_carriers",
            args: {
                site_id: 3
            },
            freeze: true,
            freeze_message: "Loading eBay UK shipping carriers..."
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
