// Copyright (c) 2021, Ben Glazier and contributors
// For license information, please see license.txt

const ebay_token_module = 'erpnext_ebay.ebay_tokens';

function start_consent(frm, sandbox, app_id, ru_name, scopes) {
    // Start eBay user token consent flow
    sandbox = sandbox ? 1 : 0
    if (frm.is_dirty()) {
        frappe.throw('Save form first!');
    }
    const name_string = sandbox ? 'sandbox' : 'production';
    if (!app_id) {
        frappe.throw(`No ${name_string} App ID specified!`);
    }
    if (!ru_name) {
        frappe.throw(`No ${name_string} redirect URL name!`);
    }
    if (!sandbox && !scopes) {
        frappe.throw(`No ${name_string} scopes specified!`);
    }
    const auth_url = (
        sandbox ? 'https://auth.sandbox.ebay.com/oauth2/authorize'
        : 'https://auth.ebay.com/oauth2/authorize'
    );
    frappe.call({
        method: ebay_token_module + '.generate_state_token',
        args: {
            sandbox: sandbox
        }
    }).then(({message: state_token}) => {
        if (!state_token) {
            return
        }
        const state = {
            hostname: location.origin,
            sandbox: sandbox,
            state_token: state_token
        };
        state.hostname = location.origin;
        const params = new URLSearchParams();
        params.append('client_id', app_id);
        params.append('response_type', 'code');
        params.append('redirect_uri', ru_name);
        if (scopes) {
            params.append('scope', scopes);
        }
        params.append('state', JSON.stringify(state));
        const url = `${auth_url}?${params.toString()}`;
        window.open(url, 'ugs_ebay_auth');
    });
}

frappe.ui.form.on('eBay API Settings', {
    refresh(frm) {
        $('[data-fieldname="production_key_jwe"] .control-value')
            .css({'font-size': 'xx-small', 'word-break': 'break-all',
                  'font-family': 'monospace'});
        $('[data-fieldname="sandbox_key_jwe"] .control-value')
            .css({'font-size': 'xx-small', 'word-break': 'break-all',
                  'font-family': 'monospace'});
    },
    authorize_sandbox_button(frm) {
        // Start consent flow for sandbox
        const app_id = frm.doc.sandbox_app_id;
        const ru_name = frm.doc.sandbox_ru_name;
        const scopes = frm.doc.sandbox_scopes;
        start_consent(frm, 1, app_id, ru_name, scopes);
    },
    authorize_production_button(frm) {
        // Start consent flow for production
        const app_id = frm.doc.production_app_id;
        const ru_name = frm.doc.production_ru_name;
        const scopes = frm.doc.production_scopes;
        start_consent(frm, 0, app_id, ru_name, scopes);
    },
    get_sandbox_key_button(frm) {
        // Get a public/private key pair from the sandbox
        if (frm.is_dirty()) {
            frappe.throw('Save form first!');
        }
        frappe.call({
            method: ebay_token_module + '.create_new_key_pair',
            args: {sandbox: 1}
        }).then(() => {
            frm.reload_doc();
        });
    },
    get_production_key_button(frm) {
        // Get a public/private key pair from production
        if (frm.is_dirty()) {
            frappe.throw('Save form first!');
        }
        frappe.call({
            method: ebay_token_module + '.create_new_key_pair',
            args: {sandbox: 0}
        }).then(() => {
            frm.reload_doc();
        });
    }
});
