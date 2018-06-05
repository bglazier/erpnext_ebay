// Extend core Item doctype 

/*
// Auto create slideshow
cur_frm.cscript.auto_create_slideshow = function(doc, cdt, cdn) {

    var item_code = doc.name;
    if (doc) {

        if (doc.__islocal) {
            frappe.msgprint(__("Please save the document before auto-creating slideshow."));
            return;
        }
    }

    frappe.call({
        method: 'erpnext_ebay.auto_slideshow.process_new_images',
        args: {
            item_code: item_code
        },
        callback: function(r) {
            if (r) {
                cur_frm.set_value("slideshow", "SS-" + item_code);

                // Cannot do this - as field is type "Attach"
                //cur_frm.set_value("website_image", "/files/" + item_code + "-0" + ".jpg");

        //cur_frm.set_df_property('website_image','options' "/files/" + item_code + "-0" + ".jpg");
                //cur_frm.refresh_field("website_image");


                frappe.msgprint("Hopefully slideshow created.");

            } else {
                frappe.msgprint("Problem. Please manually set up slideshow and website image.");

            }
        }
    })

}
*/


// Auto create slideshow
cur_frm.cscript.auto_create_slideshow = function(doc, cdt, cdn) {
    
    var item_code = doc.name;
    // Check document is saved
    if (doc) {
        if (doc.__islocal) {
            frappe.msgprint(__("Please save the document before auto-creating slideshow."));
            return;
        }
    }
    
    // Create the dialog
    var d = new frappe.ui.Dialog({
        'fields': [
            {'fieldname': 'ht', 'fieldtype': 'HTML'}
        ],
    });
    d.num_images = 0;
    d.$modal = d.$wrapper.find('.modal-dialog').parent();
    d.$modal.on('hidden.bs.modal', function (e) {
        d.$modal.empty();
        d.$modal.remove();
    })
    d.$modal.attr('id', 'ss_modal');
    d.$modal.attr('data-keyboard', false);
    d.$modal.attr('data-backdrop', "static");

    var html = '<p id="ss_maintext">Processing image <span id="ssimg_id">1</span> of ' +
               '<span id="ssimg_n">??</span>, please wait...</p>' +
               '<div id="slideshow_table">' +
               '</div>'
    d.fields_dict.ht.$wrapper.html(html);
    d.set_title('Processing images');
    d.no_cancel();
    d.show();

    cur_frm.slideshow_dialog = d;
    
    // If an rte_id for this form does not already exist, create one 
    if (!cur_frm.rte_id) {
        rand_id = Math.floor(Math.random() * 100000) + 1;
        cur_frm.rte_id = "rte_" + frappe.session.user + "_" + rand_id;
    }
    
    // Set a tag matching this item and dialog
    rand_id = Math.floor(Math.random() * 100000) + 1;
    cur_frm.slideshow_dialog.tag = item_code + "_" + rand_id;
    
    // Call the server - process the images
    frappe.call({
        method: 'erpnext_ebay.auto_slideshow.process_new_images',
        args: {
            item_code: item_code,
            rte_id: cur_frm.rte_id,
            tag: cur_frm.slideshow_dialog.tag
        },
        callback: function(r) {
            if (r.message == "success") {
                cur_frm.set_value("slideshow", "SS-" + item_code);

                // Cannot do this - as field is type "Attach"
                //cur_frm.set_value("website_image", "/files/" + item_code + "-0" + ".jpg");

        //cur_frm.set_df_property('website_image','options' "/files/" + item_code + "-0" + ".jpg");
                //cur_frm.refresh_field("website_image");

            } else {
                frappe.msgprint("There has been a problem. " +
                   "Please manually set up slideshow and website image.");
                cur_frm.slideshow_dialog.hide();

            }
        }
    })
}


// Update slideshow window
// This is called as auto_slideshow proceeds to update the modal dialog box
cur_frm.cscript.update_slideshow = function(tag, JSON_args) {
    // Check we have the right tag
    if (tag != cur_frm.slideshow_dialog.tag) return;
    
    var base_url = frappe.urllib.get_base_url()
    var args = JSON.parse(JSON_args);
    
    switch(args.command) {
        case "set_image_number":
            // This is done once the number of images is known, to create
            // the Bootstrap grid
            var n_images = parseInt(args.n_images);
            $("#ssimg_n").html(args.n_images);
            var n_rows = Math.ceil((n_images / 3.0)-0.1);
            table = $("#slideshow_table");
            var img_id = 1;
            for (i = 0; i < n_rows; i++) {
                var new_row = table.append('<div class="row"></div>');
                for (j = 0; j < 3; j++) {
                    var new_col = $(
                        '<div class="col-sm-4 border" ' +
                        'style="min-height: 100px; text-align: center;"></div>'
                    );
                    if (img_id == 1) {
                        loader_gif = base_url + 
                            "/assets/erpnext_ebay/img/ajax-loader2.gif";
                    } else {
                        loader_gif = base_url +
                            "/assets/erpnext_ebay/img/ajax-loader.gif";
                    }
                    var img = $('<img src="' + loader_gif + '"></img>');
                    img.attr({'id': 'ss_img_' + img_id});
                    new_col.append(img);
                    new_col.appendTo(new_row);
                    img_id++;
                    if (img_id > n_images) break;
                }
            }
            break;

        case "new_image":
            // This is done as each new image arrives
            var img_id = parseInt(args.img_id);
            var n_images = parseInt(args.n_images);
            $("#ssimg_id").html(args.img_id);
            var file_url = base_url + '/' + args.file_url
            $("#ss_img_" + img_id).attr('src', file_url);
            var loader_gif = base_url +
                            "/assets/erpnext_ebay/img/ajax-loader2.gif";
            if (img_id < n_images) {
                $("#ss_img_"+(img_id+1)).attr('src', loader_gif);
            }
            break;

        case "done":
            // The slideshow has been created and the dialog box can
            // be unlocked
            $("#ss_maintext").html('Slideshow created');
            var d = cur_frm.slideshow_dialog
            d.get_close_btn().toggle(true);
            d.$modal.data('bs.modal').options.backdrop = 'true';
            d.$modal.data('bs.modal').options.keyboard = 'true';
            break;
    }
}


// View slideshow
cur_frm.cscript.view_slideshow = function(frm, cdt, cdn) {
  if (frm.slideshow)
  {
    frappe.call({
        method: 'erpnext_ebay.auto_slideshow.view_slideshow_py',
        args: {
            slideshow: frm.slideshow
        },
        callback: function(r) {
            if (r) {
                frappe.msgprint(r, 'View Slideshow');
            } else {
                frappe.msgprint("Fatal Error getting Slideshow details.");
            }
        }
    });
  }
  else
  {
      frappe.msgprint("There is no Website Slideshow for this Item");
  }

  }


// Revise items
cur_frm.cscript.validate = function (frm, cdt, cdn) 
{

	//frappe.call({
        //method: 'erpnext_ebay.revise_items.revise_generic_items',
       // args: {item_code: frm.item_code},
        //callback: function(r) {}
    //})

}
