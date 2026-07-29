# -*- coding: utf-8 -*-
"""Dictionaries for looking up Online Selling handling code"""

import frappe


def get_platform_dict():
    """Return a dict of selling platform names to their handler classes.

    Platforms are registered via the 'online_selling_platforms' hook,
    which maps each platform name to the dotted path of its handler
    class. If multiple apps register the same platform name, the
    last-installed app wins.
    """
    platform_hooks = frappe.get_hooks('online_selling_platforms') or {}
    return {
        platform_name: frappe.get_attr(dotted_paths[-1])
        for platform_name, dotted_paths in platform_hooks.items()
    }
