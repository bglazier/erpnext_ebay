// Copyright (c) 2016, Ben Glazier and contributors
// For license information, please see license.txt

var MAX_LEVEL = 6;

frappe.ui.form.on('eBay Listing', {
    do_a_thing: function do_a_thing_change (frm) {
        // clicked the damn button!
        console.log(frm);
    },

    onload_post_render: function ebay_listing_onload_post_render (frm) {
        // Event called after the form is rendered
        // Lock the forms until the initial data load completes
        lock_forms(frm, 0);
    },

    onload: function ebay_listing_onload (frm) {
        // Event called before the form is rendered
        // Global variable for various properties
        frm.ebay_data = {};
        // Initial display of the form: set up categories
        frappe.call({
            method: "erpnext_ebay.ebay_categories.check_cache_versions",
            args: {},
            callback: function is_cache_ok (data) {
                // Check if the eBay cache is up to date
                if (data.message[0] && data.message[1]) {
                    // The cache is up to date, set up the form
                    initial_form_setup(frm);
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
                            initial_form_setup(frm);
                        }
                    });
                }
            }
        });

        // Get the supported listing types
        frappe.call({
            method: "erpnext_ebay.ebay_categories.supported_listing_types",
            args: {},
            callback: function (data) {
                // Set up the listing type selection
                frm.set_df_property('ebay_listing_type_select', 'options',
                                    data.message);
            }
        });
        if (frm.doc['ebay_listing_type']) {
            frm.set_value('ebay_listing_type', frm.doc.ebay_listing_type);
        }
    },

    validate: function validate_listing(frm) {
        // Check a category is selected
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
    },

    'ebay_conditionid_select': function (frm) {
        // Change of conditionID - store in document field
        frm.doc['ebay_conditionid'] =
            frm.fields_dict['ebay_conditionid_select'].value;
        // Check if condition description is enabled/disabled
        update_condition_description_status(frm, false);
    },

    'ebay_listing_type_select': function (frm) {
        // Change of listing type - store in document field
        frm.doc['ebay_listing_type'] =
            frm.fields_dict['ebay_listing_type_select'].value;
        update_listing_durations(frm);
    },

    'ebay_listing_duration_select': function (frm) {
        // Change of listing duration - store in document field
        frm.doc['ebay_listing_duration'] =
            frm.fields_dict['ebay_listing_duration_select'].value;
    }
});

/*
function get_last_category(frm) {
    // Return the ID of the last selected category on the form
    var last_category = 0;
    for (var i=1; i<=MAX_LEVEL; i++) {
        var catname = 'category_' + String(i);
        var value = frm.fields_dict[catname].value;
        if (value && (value > 0)) {
            last_category = value;
        } else {
            break;
        }
    }
    return last_category;
}*/


function update_condition_description_status(frm) {
    // Update the condition description field
    if ((frm.fields_dict['ebay_conditionid_select'].input.disabled) ||
            (frm.fields_dict['ebay_conditionid_select'].value > 1500)) {
        // Allow a condition description
        frm.fields_dict['condition_description'].input.disabled = false;
        frm.set_df_property(
            'condition_description', 'label',
            'Condition description (optional)');
    } else {
        // No condition description for this ConditionID
        frm.fields_dict['condition_description'].input.disabled = true;
        frm.set_value('condition_description', '');
        frm.set_df_property(
            'condition_description', 'label',
            'Condition description (select an appropriate condition)');
    }
}


function update_listing_durations(frm) {
    // Update the listing duration list based on the currently
    // selected listing type and category
    listing_durations_obj = frm.ebay_data.category_data.listing_durations
    listing_type = frm.fields_dict['ebay_listing_type_select'].value;
    if (!listing_type) {
        frm.fields_dict['ebay_listing_duration_select'].input.disabled = true;
        frm.set_df_property('ebay_listing_duration_select', 'label',
                            'Length of listing (select a listing type)');
        return
    }
    var listing_durations = listing_durations_obj[listing_type];
    frm.fields_dict['ebay_listing_duration_select'].input.disabled = false;
    frm.set_df_property('ebay_listing_duration_select', 'options',
                        listing_durations)
        frm.set_df_property('ebay_listing_duration_select', 'label',
                            'Length of listing');
    valid_value = false
    for (i=0; i<listing_durations.length; i++) {
        if (listing_durations[i].value
            == frm.fields_dict['ebay_listing_duration_select'].value) {
            valid_value = true
        }
    }
    if (!valid_value) {
        frm.set_value('ebay_listing_duration_select', null);
    }
}


