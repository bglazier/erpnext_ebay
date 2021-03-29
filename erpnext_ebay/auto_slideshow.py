# -*- coding: utf-8 -*-
# Copyright (c) 2015, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

import os
import re
import shutil
from datetime import date

import json
import frappe

from erpnext_ebay.utils.slideshow_utils import (
    resize_image, create_website_image)

uploads_path = os.path.join(os.sep, 'home', 'uploads')

re_digitsearch = re.compile('([0-9]+)')


def realtime_eval(rte_id, tag, event, msg):
    """
    Use publish_realtime to run javascript code using custom event handler.

    rte_id: persistent id for the current form
    tag: communications tag specific to one series of communications
    event: name of custom event to trigger on client.
    msg: JSON serializable object (e.g. dict) to push to client.
    """

    rte_msg = json.dumps(msg)
    js = "erpnext_ebay.realtime_event('{}', '{}', '{}', '{}');"
    js = js.format(rte_id, tag, event, rte_msg)
    frappe.publish_realtime(event='eval_js', message=js,
                            user=frappe.session.user)


@frappe.whitelist()
def process_new_images(item_code, rte_id, tag):
    """Read images from 'uploads' folder, sort and rename them, resize and
    auto-orient them, copy them to the site public images folder and finally
    create a website slideshow.

    Server-side part of auto-slideshow, called from a button on item page.
    """

    # Whitelisted function; check permissions
    if not frappe.has_permission('Item', 'write'):
        frappe.throw('Need write permissions on Item!',
                     frappe.PermissionError)

    public_site_files_path = os.path.abspath(
        frappe.get_site_path('public', 'files'))

    ret_val = {'success': False}

    # Get user
    current_user = frappe.db.get_value(
        "User", frappe.session.user, ["username"])
    upload_images_directory = os.path.join(uploads_path, current_user)

    slideshow_code = 'SS-' + item_code

    # Check that no slideshow exists for this item, and that we don't have
    # an existing slideshow with a matching name ('SS-ITEM-?????')
    if frappe.db.get_value("Item", item_code, "slideshow", slideshow_code):
        frappe.msgprint("A website slideshow is already set for this item.")
        return ret_val

    if frappe.db.exists("Website Slideshow", slideshow_code):
        frappe.msgprint("A website slideshow with the name " + slideshow_code +
                        " already exists.")
        return ret_val

    # Images should already be uploaded onto local uploads directory
    # Sort these images into a 'natural' order
    file_list = list_files(upload_images_directory)
    n_files = len(file_list)
    file_dict = {}
    for file in file_list:
        file_dict[file] = tuple(int(x) if x.isdigit() else x
                                for x in re_digitsearch.split(file) if x)
    file_list.sort(key=lambda x: file_dict[x])

    if(n_files == 0):
        frappe.msgprint("There are no images to process. " +
                        "Please upload images first.")
        return ret_val

    # Update the number of images to process
    msg = {'command': 'set_image_number',
           'n_images': n_files}
    realtime_eval(rte_id, tag, 'update_slideshow', msg)

    new_file_list = []
    file_sizes = []

    # Rename the files to ITEM-XXXXX-Y and move all the files to
    # public_site_files_path
    w = len(str(n_files))
    for i, fname in enumerate(file_list, 1):
        new_fname = item_code + '-{num:0{width}}.jpg'.format(num=i, width=w)
        new_file_list.append(new_fname)

        upload_fpath = os.path.join(upload_images_directory, fname)
        site_fpath = os.path.join(public_site_files_path, new_fname)
        shutil.move(upload_fpath, site_fpath)

        # Now auto resize the image
        resize_image(site_fpath)

        # Url (relative to hostname) of file
        file_url = os.path.join('files', new_fname)

        # File size
        file_sizes.append(os.path.getsize(site_fpath))

        # Now update the slideshow
        msg = {'command': 'new_image',
               'img_id': i,
               'n_images': n_files,
               'file_url': file_url}
        realtime_eval(rte_id, tag, 'update_slideshow', msg)

    if create_slideshow(slideshow_code):
        create_slideshow_items(slideshow_code, new_file_list, file_sizes)
    else:
        frappe.msgprint("There was a problem creating the slideshow. " +
                        "You will need to do this manually")
        return ret_val

    # For now, assume the first image is the primary image
    # Note this is the idx which is one-indexed, not zero-indexed.
    idx_main_image = 1

    # Update the website slideshow
    frappe.db.set_value('Item', item_code, 'slideshow', slideshow_code)

    # Update the item image
    file_name = new_file_list[idx_main_image-1]
    image_url = os.path.join(
        'files', new_file_list[idx_main_image-1])
    frappe.db.set_value('Item', item_code, 'image', image_url)

    # Set up website image
    web_url, thumb_url = create_website_image(file_name, item_code)

    # Set the website image and thumbnail
    frappe.db.set_value('Item', item_code, 'website_image', web_url)
    frappe.db.set_value('Item', item_code, 'thumbnail', thumb_url)

    # Add a comment to the Item
    frappe.get_doc("Item", item_code).add_comment(
        "Attachment",
        "Auto Create Slideshow: Website slideshow {}".format(slideshow_code))

    # Allow the slideshow to close and update to show completion
    msg = {'command': 'done'}
    realtime_eval(rte_id, tag, 'update_slideshow', msg)

    ret_val['success'] = True
    return ret_val


def create_slideshow(slideshow_name):
    """Create the doc for the Website Slideshow.

    Returns the slideshow doc.
    """

    ss = frappe.get_doc({"doctype": "Website Slideshow",
                         "slideshow_name": slideshow_name})

    ss.insert(ignore_permissions=True)
    return ss


def create_slideshow_items(parent, file_list, file_sizes):
    """Creates the docs for the website slideshow items and the files.

    Creating the docs for the Website Slideshow Items is necessary for
    the website slideshow to work.
    Creating the docs for the Files is not required, but it is what Frappe
    does so we can replicate that. The files are also attached to the Website
    Slideshow rather than the individual Items.
    However: creating individual File docs means that deleting the Website
    Slideshow deletes the files.

    For now: this is deliberately 'broken'.
    """

    idx = 1
    for fname, fsize in zip(file_list, file_sizes):
        filename = '/files/' + fname

        s = frappe.get_doc({
            "doctype": "Website Slideshow Item",
            "parent": parent,
            "parentfield": "slideshow_items",
            "parenttype": "Website Slideshow",
            "image": filename,
            "idx": idx
            })
        idx += 1
        s.insert(ignore_permissions=True)

        # Disabled as we don't want to delete the files if the
        # Website Slideshow is deleted.
        #f = frappe.get_doc({
            #"doctype": "File",
            #"file_url": filename,
            #"file_name": fname,
            #"attached_to_doctype": "Website Slideshow",
            #"attached_to_name": parent,
            #"attached_to_field": None,
            #"folder": 'Home/Attachments',
            #"file_size": fsize,
            #"is_private": 0
        #})
        #f.insert(ignore_permissions=True)

    return


def list_files(path):
    # returns a list of names (with extension, without full path) of all files
    # in folder path

    # requires import os

    files = []
    for name in os.listdir(path):
        if os.path.isfile(os.path.join(path, name)):
            files.append(name)
    return files
