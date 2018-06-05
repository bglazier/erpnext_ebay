erpnext_ebay_realtime_event = function(rte_id, tag, event, args) {
    // Impromptu event handler for frappe.publish_realtime using eval
    // Uses an 'rte_id' variable, stored in the current form, to check
    // the event goes to the right listeners
    // Triggers events as required
    if (cur_frm.rte_id == rte_id) {
        switch(event) {
            case "update_slideshow":
                cur_frm.cscript.update_slideshow(tag, args);
                break;
        }
    }
}
