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
