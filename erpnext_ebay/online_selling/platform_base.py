# -*- coding: utf-8 -*-
"""Base class for Online Selling platform"""
from __future__ import unicode_literals


class OnlineSellingPlatformClass(object):
    """This is a class used only to store data and methods in an easy-to-pass
    object. This could just as easily be a dictionary, but there is no
    significant harm to using a class here.

    This unimplemented abstract class is used primarily to document the class
    methods and objects that should be implemented."""

    # Should all entries be deleted on Item load?
    delete_entries_on_item_onload = True

    @classmethod
    def item_onload(cls, doc):
        """Regenerate Online Selling Items from an Item doc.
        If delete_onload is true, then old entries will have been deleted.
        """
        pass
