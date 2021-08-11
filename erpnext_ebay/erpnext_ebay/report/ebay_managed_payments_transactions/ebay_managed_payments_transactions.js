// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["eBay Managed Payments Transactions"] = {
    "filters": [
        {
            "fieldname": "start_date",
            "label": "From Date",
            "fieldtype": "Date",
            "default": null
        },
        {
            "fieldname": "end_date",
            "label": "To Date",
            "fieldtype": "Date",
            "default": null
        },
    ],
    onload(report) {
        report.page.add_inner_button("Update data archive", () => {
            const start_date = report.get_filter_value('start_date');
            const end_date = report.get_filter_value('end_date');
            if (!(start_date && end_date)) {
                frappe.msgprint('Must set start and end dates!');
                return;
            }
            frappe.dom.freeze('Archiving transaction data...');
            frappe.call({
                method: "erpnext_ebay.sync_mp_transactions.archive_transactions",
                args: {
                    start_date: start_date,
                    end_date: end_date
                },
                always: () => {
                    frappe.dom.unfreeze();
                },
                callback: (r) => {
                    frappe.msgprint("eBay Managed Payments transactions updated.");
//                     frappe.dom.unfreeze();
                }
            });
        });
    }
};
