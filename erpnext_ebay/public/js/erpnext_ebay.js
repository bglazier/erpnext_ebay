erpnext_ebay_realtime_event = function(rte_id, tag, event, args) {
    // Impromptu event handler for frappe.publish_realtime using eval
    // Uses an 'rte_id' variable, stored in the current form, to check
    // the event goes to the right listeners
    // Triggers events as required
    if (cur_frm.rte_id == rte_id) {
        switch(event) {
            case "update_slideshow":
                update_slideshow(tag, args);
                break;
        }
    }
}

// Update slideshow window
// This is called as auto_slideshow proceeds to update the modal dialog box
function update_slideshow(tag, JSON_args) {
    // Check we have the right tag
    if (tag != cur_frm.slideshow_dialog.tag) return;

    const base_url = frappe.urllib.get_base_url();
    const args = JSON.parse(JSON_args);

    switch(args.command) {
        case "set_image_number": {
            // This is done once the number of images is known, to create
            // the Bootstrap grid
            const n_images = parseInt(args.n_images, 10);
            $("#ssimg_n").html(args.n_images);
            const n_rows = Math.ceil((n_images / 3.0)-0.1);
            $table = $("#slideshow_table");
            let img_id = 1;
            for (let i = 0; i < n_rows; i++) {
                // Loop over the rows
                let new_row = $table.append('<div class="row"></div>');
                for (let j = 0; j < 3; j++) {
                    // Loop over the 3 elements in a row
                    let new_col = $(
                        '<div class="col-lg-4 border" ' +
                        'style="min-height: 100px; text-align: center;"></div>'
                    );
                    // Add spinning icons for unprocessed images
                    // Different icon for currently processed image
                    if (img_id === 1) {
                        loader_gif = base_url + 
                            "/assets/erpnext_ebay/img/ajax-loader2.gif";
                    } else {
                        loader_gif = base_url +
                            "/assets/erpnext_ebay/img/ajax-loader.gif";
                    }
                    let img = $('<img src="' + loader_gif + '" />');
                    img.attr({'id': 'ss_img_' + img_id});
                    new_col.append(img);
                    new_col.appendTo(new_row);
                    img_id++;
                    if (img_id > n_images) break;
                }
            }
            break;
        }
        case "new_image": {
            // This is done as each new image arrives
            // Add the new photo and upload the animated GIF for the next image
            const img_id = parseInt(args.img_id, 10);
            const n_images = parseInt(args.n_images, 10);
            $("#ssimg_id").html(args.img_id);
            const file_url = base_url + '/' + args.file_url
            $("#ss_img_" + img_id).attr('src', file_url);
            const loader_gif = base_url +
                "/assets/erpnext_ebay/img/ajax-loader2.gif";
            if (img_id < n_images) {
                $("#ss_img_"+(img_id+1)).attr('src', loader_gif);
            }
            break;
        }
        case "done": {
            // The slideshow has been created and the dialog box can
            // be unlocked
            $("#ss_maintext").html('Slideshow created');
            const d = cur_frm.slideshow_dialog
            d.get_close_btn().toggle(true);
            d.$modal.data('bs.modal').options.backdrop = 'true';
            d.$modal.data('bs.modal').options.keyboard = 'true';
            break;
        }
    }
};
