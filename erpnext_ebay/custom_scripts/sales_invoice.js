// Extend core Sales Invoice doctype functionality

{  // Start whole-file block

async function monkey_patch_calculate_taxes_and_totals(update_paid_amount) {
    // While calculating taxes and totals, fudge the party account currency
    // to match the SINV currency
    if (this.frm.doc.pos_profile && this.frm.doc.pos_profile.startsWith('eBay')) {
        const old_party_account_currency = this.frm.doc.party_account_currency;
        this.frm.doc.party_account_currency = this.frm.doc.currency;
        await this._old_calculate_taxes_and_totals(update_paid_amount);
        this.frm.doc.party_account_currency = old_party_account_currency;
        this.frm.refresh_fields();
    } else {
        await this._old_calculate_taxes_and_totals(update_paid_amount);
    }
}


frappe.ui.form.on("Sales Invoice", {
    onload(frm) {
        // Monkey-patch calculate_taxes_and_totals
        if (!frm.cscript._old_calculate_taxes_and_totals) {
            frm.cscript._old_calculate_taxes_and_totals = frm.cscript.calculate_taxes_and_totals;
        }
        frm.cscript.calculate_taxes_and_totals = monkey_patch_calculate_taxes_and_totals;
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
