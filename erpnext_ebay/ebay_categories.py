# -*- coding: utf-8 -*-
"""Functions to deal with eBay categories and relevant category options."""

import json

import frappe
from frappe import msgprint

from erpnext_ebay.ebay_get_requests import ebay_logger
from erpnext_ebay.ebay_requests_rest import (
    get_default_category_tree_id, get_category_tree, get_category_policies
)
from erpnext_ebay.ebay_constants import *


@frappe.whitelist()
def category_sync(force_override_categories=False):
    """Load a new set of eBay categories.

    By default, this checks the current versions of the eBay categories cache
    and does not update it if the category version has not changed (i.e. the
    eBay categories have not changed).
    If force_override_categories is set, then the eBay categories will be
    redownloaded and new Item Group eBay entries set.
    """
    # Check permissions, as this is a whitelisted function
    if 'System Manager' not in frappe.get_roles(frappe.session.user):
        return frappe.PermissionError(
            'Only System Managers can update the eBay categories.')
    # Assume we must update unless we have a cache version and the
    # eBay category tree version matches
    update_categories = True
    if not force_override_categories:
        tree_info = get_cache_tree_version()
        if tree_info:
            ebay_tree_info = get_default_category_tree_id()
            match = all(
                ebay_tree_info[f] == tree_info[f]
                for f in ('category_tree_id', 'category_tree_version')
            )
            if match:
                update_categories = False
    if update_categories:
        # Update the category cache
        update_category_cache()
        # Update the Item Group eBay categories.
        create_item_group_ebay(force_override_categories)


def get_cache_tree_version():
    """Check existence and non-emptyness of tables, and check and
    return default tree id and tree version number as a dict.
    Returns None if cache does not exist.
    """
    tables_list = frappe.db.get_tables()

    # Check categories cache
    if 'eBay_categories_info' in tables_list:
        # Table exists
        categories_info = frappe.db.sql(
            """SELECT category_tree_id, category_tree_version
            FROM eBay_categories_info;
            """, as_dict=True
        )
        if categories_info:
            # Table is not empty; get version
            return categories_info[0]
    return None


def update_category_cache(tree_id=None):
    """Update the eBay categories cache for the provided tree ID."""

    # If we don't have a tree ID, get one
    if tree_id is None:
        tree_id = get_default_category_tree_id()['category_tree_id']

    # Load using the eBay API
    cat_tree = get_category_tree(tree_id)
    category_info = {
        'category_tree_id': cat_tree['category_tree_id'],
        'category_tree_version': cat_tree['category_tree_version']
    }

    def get_cat_dict(category, parent=None):
        """Fetch the various category properties of interest.
        Adds a key 'category_parent' set equal to the supplied value.
        """
        cat_dict = {}
        for key, value in category.items():
            if key == 'category':
                cat_dict.update(value)
            elif key == 'child_category_tree_nodes':
                continue
            elif key == 'leaf_category_tree_node':
                cat_dict[key] = bool(value)
            else:
                cat_dict[key] = value
        cat_dict['category_parent'] = parent
        return cat_dict

    def unroll_cat(category, parent=None):
        """Given a category in the eBay category tree hierarchy, return a list
        of the category plus all of its child categories.
        Returns a list.
        """
        cat_dict = get_cat_dict(category, parent=parent)
        category_list = [cat_dict]
        children = category['child_category_tree_nodes']
        if children:
            for child_cat in children:
                category_list.extend(
                    unroll_cat(child_cat, parent=cat_dict['category_id'])
                )
        return category_list

    root_cat = cat_tree['root_category_node']
    if root_cat['category']['category_id'] != '0':
        frappe.throw('Unexpected root category category_id')
    categories_data = unroll_cat(root_cat)
    max_level = max(x['category_tree_node_level'] for x in categories_data)

    # Get category policies data
    # Filter to only policies on this tree
    category_policies = [
        x for x in get_category_policies()['category_policies']
        if x['category_tree_id'] == tree_id
    ]
    BOOL_FIELDS = (
        'auto_pay_enabled', 'b2b_vat_enabled', 'expired', 'intangible_enabled',
        'lsd', 'orpa', 'orra', 'reduce_reserve_allowed', 'value_category',
        'virtual'
    )
    for category in category_policies:
        payment_methods = category.pop('payment_methods')
        for field, value in category.items():
            if field in BOOL_FIELDS:
                category[field] = bool(value)
        category['payment_methods'] = json.dumps(payment_methods)

    # Create SQL cache
    set_ebay_categories_cache(
        category_info, categories_data, category_policies
    )

    frappe.db.set_single_value(
        'eBay Manager Settings',
        'ebay_categories_cache_maximum_level',
        max_level
    )


