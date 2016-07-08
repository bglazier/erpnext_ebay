// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt


function proc_opts (option_string) {
    if (!option_string) {
        return [];
    }
    var opts_in = option_string.split('\n');
    var opts_out = [];
    for (var i=0; i<opts_in.length; i=i+2) {
        opts_out.push({'value': opts_in[i], 'label': opts_in[i+1]});
    }
    return opts_out;
};


function category_change (frm, category_level) {
    new_val = frm.fields_dict["category_" + String(category_level)].value
    if (new_val == 0) {
        return;
    }
    frm.doc["category_id_" + String(category_level)] = new_val;
    for (var i=1; i<=category_level; i++) {
        var catname = "category_" + String(i);
        frm.fields_dict[catname].input.disabled = true;
        frm.refresh_field(catname);
    }
    for (var i=category_level+1; i<=6; i++) {
        var catname = "category_" + String(i);
        frm.set_df_property(catname, "options", []);
        frm.set_df_property(catname, "reqd", false);
        frm.fields_dict[catname].input.disabled = true;
        frm.set_value(catname, 0);
        frm.doc["category_id_" + String(i)] = 0;
    };
    frappe.call({
        method: "erpnext_ebay.ebay_listing_utils.client_update_ebay_categories",
        args: {category_level: category_level,
               category_stack: [frm.fields_dict.category_1.value,
                                frm.fields_dict.category_2.value,
                                frm.fields_dict.category_3.value,
                                frm.fields_dict.category_4.value,
                                frm.fields_dict.category_5.value,
                                frm.fields_dict.category_6.value]},
        callback: function update_categories (data) {
            for (var i=1; i<=category_level; i++) {
                var catname = "category_" + String(i);
                frm.fields_dict[catname].input.disabled = false;
                frm.refresh_field(catname);
            }
            var catname = "category_" + String(category_level+1);
            if (data.message && data.message.length > 0) {
                frm.fields_dict[catname].input.disabled = false;
                frm.set_df_property(catname, "reqd", true);
            }
            frm.set_df_property(catname, "options", data.message);
        }
    });
};


function check_all_categories_selected (frm) {
    for (var i=1; i<=6; i++) {
        var catname = 'category_' + String(i)
        var has_options = false
        if (frm.fields_dict[catname].df['options']) {
           has_options = frm.fields_dict[catname].df['options'].length > 0
        }
        if (has_options && frm.doc['category_id_' + String(i)] == 0) {
            return false;
        }
    }
    return true;
};


frappe.ui.form.on('eBay Listing', {
    onload: function ebay_listing_onload (frm) {
        category_stack = [frm.doc.category_id_1,
                          frm.doc.category_id_2,
                          frm.doc.category_id_3,
                          frm.doc.category_id_4,
                          frm.doc.category_id_5,
                          frm.doc.category_id_6]
        frappe.call({
            method: "erpnext_ebay.ebay_listing_utils.client_get_ebay_categories",
            args: {category_stack: category_stack},
            callback: function load_categories (data) {

                for (var i=1; i<=6; i++) {
                    var catname = 'category_' + String(i);
                    frm.set_df_property(catname, "options", data.message[i-1]);
                    if (data.message[i-1].length > 0) {
                        frm.set_df_property(catname, "reqd", true);
                    } else {
                        frm.fields_dict[catname].input.disabled = true;
                    }
                    frm.set_value(catname, frm.doc['category_id_' + String(i)]);
                }

                frappe.ui.form.on('eBay Listing', 'category_1', function category_1_change (frm) {
                    category_change(frm, 1);
                });

                frappe.ui.form.on('eBay Listing', 'category_2', function category_2_change (frm) {
                    category_change(frm, 2);
                });

                frappe.ui.form.on('eBay Listing', 'category_3', function category_3_change (frm) {
                    category_change(frm, 3);
                });

                frappe.ui.form.on('eBay Listing', 'category_4', function category_4_change (frm) {
                    category_change(frm, 4);
                });

                frappe.ui.form.on('eBay Listing', 'category_5', function category_5_change (frm) {
                    category_change(frm, 5);
                });
            }
        });
    }
});

frappe.ui.form.on("eBay Listing", "validate", function validate_listing (frm) {
    if (!check_all_categories_selected(frm)) {
        msgprint(__("You must select a appropriate eBay category!"));
        validated = false;
        return false;
    }
});