function lock_forms(frm, category_level) {
    // The category has changed OR initial form rendering - lock the form
    // The form will subsequently be unlocked after a callback with the new
    // category information

    if (category_level == 0) {
        // Initial locking
        // Disable the category boxes if they are still empty
        for (var i=1; i<=MAX_LEVEL; i++) {
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
    } else {
        // Category update locking
        // Category select inputs
        for (var i=1; i<=category_level; i++) {
            // Disable all the category 'select' inputs for now
            var catname = "category_" + String(i);
            frm.fields_dict[catname].input.disabled = true;
            frm.refresh_field(catname);
        }
        for (i=category_level+1; i<=MAX_LEVEL; i++) {
            // Blank any category 'select' inputs below the changed level
            catname = "category_" + String(i);
            frm.set_df_property(catname, "options", []);
            frm.set_df_property(catname, "reqd", false);
            frm.fields_dict[catname].input.disabled = true;
            frm.set_value(catname, "0");
            frm.doc["category_id_" + String(i)] = "0";
        }
    }

    // Uncheck 'is this a listing category?' checkbox
    frm.fields_dict['ebay_is_listing_category'].input.disabled = true;
    frm.fields_dict['ebay_is_listing_category'].set_input(false);

    // Lock the condition fields
    frm.fields_dict['ebay_conditionid_select'].input.disabled = true;

    frm.set_df_property('condition_description', 'label',
                        'Condition description');
    frm.fields_dict['condition_description'].input.disabled = true;

    frm.set_df_property('ebay_conditionhelpurl', 'value', '');

    // Lock the listing duration field
    frm.fields_dict['ebay_listing_duration_select'].input.disabled = true;
}


function unlock_update(frm, category_level, onload, data) {
    // The categories have been updated (onload or a change).
    // Unlock and update the fields which depend on the category.

    var category_options = data.message.category_options;

    if (onload) {
        // We have a complete set of categories; update everything
        min_level = 1;
        max_level = MAX_LEVEL;
    } else {
        // We only (possibly) have an options list at category_level
        min_level = category_level+1;
        max_level = category_level+1;
        for (var i=1; i<=category_level; i++) {
            // Enable category 'select' inputs above and on the
            // changed level
            var catname = "category_" + String(i);
            frm.fields_dict[catname].input.disabled = false;
            frm.refresh_field(catname);
        }
    }

    // Set the options for all provided levels
    for (var i=min_level; i<=max_level; i++) {
        var catname = "category_" + String(i);
        frm.set_df_property(catname, "options", category_options[i-1]);
        if (category_options[i-1] && category_options[i-1].length > 0) {
            // Enable the level if it has options
            frm.fields_dict[catname].input.disabled = false;
            frm.set_df_property(catname, "reqd", true);
        } else {
            // It becomes/remains disabled
            frm.fields_dict[catname].input.disabled = true;
        }
    }

    // Update 'is this a listing category?' checkbox
    if (data.message.is_listing_category) {
        frm.fields_dict['ebay_is_listing_category'].set_input(true);
    } else {
        frm.fields_dict['ebay_is_listing_category'].set_input(false);
    }

    // Update condition values
    if (!data.message.condition_values) {
        // If there are no condition values then this is probably
        // not a listing category
        data.message_condition_enabled = 'Disabled';
    }
    switch(data.message.condition_enabled) {
        case 'Disabled':
            frm.set_df_property('ebay_conditionid_select', 'options', []);
            frm.fields_dict['ebay_conditionid_select'].input.disabled = true;
            frm.set_df_property('ebay_conditionid_select', 'reqd', false);
            frm.set_df_property(
                'ebay_conditionid_select', 'label',
                'Condition (disabled for this category)');
            frm.set_value('ebay_conditionid_select', null);
            break;
        case 'Enabled':
            data.message.condition_values.push({'label': '', 'value': 0});
            frm.set_df_property('ebay_conditionid_select', 'options',
                                data.message.condition_values);
            frm.fields_dict['ebay_conditionid_select'].input.disabled = false;
            frm.set_df_property('ebay_conditionid_select', 'reqd', false);
            frm.set_df_property(
                'ebay_conditionid_select', 'label',
                'Condition (optional for this category)');
            break;
        case 'Required':
            frm.set_df_property('ebay_conditionid_select', 'options',
                                data.message.condition_values);
            frm.fields_dict['ebay_conditionid_select'].input.disabled = false;
            frm.set_df_property('ebay_conditionid_select', 'reqd', true);
            frm.set_df_property(
                'ebay_conditionid_select', 'label',
                'Condition (required for this category)');
            break;
        default:
            frappe.throw('No eBay ConditionEnabled value passed!');
            break;
    }

    // Update condition description field status
    update_condition_description_status(frm);

    // Update condition help URL
    url = data.message['condition_help_URL'];
    if (url) {
        url_html = 'For more information about these item conditions go to '
                   +'<a href="' + url + '">' + url + '</a>'
        frm.set_df_property('ebay_conditionhelpurl', 'options', url_html);
    } else {
        frm.set_df_property('ebay_conditionhelpurl', 'options', '');
    }

    // Update listing duration field
    update_listing_durations(frm);
}


function category_change (frm, category_level) {
    // The category on category_level has changed - update the form
    new_val = frm.fields_dict["category_" + String(category_level)].value;
    if (new_val === "0") {
        return;
    }
    frm.doc["category_id_" + String(category_level)] = new_val;

    // Lock those parts of the form that will be affected by a category change
    lock_forms(frm, category_level);

    var category_stack = [];
    for (i=1; i<=MAX_LEVEL; i++) {
        catname = "category_" + String(i);
        category_stack.push(frm.fields_dict[catname].value);
    }

    frappe.call({
        // Callback to obtain updated category information for the new
        // choice of category
        method: "erpnext_ebay.ebay_categories.client_get_new_categories_data",
        args: {category_level: category_level,
               category_stack: category_stack},
        callback: function (data) {
            frm.ebay_data.category_data = data.message;
            unlock_update(frm, category_level, false, data);
        }
    });
}


function check_all_categories_selected (frm) {
    // Validation function - check we have no further category choices
    if (!frm.fields_dict['category_1'].df['options']) {
        // Categories are not set up
        return false;
    }
    for (var i=1; i<=MAX_LEVEL; i++) {
        var catname = 'category_' + String(i);
        if (frm.fields_dict[catname].df['options'] &&
                frm.fields_dict[catname].df['options'].length > 0 &&
                frm.doc['category_id_' + String(i)] === "0") {
            return false;
        }
    }
    return true;
}


function initial_form_setup (frm) {
    // If we have an update-to-date eBay cache, get the category etc. data
    var category_stack = [];
    for (var i=1; i<=MAX_LEVEL; i++) {
        catname = "category_id_" + String(i);
        category_stack.push(frm.doc[catname]);
    }

    // Set the value for the conditionID from the document
    frm.set_value('ebay_conditionid_select', frm.doc['ebay_conditionid']);

    frappe.call({
        // Callback to obtain current eBay categories for this listing
        method: "erpnext_ebay.ebay_categories.client_get_new_categories_data",
        args: {category_level: 0,
               category_stack: category_stack},
        callback: function load_categories (data) {

            // Unlock the form and update
            frm.ebay_data.category_data = data.message;
            unlock_update(frm, 0, true, data);

            // Set the category select boxes according to the document
            for (var i=1; i<=MAX_LEVEL; i++) {
                var catname = 'category_' + String(i);
                frm.set_value(catname, frm.doc['category_id_' + String(i)]);
            }

            // Set up events for changing the categories 'select' inputs
            function category_change_function (frm, cat_level) {
                return function (frm) {
                    category_change(frm, cat_level);
                }
            }

            for (i=1; i<=MAX_LEVEL; i++) {
                catname = 'category_' + String(i);
                frappe.ui.form.on('eBay Listing', catname,
                                  category_change_function(frm, i));
            }
        }
    });
}


