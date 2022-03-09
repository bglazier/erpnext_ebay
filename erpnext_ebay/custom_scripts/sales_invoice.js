// Extend core Sales Invoice doctype functionality

{  // Start whole-file block

function monkey_patch_calculate_taxes_and_totals(update_paid_amount) {
    // While calculating taxes and totals, fudge the party account currency
    // to match the SINV currency
    if (this.frm.doc.pos_profile && this.frm.doc.pos_profile.startsWith('eBay')) {
        const old_party_account_currency = this.frm.doc.party_account_currency;
        this.frm.doc.party_account_currency = this.frm.doc.currency;
        this._old_calculate_taxes_and_totals(update_paid_amount);
        this.frm.doc.party_account_currency = old_party_account_currency;
        this.frm.refresh_fields();
    } else {
        this._old_calculate_taxes_and_totals(update_paid_amount);
    }
}


frappe.ui.form.on("Sales Invoice", {
    onload(frm) {
        // Monkey-patch calculate_taxes_and_totals
        if (!frm.cscript._old_calculate_taxes_and_totals) {
            frm.cscript._old_calculate_taxes_and_totals = frm.cscript.calculate_taxes_and_totals;
        }
        frm.cscript.calculate_taxes_and_totals = monkey_patch_calculate_taxes_and_totals;
    }
});

}  // End whole-file block
