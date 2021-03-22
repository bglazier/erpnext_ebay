// Extend core Item doctype 


function get_online_selling_items(frm, item_code) {
    // Get Online Selling Items
    frappe.call({
        method: 'erpnext_ebay.custom_methods.item_methods.item_platform_async',
        args: {
            'item_code': item_code
        }
    }).then(({message: osi_list}) => {
        // Add Online Selling Items, but don't dirty the form
        if (!(osi_list && osi_list.length)) {
            frm.get_field('online_selling_section').collapse(true);
            frappe.ui.form.trigger("Item", "online_selling_async_complete");
            return;
        }
        frm._dirty = frm.dirty;
        frm.dirty = () => {};
        osi_list.forEach(osi_dict => {
            let child = frm.add_child('online_selling_items');
            Object.assign(child, osi_dict);
        });
        frm.doc.online_selling_items.forEach((child, index) => {
            child.idx = index + 1;
        });
        frm.refresh_field('online_selling_items');
        frm.get_field('online_selling_section').collapse(false);
        frm.dirty = frm._dirty;
        // Delay the trigger so that updates have occurred first
        // following a save or similar (e.g. from after_save event)
        setTimeout(() => {
            frappe.ui.form.trigger("Item", "online_selling_async_complete");
        }, 1);
    });
}


frappe.ui.form.on("Item", {

    onload_post_render(frm, doctype, docname) {
        const field = frm.fields_dict['online_selling_items'];
        field.grid.sortable_status = false;
        field.grid.static_rows = true;
        field.grid.refresh();
        frappe.ui.form.trigger('Item', 'get_online_selling');
    },

    after_save(frm, doctype, docname) {
        get_online_selling_items(frm, docname);
    },

    get_online_selling(frm, doctype, docname) {
        get_online_selling_items(frm, docname);
    },

    auto_create_slideshow(frm, doctype, docname) {
        // Save document before auto creating slideshow
        frm.save("Save",
            function(r) { 
                frappe.ui.form.trigger('Item', '_auto_create_slideshow');
            }
        );
    },

    _auto_create_slideshow(frm, doctype, docname) {

        const item_code = docname;

        // Create the dialog
        const d = new frappe.ui.Dialog({
            'fields': [
                {'fieldname': 'ht', 'fieldtype': 'HTML'}
            ],
        });
        d.num_images = 0;
        d.$modal = d.$wrapper.find('.modal-dialog').parent();
        d.$modal.on('hidden.bs.modal', function (e) {
            // Ensure the modal is deleted on exit
            d.$modal.empty();
            d.$modal.remove();
        })
        d.$modal.attr('data-keyboard', false);
        d.$modal.attr('data-backdrop', "static");

        const html = '<p id="ss_maintext">Processing image <span id="ssimg_id">1</span> of ' +
                '<span id="ssimg_n">??</span>, please wait...</p>' +
                '<div id="slideshow_table">' +
                '</div>'
        d.fields_dict.ht.$wrapper.html(html);
        d.set_title('Processing images');
        d.no_cancel();
        d.show();

        frm.slideshow_dialog = d;

        // If an rte_id for this form does not already exist, create one 
        if (!frm.rte_id) {
            let rand_id = Math.floor(Math.random() * 100000) + 1;
            frm.rte_id = "rte_" + frappe.session.user + "_" + rand_id;
        }

        // Set a tag matching this item and dialog
        let rand_id = Math.floor(Math.random() * 100000) + 1;
        frm.slideshow_dialog.tag = item_code + "_" + rand_id;

        // Call the server - process the images
        // Wait until the #slideshow_table is created before proceeding
        let checkExist = setInterval(function() {
            if ($('#slideshow_table').length) {
                clearInterval(checkExist);
                frappe.call({
                    method: 'erpnext_ebay.auto_slideshow.process_new_images',
                    args: {
                        item_code: item_code,
                        rte_id: frm.rte_id,
                        tag: frm.slideshow_dialog.tag
                    },
                    callback: function(r) {
                        if (r.message.success) {
                            frm.reload_doc();

                        } else {
                            frm.slideshow_dialog.hide();
                            frappe.msgprint(
                                "There has been a problem. " +
                                "Please manually set up slideshow and website image.");

                        }
                    }
                });
            }
        }, 100); // check every 100ms
    },

    // View slideshow
    view_slideshow(frm, doctype, docname) {
        const base_url = frappe.urllib.get_base_url();

        if (frm.doc.slideshow) {

            // Create the dialog
            const d = new frappe.ui.Dialog({
                'fields': [
                    {'fieldname': 'ht', 'fieldtype': 'HTML'}
                ],
            });
            d.$modal = d.$wrapper.find('.modal-dialog').parent();
            d.$modal.on('hidden.bs.modal', function (e) {
                // Ensure the modal is deleted on exit
                d.$modal.empty();
                d.$modal.remove();
            })

            // Increase the width from 600px to 1000px
            d.$wrapper.find('.modal-dialog').css('width', '1000px');

            d.set_title('Viewing slideshow ' + frm.doc.slideshow);
            d.show();

            frappe.call({
                // Call server-side view_slideshow
                // Get the list of images and format into a 2 column
                // Bootstrap layout with clickable links and filenames
                method: 'erpnext_ebay.custom_methods.website_slideshow_methods.view_slideshow_py',
                args: {
                    slideshow: frm.doc.slideshow
                },
                callback: function(r) {

                    const item_group_ebay = frm.doc.item_group_ebay || '(not defined)';
                    let html = "<p>Ebay item group: " + item_group_ebay + "</p>";
                    // Add the main table
                    html += '<div id="slideshow_table">';

                    if (r.message) {
                        html += '<div class="row">';

                        let in_row = 0;
                        for (let i = 0; i < r.message.length; i++) {
                            let img = r.message[i];
                            if (in_row === 2) {
                                html += '</div><div class="row">';
                                in_row = 0;
                            }
                            html +=
                                '<div class="col-lg-6" ' +
                                'style="padding: 5px">' +
                                '<div class="col-lg-12 border" ' +
                                'style="text-align: center; padding: 0px">' +
                                '<a href="'+img+'">' +
                                '<img src="'+img+'" /></a>' +
                                '<p>'+img+'</p>' +
                                '</div></div>';
                            in_row++;
                        }
                        html += '</div>';

                    } else {
                        frappe.msgprint("Fatal Error getting Slideshow details.");
                    }

                    html += '</div>';
                    d.fields_dict.ht.$wrapper.html(html);

                }
            });
        } else {
            frappe.msgprint("There is no Website Slideshow for this Item.");
        }

    },

    // Slideshow editing window
    slideshow_button(frm, doctype, docname) {
        console.log('slideshow_button');
        if (!frm.doc.slideshow) {
            frappe.msgprint("There is no Website Slideshow for this Item.");
        }
        const ebay_message = `eBay Item Group: ${frm.doc.item_group_ebay}`;
        erpnext_ebay.open_slideshow_window(frm, frm.doc.slideshow, ebay_message);
    }
});

