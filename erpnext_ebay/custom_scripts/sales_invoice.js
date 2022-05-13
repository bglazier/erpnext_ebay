// Extend core Sales Invoice doctype functionality

{  // Start whole-file block

async function monkey_patch_calculate_taxes_and_totals(update_paid_amount) {
    // While calculating taxes_and_totals, fudge the party account currency
    // to match the SINV currency
    if (this.frm.doctype == 'Sales Invoice' && this.frm.doc.pos_profile && this.frm.doc.pos_profile.startsWith('eBay')) {
        const old_party_account_currency = this.frm.doc.party_account_currency;
        this.frm.doc.party_account_currency = this.frm.doc.currency;
        await this._old_calculate_taxes_and_totals(update_paid_amount);
        this.frm.doc.party_account_currency = old_party_account_currency;
        this.frm.refresh_fields();
    } else {
        await this._old_calculate_taxes_and_totals(update_paid_amount);
    }
}


function monkey_patch_set_default_payment(total_amount_to_pay, update_paid_amount) {
    // This version, for eBay SINVs, accepts amount not base_amount
    if (this.frm.doctype == 'Sales Invoice' && this.frm.doc.pos_profile && this.frm.doc.pos_profile.startsWith('eBay')) {
        var me = this;
        var payment_status = true;
        if(this.frm.doc.is_pos && (update_paid_amount===undefined || update_paid_amount)) {
            $.each(this.frm.doc['payments'] || [], function(index, data) {
                if(data.default && payment_status && total_amount_to_pay > 0) {
                    let amount = flt(total_amount_to_pay, precision("amount", data));
                    frappe.model.set_value(data.doctype, data.name, "amount", amount);
                    let base_amount = flt(total_amount_to_pay * me.frm.doc.conversion_rate, precision("base_amount", data));
                    frappe.model.set_value(data.doctype, data.name, "base_amount", base_amount);
                    payment_status = false;
                } else if(me.frm.doc.paid_amount) {
                    frappe.model.set_value(data.doctype, data.name, "amount", 0.0);
                }
            });
        }
    } else {
        this._old_set_default_payment(total_amount_to_pay, update_paid_amount);
    }
}


function monkey_patch_calculate_item_values() {
    // Calculate as normal to begin
    this._old_calculate_item_values();
    if (!(this.frm.doctype == 'Sales Invoice' && this.frm.doc.pos_profile && this.frm.doc.pos_profile.startsWith('eBay'))) {
        // Only override for eBay SINVs
        return;
    }
    let me = this;
    if (this.discount_amount_applied) {
        // No calculation in this case
        return;
    }
    let amount_total = 0;
    let base_item_amount_total = 0;
    this.frm.doc.items.forEach((item, i) => {
        amount_total += item.amount;
        base_item_amount_total += item.base_amount;
    });
    if (!amount_total) {
        // Zero-value SINV
        return;
    }
    // Adjust base_rate and base_amount so totals add up correctly
    const base_amount_total = flt(
        me.frm.doc.conversion_rate * amount_total,
        precision("base_total", me.frm.doc)
    );
    if (base_amount_total == base_item_amount_total) {
        // Rounding works
        return
    }
    // Otherwise, we need to fudge things
    const base_amount_obj = me.frm.doc.items.reduce((acc, item, i) => {
        acc[i] = item.amount * me.frm.doc.conversion_rate;
        return acc;
    }, {});
    const base_amounts = erpnext_ebay.divide_rounded(
        base_amount_obj, base_amount_total,
        precision("base_total", me.frm.doc)
    );
    Object.entries(base_amounts).forEach(([i, v]) => {
        const item = me.frm.doc.items[i];
        item.base_amount = v;
        if ((!item.qty) && me.frm.doc.is_return) {
            item.base_rate = flt(-item.base_amount, precision("base_rate", item));
        } else if ((!item.qty) && me.frm.doc.is_debit_note) {
            item.base_rate = flt(item.base_amount, precision("base_rate", item));
        } else {
            item.base_rate = flt(item.base_amount / item.qty, precision("base_rate", item));
        }
        item.base_net_rate = item.base_rate
        item.base_net_amount = item.base_amount
    });
}


frappe.ui.form.on("Sales Invoice", {
    onload(frm) {
        // Monkey-patch calculate_taxes_and_totals and calculate_item_values
        // functions
        if (!frm.cscript._old_calculate_taxes_and_totals) {
            frm.cscript._old_calculate_taxes_and_totals = frm.cscript.calculate_taxes_and_totals;
        }
        frm.cscript.calculate_taxes_and_totals = monkey_patch_calculate_taxes_and_totals;
        if (!frm.cscript._old_set_default_payment) {
            frm.cscript._old_set_default_payment = frm.cscript.set_default_payment;
        }
        frm.cscript.set_default_payment = monkey_patch_set_default_payment;
        if (!frm.cscript._old_calculate_item_values) {
            frm.cscript._old_calculate_item_values = frm.cscript.calculate_item_values;
        }
        frm.cscript.calculate_item_values = monkey_patch_calculate_item_values;
    },

    before_save(frm) {
        if (frm.doc.disable_rounded_total) {
            frm.set_value('disable_rounded_total', false);
        }
        frm.doc.rounded_total = 0.0;
        frm.doc.base_rounded_total = 0.0;
    },

    before_submit(frm) {
        if (frm.doc.disable_rounded_total) {
            frm.set_value('disable_rounded_total', false);
        }
        frm.doc.rounded_total = 0.0;
        frm.doc.base_rounded_total = 0.0;
    }
});

}  // End whole-file block
