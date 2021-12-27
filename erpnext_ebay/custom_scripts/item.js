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

});

