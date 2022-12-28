import frappe
from frappe.desk.reportview import build_match_conditions, get_filters_cond


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_customer_list(doctype, txt, searchfield, start, page_len, filters=None):
    from erpnext.controllers.queries import get_fields

    fields = ["name", "customer_name", "customer_group", "territory", "ebay_user_id"]

    if frappe.db.get_default("cust_master_name") == "Customer Name":
        fields = ["name", "customer_group", "territory", "ebay_user_id"]

    fields = ', '.join(
        f'`{x}`' for x in get_fields("Customer", fields)
    )

    match_conditions = build_match_conditions("Customer")
    match_conditions = "and {}".format(match_conditions) if match_conditions else ""

    if filters:
        filter_conditions = get_filters_cond(doctype, filters, [])
        match_conditions += "{}".format(filter_conditions)

    txt = txt.replace('\\', r'\\').replace('_', r'\_').replace('%', r'\%')
    txt_start = f'{txt}%'
    txt_both = f'%{txt}%'

    return frappe.db.sql(
        f"""
        SELECT {fields}
        FROM `tabCustomer`
        WHERE docstatus < 2
            AND (`{searchfield}` LIKE %(txt_both)s
                OR customer_name LIKE %(txt_both)s
                OR ebay_user_id LIKE %(txt_start)s)
            {match_conditions}
        ORDER BY
            CASE WHEN `name` LIKE %(txt_both)s THEN 0 ELSE 1 END,
            CASE WHEN `customer_name` LIKE %(txt_both)s THEN 0 ELSE 1 END,
            CASE WHEN `ebay_user_id` LIKE %(txt_start)s THEN 0 ELSE 1 END,
            `name`, `customer_name`, `ebay_user_id`
        LIMIT %(start)s, %(page_len)s;
        """, {
            'searchfield': searchfield,
            'txt_start': txt_start,
            'txt_both': txt_both,
            'start': start,
            'page_len': page_len
        }
    )
