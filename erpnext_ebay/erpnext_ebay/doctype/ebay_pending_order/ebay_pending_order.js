// Copyright (c) 2021, Ben Glazier and contributors
// For license information, please see license.txt

frappe.ui.form.on('eBay Pending Order', {
    refresh(frm) {
        // Set fieldtype to 'Data' for last_modified and created_time
        // so that we don't display the local timezone
        frm.set_df_property('last_modified', 'fieldtype', 'Data');
        frm.set_df_property('created_time', 'fieldtype', 'Data');
    }
});
