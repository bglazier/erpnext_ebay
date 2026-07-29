// Extend core Item doctype


function get_online_selling_items(frm, item_code) {
    // Get Online Selling Items
    frappe.call({
        method: 'erpnext_ebay.custom_methods.item_methods.item_platform_async',
        args: {
            'item_code': item_code
        }
    }).then(({message: osi_list}) => {
        // Replace the Online Selling Items, but don't dirty the form
        frm._dirty = frm.dirty;
        frm.dirty = () => {};
        frm.clear_table('online_selling_items');
        (osi_list || []).forEach(osi_dict => {
            let child = frm.add_child('online_selling_items');
            Object.assign(child, osi_dict);
        });
        frm.doc.online_selling_items.forEach((child, index) => {
            child.idx = index + 1;
        });
        frm.refresh_field('online_selling_items');
        frm.dirty = frm._dirty;
        online_selling_show_grid(frm);
        // Delay the trigger so that updates have occurred first
        setTimeout(() => {
            frappe.ui.form.trigger('Item', 'online_selling_async_complete');
        }, 1);
    }).catch(() => {
        online_selling_show_grid(frm);
    });
}


function online_selling_show_loading(frm) {
    // Hide the Online Selling Items grid and show a loading message
    const field = frm.get_field('online_selling_items');
    frm._online_selling_fetching = true;
    field.$wrapper.hide();
    if (!frm._online_selling_loading) {
        frm._online_selling_loading = $(
            '<div class="text-muted">Loading...</div>'
        ).insertBefore(field.$wrapper);
    }
    frm._online_selling_loading.show();
}


function online_selling_show_grid(frm) {
    // Show the Online Selling Items grid and hide any loading message
    frm._online_selling_fetching = false;
    if (frm._online_selling_loading) {
        frm._online_selling_loading.hide();
    }
    frm.get_field('online_selling_items').$wrapper.show();
}


function setup_online_selling_section(frm) {
    // Load the Online Selling Items only when the Online Selling
    // Section is opened; closing and re-opening the section (which
    // also happens on every form refresh) reloads the entries
    const section = frm.fields_dict['online_selling_section'];
    if (!section || section._online_selling_wrapped) {
        return;
    }
    section._online_selling_wrapped = true;
    const section_collapse = section.collapse.bind(section);
    section.collapse = (hide) => {
        section_collapse(hide);
        if (section.is_collapsed()) {
            // Permit a reload when the section is next opened
            frm._online_selling_loaded = false;
        } else if (!frm._online_selling_loaded) {
            frm._online_selling_loaded = true;
            online_selling_show_loading(frm);
            frappe.ui.form.trigger('Item', 'get_online_selling');
        }
    };
}


frappe.ui.form.on('Item', {

    onload_post_render(frm, doctype, docname) {
        const field = frm.fields_dict['online_selling_items'];
        field.grid.sortable_status = false;
        field.grid.static_rows = true;
        field.grid.refresh();
        setup_online_selling_section(frm);
    },

    get_online_selling(frm, doctype, docname) {
        get_online_selling_items(frm, docname);
    },

});
