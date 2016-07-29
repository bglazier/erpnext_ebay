// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt


frappe.ui.form.on('eBay Listing', {
    onload_post_render: function ebay_listing_onload_post_render (frm) {
        // Disable the category boxes if they are still empty
        for (var i=1; i<=6; i++) {
            // Loop over each level, disabling the select inputs
            var catname = 'category_' + String(i);
            if (frm.fields_dict[catname].df['options'] &&
                    frm.fields_dict[catname].df['options'].length > 0) {
                // Ensure the fields are not disabled (in case callback
                // happened too soon?
                frm.fields_dict[catname].input.disabled = false;
                frm.refresh_field(catname);
            } else {
                // Disable the empty field
                frm.fields_dict[catname].input.disabled = true;
                frm.refresh_field(catname);
            }
        }
    },

    onload: function ebay_listing_onload (frm) {
        // Initial display of the form: set up categories
        frappe.call({
            method: "erpnext_ebay.ebay_categories.check_cache_versions",
            args: {},
            callback: function is_cache_ok (data) {
                // Check if the eBay cache is up to date
                if (data.message[0] && data.message[1]) {
                    // The cache is up to date, set up the categories
                    initial_category_setup(frm);
                } else {
                    // The cache is not up to date, we cannot set up
                    // the categories yet.
                    msgprint('The eBay cache is not up to date, and needs ' +
                             'to be updated. This may take some time.');
                    frappe.call({
                        method: ("erpnext_ebay.ebay_categories" +
                                 ".ensure_updated_cache"),
                        args: {force_categories: false, force_features: false},
                        callback: function () {
                            initial_category_setup(frm);
                        }
                    });
                }
            }
        });
    },

    validate: function validate_listing(frm) {
        // Check the basic data of the form
        if (!check_all_categories_selected(frm)) {
            msgprint(__("You must select a appropriate eBay category!"));
            validated = false;
            return;
        }
    },

    before_submit: function test_listing(frm) {
        // Test submitting the listing to eBay
        msgprint("before_submit");
        frappe.call({
            method: "erpnext_ebay.ebay_listing_utils.test_listing_item",
            args: {doc_name: frm.doc.name},
            callback: function successful_testing (data) {
                // TODO - write this callback to resubmit the document
                //validated = (data.message == 'true');
            }
        });
        // TODO - disable the form/show a waiting thing until the callback
        // returns
        validated = false;
    },

    before_cancel: function cancel_listing(frm) {
        // Cancel listing
        msgprint("This eBay interface is not ready yet!");
        validated = false;
    }
});


function category_change (frm, category_level) {
    // The category on category_level has changed - update the form
    new_val = frm.fields_dict["category_" + String(category_level)].value;
    if (new_val === "0") {
        return;
    }
    frm.doc["category_id_" + String(category_level)] = new_val;
    for (var i=1; i<=category_level; i++) {
        // Disable all the category 'select' inputs for now
        var catname = "category_" + String(i);
        frm.fields_dict[catname].input.disabled = true;
        frm.refresh_field(catname);
    }
    for (i=category_level+1; i<=6; i++) {
        // Blank any category 'select' inputs below the changed level
        catname = "category_" + String(i);
        frm.set_df_property(catname, "options", []);
        frm.set_df_property(catname, "reqd", false);
        frm.fields_dict[catname].input.disabled = true;
        frm.set_value(catname, "0");
        frm.doc["category_id_" + String(i)] = "0";
    }
    frappe.call({
        // Callback to obtain updated category information for the new
        // choice of category
        method: "erpnext_ebay.ebay_categories.client_update_ebay_categories",
        args: {category_level: category_level,
               category_stack: [frm.fields_dict.category_1.value,
                                frm.fields_dict.category_2.value,
                                frm.fields_dict.category_3.value,
                                frm.fields_dict.category_4.value,
                                frm.fields_dict.category_5.value,
                                frm.fields_dict.category_6.value]},
        callback: function update_categories (data) {
            for (var i=1; i<=category_level; i++) {
                // Enable category 'select' inputs above and on the
                // changed level
                var catname = "category_" + String(i);
                frm.fields_dict[catname].input.disabled = false;
                frm.refresh_field(catname);
            }
            catname = "category_" + String(category_level+1);
            if (data.message && data.message.length > 0) {
                // Enable the next level down if it has options
                frm.fields_dict[catname].input.disabled = false;
                frm.set_df_property(catname, "reqd", true);
            }
            // Set the options for the next level down
            frm.set_df_property(catname, "options", data.message);
        }
    });
}


function check_all_categories_selected (frm) {
    // Validation function - check we have no further category choices
    if (!frm.fields_dict['category_1'].df['options']) {
        // Categories are not set up
        return false;
    }
    for (var i=1; i<=6; i++) {
        var catname = 'category_' + String(i);
        if (frm.fields_dict[catname].df['options'] &&
                frm.fields_dict[catname].df['options'].length > 0 &&
                frm.doc['category_id_' + String(i)] === "0") {
            return false;
        }
    }
    return true;
}


function initial_category_setup (frm) {
    // If we have an update-to-date eBay cache, get the category data
    category_stack = [frm.doc.category_id_1,
                      frm.doc.category_id_2,
                      frm.doc.category_id_3,
                      frm.doc.category_id_4,
                      frm.doc.category_id_5,
                      frm.doc.category_id_6];
    frappe.call({
        // Callback to obtain current eBay categories for this listing
        method: "erpnext_ebay.ebay_categories.client_get_ebay_categories",
        args: {category_stack: category_stack},
        callback: function load_categories (data) {

            for (var i=1; i<=6; i++) {
                // Loop over each level, setting up the 'select' inputs
                var catname = 'category_' + String(i);
                frm.set_df_property(catname, "options", data.message[i-1]);
                if (data.message[i-1].length > 0) {
                    if (frm.fields_dict[catname]['input']) {
                        // Enable the field, if it exists yet
                        frm.fields_dict[catname].input.disabled = false;
                    }
                    frm.set_df_property(catname, "reqd", true);
                } else {
                    frm.fields_dict[catname].input.disabled = true;
                }
                frm.set_value(catname, frm.doc['category_id_' + String(i)]);
            }

            // Set up events for changing the categories 'select' inputs
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


