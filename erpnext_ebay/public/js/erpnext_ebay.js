// Initialize slideshow and main erpnext_ebay object.

var erpnext_ebay = {
    cur_slideshow: null,

    realtime_event(rte_id, tag, event, args) {
        // Impromptu event handler for frappe.publish_realtime using eval
        // Uses an 'rte_id' variable, stored in the current form, to check
        // the event goes to the right listeners
        // Triggers events as required
        if (cur_frm.rte_id == rte_id) {
            switch(event) {
                case "update_slideshow":
                    this.update_slideshow(tag, args);
                    break;
            }
        }
    },

    // Update slideshow window
    // This is called as auto_slideshow proceeds to update the modal dialog box
    update_slideshow(tag, JSON_args) {
        // Check we have the right tag
        if (tag != cur_frm.slideshow_dialog.tag) {
            return;
        }

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
    },

    open_slideshow_window(frm, slideshow, extra_message) {
        // Opens a modal window for editing the Website Slideshow 'slideshow'

        if (this.cur_slideshow) {
            this.cur_slideshow.close();
        }

        this.cur_slideshow = new UGSSlideshow(slideshow, extra_message);
    }

};


// *****************************************************************************
// Slideshow window

class UGSSlideshow {
    // The main slideshow window
    static image_widths = [200, 300, 400, 500, 800, 1200];
    static aspect_ratio = 0.75;
    static old_direction_arrows = {
        0: '',
        1: 'fa-long-arrow-left',
        2: 'fa-long-arrow-down',
        3: 'fa-long-arrow-right'
    }
    static all_direction_arrows = (
        'fa-long-arrow-left fa-long-arrow-down fa-long-arrow-right'
    );
    constructor(slideshow, extra_message) {
        // Construct and show slideshow dialog
        this.slideshow = slideshow;
        this.extra_message = extra_message;
        this.image_width = 300;

        this.make();

        // Initialize properties
        this.slideshow = slideshow;
        this.ss_doc = null;
        // Load data
        this.load();
    }
    make() {
        // Make basics of slideshow dialog
        this.$wrapper = $(
        `<div class="modal fade ugs-slideshow-modal" tabindex="-1">
            <div class="modal-dialog ugs-slideshow-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <div class="flex justify-between">
                            <div class="fill-width flex">
                                <span class="indicator blue"></span>
                                <h4 class="modal-title" style="font-weight: bold;">Website Slideshow ${this.slideshow}</h4>
                                <div class="input-group input-group-sm ugs-n-ebay-images hide">
                                    <span class="input-group-addon">Num. of eBay images</span>
                                    <span class="ugs-n-ebay-images-span" data-i="1">1</span>
                                    <span class="ugs-n-ebay-images-span" data-i="2">2</span>
                                    <span class="ugs-n-ebay-images-span" data-i="3">3</span>
                                    <span class="ugs-n-ebay-images-span" data-i="4">4</span>
                                    <span class="ugs-n-ebay-images-span" data-i="5">5</span>
                                    <span class="ugs-n-ebay-images-span" data-i="6">6</span>
                                    <span class="ugs-n-ebay-images-span" data-i="7">7</span>
                                    <span class="ugs-n-ebay-images-span" data-i="8">8</span>
                                    <span class="ugs-n-ebay-images-span" data-i="9">9</span>
                                    <span class="ugs-n-ebay-images-span" data-i="10">10</span>
                                    <span class="ugs-n-ebay-images-span" data-i="11">11</span>
                                    <span class="ugs-n-ebay-images-span" data-i="12">12</span>
                                    <div class="input-group-btn">
                                        <button class="btn btn-default btn-primary btn-modal-top-pick" type="button">Pick to Top</button>
                                    </div>
                                </div>
                            </div>
                            <div>
                                <div class="text-right buttons">
                                    <button type="button" class="btn btn-default btn-sm btn-modal-reload">Reload</button>
                                    <button type="button" class="btn btn-primary btn-sm btn-modal-save" disabled>Save</button>
                                    <button type="button" class="btn btn-danger btn-sm btn-modal-close">
                                        <i class="octicon octicon-x" style="padding: 1px 0px;"></i>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-body ui-front">
                        <div class="flex">
                            <div class="h5 ugs-slideshow-extra-message hide"></div>
                            <div class="panel panel-default">
                                <div class="flex align-center panel-body">
                                    <i class="octicon octicon-search" style="color: #d1d8dd; padding-right: 5px"></i>
                                    <input type="range" min="0" max="5" value="1" class="ugs-slideshow-zoom-slider">
                                </div>
                            </div>
                        </div>
                        <div class="ugs-slideshow-entries ugs-slideshow-normal"></div>
                    </div>
                </div>
            </div>
        </div>`);

        if (this.extra_message) {
            this.$wrapper.find('.ugs-slideshow-extra-message')
                .removeClass('hide')
                .text(this.extra_message);
        }

        this.$wrapper.modal({
            backdrop: 'static',
            keyboard: false,
            show: true
        });

        // References
        this.$body = this.$wrapper.find(".modal-body");
        this.$header = this.$wrapper.find(".modal-header");
        this.$buttons = this.$header.find('.buttons');
        this.$entries = this.$body.find('.ugs-slideshow-entries');

        this.$n_ebay_spans = this.$header.find('.ugs-n-ebay-images-span');
        this.$top_pick_button = this.$header.find('.btn-modal-top-pick');

        this.$reload_button = this.$buttons.find('.btn-modal-reload');
        this.$save_button = this.$buttons.find('.btn-modal-save');
        this.$close_button = this.$buttons.find('.btn-modal-close');

        this.$zoom_slider = this.$body.find('.ugs-slideshow-zoom-slider');

        // Events
        const me = this;
        this.$reload_button.click(function() {
            me.reload();
        });
        this.$save_button.click(function() {
            me.save();
        });
        this.$close_button.click(function() {
            me.close();
        });
        this.$n_ebay_spans.click(function () {
            me.set_number_of_ebay_images(this);
        });
        this.$top_pick_button.click(function() {
            me.top_pick();
        });
        this.$zoom_slider.change(function () {
            me.slider_zoom(this);
        });
        this.$body.find('.ugs-slideshow-entries')
            .on('click', 'img', function() {
                const $entry = $(this).parent().parent();
                if ($entry.hasClass('ugs-slideshow-top-pick')) {
                    me.top_pick_img_click(this);
                }
            }
        );
        this.$entries.on('click', '.fa-trash', function() {
            me.delete_entry(this);
        });
        this.$entries.on('click', '.fa-rotate-left', function() {
            me.rotate_entry(this, false);
        });
        this.$entries.on('click', '.fa-rotate-right', function() {
            me.rotate_entry(this, true);
        });

        // Drag events
        let drag_target, drag_counter;

        this.$entries.on('dragstart', '.ugs-slideshow-entry', function(e) {
            // Drag begun
            drag_target = null;
            drag_counter = 0;
            me.$entries.addClass('drag-active');
            const dragged = $(this);
            dragged.addClass('entry-drag');
            e.originalEvent.dataTransfer.dropEffect = "move";
            e.originalEvent.dataTransfer.setData(
                'text/plain', dragged.index().toString()
            );
        });
        this.$entries.on('dragover', '.ugs-slideshow-entry', function(e) {
            // Allow entries to become drag targets
            e.preventDefault();
            return false;
        });
        this.$entries.on('dragenter', '.ugs-slideshow-entry', function(e) {
            // Entering entry or child of entry
            if (drag_target == this) {
                drag_counter += 1;
            } else {
                $(drag_target).removeClass('drag-over');
                drag_target = this;
                drag_counter = 1;
            }
            if (drag_counter == 1) {
                $(this).addClass('drag-over');
            }
            return false;
        });
        this.$entries.on('dragleave', '.ugs-slideshow-entry', function(e) {
            // Leaving entry or child of entry
            if (drag_target == this) {
                drag_counter -= 1;
            } else {
                drag_target = null;
                drag_counter = 0;
            }
            if (drag_counter <= 0) {
                $(this).removeClass('drag-over');
            }
            return false;
        });
        this.$entries.on('dragend', '.ugs-slideshow-entry', function(e) {
            // Drag ended
            drag_target = null;
            drag_counter = 0;
            me.$entries.removeClass('drag-active');
            me.$entries.find('.drag-over').removeClass('drag-over');
            $(this).removeClass('entry-drag');
            return false;
        });
        this.$entries.on('drop', '.ugs-slideshow-entry', function(e) {
            // Entry dropped on another entry
            drag_target = null;
            drag_counter = 0;
            me.$entries.removeClass('drag-active');
            const to_id = $(this).index();
            const from_id = parseInt(
                e.originalEvent.dataTransfer.getData('text/plain'), 10
            );
            if (from_id == to_id) {
                // Drop on self; nothing to do.
                return false;
            }
            setTimeout(() => {
                me.move_entry(from_id, to_id);
            });
            return false;
        });
    }
    set_indicator(indicator) {
        this.$header.find('.indicator')
            .removeClass().addClass('indicator ' + indicator);
    }
    set_number_of_ebay_images(el) {
        // New number of eBay images selected
        const $span = $(el);
        if ($span.hasClass('active') || $span.hasClass('disabled')) {
            return;
        }
        this.ss_doc.number_of_ebay_images = $span.data('i');
        this.dirty();
        this.refresh_n_ebay_images();
    }
    top_pick() {
        const $button = this.$top_pick_button;
        if ($button.text() === 'Pick to Top') {
            // Switch to 'Pick to Top' mode
            $button.text('Done Picking')
                .removeClass('btn-primary').addClass('btn-success');
            this.$save_button.prop('disabled', true);
            this.$reload_button.prop('disabled', true);
            this.$zoom_slider.prop('disabled', true);
            this.$entries.removeClass('ugs-slideshow-normal')
                .addClass('ugs-slideshow-top-pick');
            this.$entries.children().attr('draggable', false);
            this.$n_ebay_spans.addClass('disabled');
        } else {
            // Switch back to normal mode
            $button.text('Pick to Top')
                .removeClass('btn-success').addClass('btn-primary');
            this.$save_button.prop('disabled', false);
            this.$reload_button.prop('disabled', false);
            this.$zoom_slider.prop('disabled', false);
            this.$entries.removeClass('ugs-slideshow-top-pick')
                .addClass('ugs-slideshow-normal');
            this.$entries.children().attr('draggable', true);
            this.$n_ebay_spans.removeClass('disabled selected-pick')
            // Get selected top picks
            const $all_entries = this.$entries.children();
            const $top_picks = this.$entries.children('.selected-pick');
            const n_picks = $top_picks.length;
            // Only make changes if any images selected
            if (n_picks > 0) {
                // Get picked and unpicked slideshow item documents
                const picked = [];
                const unpicked = [];
                this.ss_doc.slideshow_items.map((ssi, i) => {
                    if ($all_entries.eq(i).hasClass('selected-pick')) {
                        picked.push(ssi);
                    } else {
                        unpicked.push(ssi);
                    }
                });
                // Update document
                this.dirty();
                this.ss_doc.number_of_ebay_images = n_picks;
                this.ss_doc.slideshow_items = picked.concat(unpicked);
                this.reorder_items();
            }
            // Remove selected top pick class
            $top_picks.removeClass('selected-pick');
            // Refresh
            this.refresh();
        }
    }
    top_pick_img_click(el) {
        const $entry = $(el).parent();
        let n_selected = this.$entries.children('.selected-pick').length
        if ($entry.hasClass('selected-pick')) {
            // Remove selected pick
            $entry.removeClass('selected-pick');
            n_selected -= 1;
        } else if (n_selected >= 12) {
            // Would add, except there are already 12 selected
            return;
        } else {
            // Add new selected pick
            $entry.addClass('selected_pick').addClass('selected-pick');
            n_selected += 1;
        }
        this.$n_ebay_spans.removeClass('selected-pick');
        this.$n_ebay_spans.filter(`[data-i=${n_selected}]`)
            .addClass('selected-pick');
    }
    slider_zoom(el) {
        // Slider zoom has changed
        const width = UGSSlideshow.image_widths[$(el).val()]
        if (width === this.image_width) {
            return;
        }
        this.image_width = width;
        this.refresh();
    }
    move_entry(from_id, to_id) {
        // Move an entry from position from_id to position to_id
        const ss_items = this.ss_doc.slideshow_items;
        ss_items.splice(to_id, 0, ss_items.splice(from_id, 1)[0])
        this.reorder_items();
        // Refresh
        this.dirty();
        this.refresh();
    }
    delete_entry(el) {
        // Prompt to delete this entry
        const me = this;
        frappe.confirm(
            'Delete this image?',
            () => {
                me._delete_entry(el);
            }
        );
    }
    _delete_entry(el) {
        // Actually delete this entry
        const $entry = $(el).parent().parent();
        if ($entry.hasClass('ugs-slideshow-entry-top')) {
            // Reduce number of eBay images by one (to minimum one)
            this.ss_doc.number_of_ebay_images = Math.max(
                this.ss_doc.number_of_ebay_images - 1, 1
            );
        }
        // Remove ss_item and reindex
        this.ss_doc.slideshow_items.splice($entry.index(), 1)
        this.reorder_items()
        // Refresh
        this.dirty();
        this.refresh();
    }
    rotate_entry(el, clockwise) {
        // Rotate this entry by 90 degrees
        const $entry = $(el).parent().parent();
        const ssi = this.ss_doc.slideshow_items[$entry.index()];
        ssi.__direction = (ssi.__direction || 0) + (clockwise ? -1 : 1)
        if (ssi.__direction < 0) {
            ssi.__direction = ssi.__direction + 4;
        } else if (ssi.__direction > 3) {
            ssi.__direction = ssi.__direction - 4;
        }
        this.refresh_entry_transform($entry, ssi.__direction);
        this.dirty();
    }
    clean() {
        this.ss_doc.__unsaved - false;
        this.$save_button.prop('disabled', false);
        this.set_indicator('blue');
    }
    dirty() {
        if (this.ss_doc.__unsaved) {
            return;
        }
        this.ss_doc.__unsaved = true;
        this.$save_button.prop('disabled', false);
        this.set_indicator('orange');
    }
    load() {
        // Load data to this.ss_doc and locals
        frappe.dom.freeze('Loading Website Slideshow...');
        frappe.db.get_doc('Website Slideshow', this.slideshow)
        .then((ss_doc) => {
            this.ss_doc = ss_doc;
            this.clean();
            this.refresh();
            frappe.dom.unfreeze();
        });
    }
    close() {
        // Close and empty dialog
        if (this.ss_doc.__unsaved) {
            // There are changes
            frappe.confirm(
                'Changes will be lost. Continue without saving?',
                () => { this._close(); }
            );
        } else {
            // No changes
            this._close();
        }
    }
    _close() {
        this.$wrapper.modal('hide');
        this.$wrapper.empty().remove();
        erpnext_ebay.cur_slideshow = null;
    }
    reload() {
        // Reload button - reload document, discarding changes
        if (this.ss_doc.__unsaved) {
            // There are changes
            frappe.confirm(
                'Changes will be lost. Continue without saving?',
                () => {
                    this.load();
                }
            );
        } else {
            // No changes
            this.load();
        }
    }
    refresh() {
        // Draw the slideshow
        // Create slideshow images
        this.refresh_entries();
        // Set up number_of_ebay_images
        this.refresh_n_ebay_images();
    }
    refresh_entries() {
        // Redraw slideshow images
        // Clear existing content
        this.$entries.empty();
        // Check for no document
        if (!this.ss_doc) {
            return;
        }
        // Check for empty slideshow
        if (!this.ss_doc.slideshow_items.length) {
            this.set_indicator('orange');
            this.$entries.text('Empty slideshow');
            return;
        }
        // Create images
        const width = this.image_width;
        const height = UGSSlideshow.aspect_ratio * width;
        this.ss_doc.slideshow_items.forEach((ssi) => {
            const $entry = $(`
                <div class="ugs-slideshow-entry" draggable="true">
                    <div class="ugs-slideshow-entry-top-pick-shadow-box"></div>
                    <img src="${ssi.image}" draggable="false"
                        style="width: ${width}px; height: ${height}px">
                    <div class="ugs-slideshow-entry-drag-target"></div>
                    <div class="fa ugs-slideshow-entry-arrow-box"></div>
                    <div class="ugs-slideshow-entry-icon-box">
                        <i class="fa fa-trash"></i>
                        <i class="fa fa-rotate-left"></i>
                        <i class="fa fa-rotate-right"></i>
                    </div>
                </div>`);
            this.refresh_entry_transform($entry, (ssi.__direction || 0));
            this.$entries.append($entry);
        });
    }
    refresh_n_ebay_images() {
        // Refresh number-of-eBay-images indicator on images
        const n_ebay = this.ss_doc.number_of_ebay_images;
        this.$n_ebay_spans.removeClass('active');
        this.$n_ebay_spans.filter(`[data-i="${n_ebay}"]`)
            .addClass('active');
        this.$header.find('.ugs-n-ebay-images').removeClass('hide');
        this.$entries.children().each(function(i) {
            if (i < n_ebay) {
                $(this).addClass('ugs-slideshow-entry-top');
            } else {
                $(this).removeClass('ugs-slideshow-entry-top');
            }
        });
    }
    refresh_entry_transform($entry, direction) {
        // Set up the transform for a single entry
        const direction_transform = {
            0: '',  // Upright
            1: 'rotate(270deg)',  // 90 degrees clockwise
            2: 'rotate(180deg)',  // 180 degrees clockwies
            3: 'rotate(90deg)'  // 270 degrees clockwise
        }
        const $img = $entry.children('img');
        let transform = direction_transform[direction];
        if (direction == 1 || direction == 3) {
            // Find the right scaling
            const nat_aspect = ($img.get(0).naturalHeight || 100) / ($img.get(0).naturalWidth || 100);
            if (nat_aspect == 1) {
                // Square box
                // No scaling needed
            } else if (nat_aspect >= 1) {
                // Tall thin box - no scaling until 1 / box aspect ratio
                const scale_factor = Math.min(
                    1.0 / UGSSlideshow.aspect_ratio,
                    nat_aspect
                )
                transform = transform + ` scale(${scale_factor})`;
            } else if (nat_aspect > UGSSlideshow.aspect_ratio) {
                // Fat column - shrink on rotate
                transform = transform + ` scale(${nat_aspect})`;
            } else {
                // Wide strip - shrink on rotate
                transform = transform + ` scale(${UGSSlideshow.aspect_ratio})`;
            }
        }
        $img.css('transform', transform);
        $entry
            .removeClass('direction-0 direction-1 direction-2 direction-3')
            .addClass(`direction-${direction}`);
        $entry.children('.ugs-slideshow-entry-arrow-box')
            .removeClass(UGSSlideshow.all_direction_arrows)
            .addClass(UGSSlideshow.old_direction_arrows[direction]);
    }
    reorder_items() {
        // Update idx of slideshow items
        this.ss_doc.slideshow_items.forEach((ssi, i) => {
            ssi.idx = i + 1;
        });
    }
    save() {
        // Save document to server, and update to new document
        frappe.call({
            method: 'erpnext_ebay.custom_methods.website_slideshow_methods.save_with_rotations',
            args: {doc: this.ss_doc},
            freeze: true,
            freeze_message: 'Saving...',
            error_handlers: {
                'TimestampMismatchError': (r) => {
                    // If the Website Slideshow doc is out of date
                    const messages = JSON.parse(r._server_messages)
                    const msg_obj = JSON.parse(messages[0])
                    msg_obj.message = message.message.replace('Document', 'Website Slideshow');
                    frappe.msgprint(msg_obj);
                }
            }
        }).then(({message}) => {
            // On success
            this.ss_doc = message;
            frappe.model.sync(message);
            this.$save_button.prop('disabled', true);
            this.clean();
            this.refresh();
        });
    }
}
