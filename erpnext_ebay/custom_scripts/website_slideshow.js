// Extend core Website Slideshow doctype

// Maximum number of eBay images
const MAX_EBAY_IMAGES = 12;


function colour_ebay_rows(frm) {
    // Colour in-use rows green (row number less than number_of_ebay_images
    if (!frm.doc.number_of_ebay_images) {
        return;
    }
    const rows = frm.get_field('slideshow_items').grid.grid_rows;
    rows.forEach(row_obj => {
        if (row_obj.doc.idx <= frm.doc.number_of_ebay_images) {
            row_obj.row.addClass('label-success');
        } else {
            row_obj.row.removeClass('label-success');
        }
    });
}


frappe.ui.form.on("Website Slideshow", {

    refresh(frm, doctype, docname) {
        colour_ebay_rows(frm);
    },

    number_of_ebay_images(frm, doctype, docname) {
        if (frm.doc.number_of_ebay_images && frm.doc.number_of_ebay_images > MAX_EBAY_IMAGES) {
            frm.set_value('number_of_ebay_images', MAX_EBAY_IMAGES);
        }
        colour_ebay_rows(frm);
    },


});


frappe.ui.form.on("Website Slideshow Item", {

    slideshow_items_move(frm, cdt, cdn) {
        // On a row change, idx is not immediately updated, so we need to
        // call colour_ebay_rows after idx is updated. Unfortunately, idx
        // changes do not generate events, so we have to use the setTimeout
        // below. The consequences of failure are low.
        setTimeout(() => {
            colour_ebay_rows(frm);
        }, 200);
    }

});