def create_ebay_categories_cache_tables():
    """Create SQL tables for the categories dictionaries"""

    tables_list = frappe.db.get_tables()  # Can't use db.table_exists here

    # Drop the tables if they exist
    if 'eBay_categories_info' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_categories_info""",
                      auto_commit=True)
    if 'eBay_categories_hierarchy' in tables_list:
        frappe.db.sql("""DROP TABLE eBay_categories_hierarchy""",
                      auto_commit=True)

    # Create the tables
    frappe.db.sql("""
        CREATE TABLE eBay_categories_info (
            category_tree_id VARCHAR(19),
            category_tree_version VARCHAR(19)
        )""", auto_commit=True)

    frappe.db.sql("""
        CREATE TABLE eBay_categories_hierarchy (
            category_id VARCHAR(19) NOT NULL,
            category_name TEXT,
            category_tree_node_level INT,
            leaf_category_tree_node BOOLEAN,
            parent_category_tree_node_href TEXT,
            category_parent VARCHAR(19),
            auto_pay_enabled BOOLEAN,
            b2b_vat_enabled BOOLEAN,
            ean_support VARCHAR(10),
            expired BOOLEAN,
            intangible_enabled BOOLEAN,
            isbn_support VARCHAR(10),
            lsd BOOLEAN,
            minimum_reserve_price DECIMAL(21, 9),
            orpa BOOLEAN,
            orra BOOLEAN,
            payment_methods TEXT,
            reduce_reserve_allowed BOOLEAN,
            upc_support VARCHAR(10),
            value_category BOOLEAN,
            virtual BOOLEAN,
            PRIMARY KEY (category_id),
            FOREIGN KEY (category_parent)
                REFERENCES eBay_categories_hierarchy(category_id)
        )""", auto_commit=True)


def set_ebay_categories_cache(categories_info, categories_data,
                              category_policies):
    """Save caches for the categories dictionaries"""

    create_ebay_categories_cache_tables()

    frappe.db.sql("""
        INSERT INTO `eBay_categories_info`
        VALUES (%(category_tree_id)s, %(category_tree_version)s);
        """, categories_info)

    for category in categories_data:
        frappe.db.sql("""
            INSERT INTO `eBay_categories_hierarchy`
            (
                category_id, category_name,
                category_tree_node_level, leaf_category_tree_node,
                parent_category_tree_node_href, category_parent
            )
            VALUES (
                %(category_id)s, %(category_name)s,
                %(category_tree_node_level)s, %(leaf_category_tree_node)s,
                %(parent_category_tree_node_href)s, %(category_parent)s
            );""", category)

    for category in category_policies:
        frappe.db.sql("""
            UPDATE `eBay_categories_hierarchy`
            SET
                auto_pay_enabled = %(auto_pay_enabled)s,
                b2b_vat_enabled = %(b2b_vat_enabled)s,
                ean_support = %(ean_support)s,
                expired = %(expired)s,
                intangible_enabled = %(intangible_enabled)s,
                isbn_support = %(isbn_support)s,
                lsd = %(lsd)s,
                minimum_reserve_price = %(minimum_reserve_price)s,
                orpa = %(orpa)s,
                orra = %(orra)s,
                payment_methods = %(payment_methods)s,
                reduce_reserve_allowed = %(reduce_reserve_allowed)s,
                upc_support = %(upc_support)s,
                value_category = %(value_category)s,
                virtual = %(virtual)s
            WHERE category_id = %(category_id)s;""", category)

    frappe.db.commit()


def create_item_group_ebay(force_delete=False):
    """Creates Item Group Ebay documents from the eBay categories cache."""

    # DANGER - items that link to these Item Group eBay documents will be
    # left hanging if the categories disappear.

    if not force_delete:
        # If we are not force-deleting, check for current Item Group eBay
        # entries. We will prefer to update these rather than replace them.
        ige_list = frappe.db.sql("""
            SELECT ebay_category_id, ebay_category_name, ebay_category,
                ebay_expired, ebay_virtual, name
                FROM `tabItem Group eBay`;
            """, as_dict=True)

        ige_dict = {x['ebay_category_id']: x for x in ige_list}

        if len(ige_list) != len(ige_dict):
            # There are multiple categories with the same ebay_category_id
            force_delete = True
        del ige_list

    if force_delete:
        # This is slower than TRUNCATE TABLE but doesn't lead to an
        # implicit commit, which often causes an error.
        frappe.db.sql("""DELETE FROM `tabItem Group eBay`;""")
        frappe.db.commit()
        ige_dict = {}

    cats = frappe.db.sql("""
        SELECT category_id, category_parent, category_name,
            leaf_category_tree_node, virtual, expired
            FROM eBay_categories_hierarchy;
        """, as_dict=True)

    parent_dict = {}
    names_dict = {}
    for cat in cats:
        parent_dict[cat.category_id] = cat.category_parent
        names_dict[cat.category_id] = cat.category_name

    # Filter out non-leaf categories
    cats = [x for x in cats if x.leaf_category_tree_node]
    cat_ids = {x.category_id for x in cats}

    # Delete any categories that exist in the DB but are not current
    if not force_delete:
        ige_cat_ids = set(ige_dict.keys())
        deleted_ids = ige_cat_ids - cat_ids
        for deleted_id in deleted_ids:
            frappe.delete_doc('Item Group eBay', ige_dict[deleted_id].name,
                              force=True)

    for i, cat in enumerate(cats):
        cat_id = cat.category_id
        cat_name = f"""{cat.category_name} {cat_id}"""
        cat_name_stack = [cat.category_name]
        cat_search_id = parent_dict[cat_id]
        while cat_search_id != "0":
            cat_name_stack.append(names_dict[cat_search_id])
            cat_search_id = parent_dict[cat_search_id]

        cat_name_stack.reverse()
        cat_label = ' | '.join(cat_name_stack)  # or ' => '

        # Test if this category already exists
        if not force_delete and cat['category_id'] in ige_dict:
            # Matching category ID exists. If it matches perfectly,
            # we do nothing.
            ige = ige_dict[cat_id]
            if not (ige['ebay_category_name'] == cat_name
                    and ige['ebay_category'] == cat_label
                    and ige['ebay_expired'] == cat.expired
                    and ige['ebay_virtual'] == cat.virtual):
                # Update the not-quite matching category
                item_group_ebay_doc = frappe.get_doc(
                    'Item Group eBay', ige['name'])
                item_group_ebay_doc.ebay_category_name = cat_name
                item_group_ebay_doc.ebay_category = cat_label
                item_group_ebay_doc.ebay_expired = cat.expired
                item_group_ebay_doc.ebay_virtual = cat.virtual
                item_group_ebay_doc.save()
            del ige_dict[cat_id]

        else:
            # No matching category found - create a new category
            item_group_ebay_doc = frappe.get_doc({
                "doctype": "Item Group eBay",
                "ebay_category_id": cat.category_id,
                "ebay_category_name": cat_name,
                "ebay_category": cat_label,
                "ebay_expired": cat.expired,
                "ebay_virtual": cat.virtual
            })

            item_group_ebay_doc.insert(ignore_permissions=True)

    frappe.db.commit()
