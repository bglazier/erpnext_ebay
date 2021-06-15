// Copyright (c) 2018, Ben Glazier and contributors
// For license information, please see license.txt

const ems_module = 'erpnext_ebay.erpnext_ebay.doctype.ebay_manager_settings.ebay_manager_settings';

frappe.ui.form.on('eBay Manager Settings', {
    get_current_hostname(frm) {
        frappe.call({
            method: ems_module + '.get_current_hostname'
        }).then(({message}) => {
            if (message) {
                frm.set_value('ebay_live_hostname', message);
            }
        });
    }
});
