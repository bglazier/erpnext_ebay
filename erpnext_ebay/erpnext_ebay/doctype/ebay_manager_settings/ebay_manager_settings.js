// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

// frappe.ui.form.on('eBay Manager Settings', {
//     refresh: function(frm) { }
// });

frappe.ui.form.on('eBay Manager Settings', 'getebaydetails', function(frm) {
    frappe.call({
        method: "erpnext_ebay.ebay_requests.GeteBayDetails",
        args: {},
        callback: function (r) {}
    });
});

frappe.ui.form.on('eBay Manager Settings', 'check_ebay_cache_version', function(frm) {
    frappe.call({
        method: "erpnext_ebay.ebay_categories.check_cache_version",
        args: {force_categories: false, force_features: false},
        callback: function (r) {}
    });
});
