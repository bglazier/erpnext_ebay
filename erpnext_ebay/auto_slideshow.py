# -*- coding: utf-8 -*-
# Copyright (c) 2015, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import os
import re
import operator
import shutil
import subprocess
from datetime import date
import xml.etree.cElementTree as ET

import json
import frappe
from frappe.model.document import Document

site_files_path = os.path.join(frappe.utils.get_bench_path(), 'sites',
                               frappe.get_site_path())
public_site_files_path = os.path.join(site_files_path, 'public', 'files')
private_site_files_path = os.path.join(site_files_path, 'private', 'files')


uploads_path = os.path.join(os.sep, 'home', 'uploads')
#uploads_path= os.path.join(os.sep, 'Users', 'ben', 'uploads')

site_url = 'http://www.universaleresourcetrading.com'

re_digitsearch = re.compile('([0-9]+)')


def resize_image(filename):
    """
    Use mogrify to resize images for an item_code
    mogrify -resize -auto-orient 1728x1728
    """
    subprocess.call(['mogrify', '-auto-orient', '-resize', '1728x1728>', filename])


def ugs_save_file_on_filesystem_hook(*args, **kwargs):
    """Intercept all write_file events, and mogrify images

    Replaces the standard write_file event. Obtains the filename, content_type
    etc. Calls the normal backup 'save_file_on_filesystem' with all arguments.
    If we do not handle the attachment specially, this function is entirely
    transparent. However, we can handle specific file types as we see fit - in
    this case we mogrify JPG and JPEG images. save_file_on_filesystem does
    strange things, so we need to reconstruct the filename using analagous
    logic - this could break in future with Frappe changes."""

    ret = frappe.utils.file_manager.save_file_on_filesystem(*args, **kwargs)

    file_name = ret['file_name']
    #file_url = ret['file_url'] # Not a consistent file system identifier

    if ('is_private' in kwargs) and kwargs['is_private']:
        file_path = os.path.join(private_site_files_path, file_name)
    else:
        file_path = os.path.join(public_site_files_path, file_name)

    extension = os.path.splitext(file_name)[1].lower()

    if extension in ('.jpg', '.jpeg'):
        # Resize and autoorient this image
        resize_image(file_path)

    return ret


@frappe.whitelist(allow_guest=True)
def view_slideshow_py(slideshow):

    images_path = os.path.join(os.sep, frappe.utils.get_bench_path(), 'sites',
                               frappe.get_site_path(), 'public')

    html = """<html><head></head><body>"""
    html += """<h3>{}</h3>""".format(slideshow)

    sql = """select image from `tabWebsite Slideshow Item` where parent = '{}'""".format(slideshow)
    records = frappe.db.sql(sql, as_dict=True)

    for r in records:
        html += """<p>{}</p>""".format(r.image)
        html += """<img src="{}" height="250" width="300">""".format(r.image)
        html += """<br>"""

    html += """</body></html>"""

    return html


@frappe.whitelist(allow_guest=True)
def process_new_images(item_code, rte_id):
    """Read images from 'uploads' folder, sort and rename them, resize and
    auto-orient them, copy them to the site public images folder and finally
    create a website slideshow.

    Server-side part of auto-slideshow, called from a button on item page.
    """

    # Get user
    current_user = frappe.db.get_value("User", frappe.session.user, ["username"])
    temp_images_directory = os.path.join(uploads_path, current_user)

    # If slideshow exists then quit
    slideshow_code = 'SS-' + item_code

    # Check that no slideshow exists for this item, and that we don't have
    # an existing slideshow with a matching name ('SS-ITEM-?????')
    if frappe.db.get_value("Item", item_code, "slideshow", slideshow_code):
        frappe.msgprint("A website slideshow is already set for this item.")
        return False

    if frappe.db.exists("Website Slideshow", slideshow_code):
        frappe.msgprint("A website slideshow with the name " + slideshow_code +
                        " already exists.")
        return False

    # Images should already be uploaded onto local temp directory
    # Sort these images into a 'natural' order
    file_list = list_files(temp_images_directory)
    n_files = len(file_list)
    file_dict = {}
    for file in file_list:
        file_dict[file] = tuple(int(x) if x.isdigit() else x
                                for x in re_digitsearch.split(file) if x)
    file_list.sort(key=lambda x: file_dict[x])

    if(n_files == 0):
        frappe.msgprint("There are no images to process. " +
                        "Please upload images first.")
        return False

    # Update the number of images to process
    rte_msg = {'command': 'set_image_number',
               'n_images': n_files}
    rte_msg = json.dumps(rte_msg)

    js = "erpnext_ebay_realtime_event('{}', 'update_slideshow', '{}');"
    js = js.format(rte_id, rte_msg)
    frappe.publish_realtime(event='eval_js', message=js,
                            user=frappe.session.user)

    # Rename the files to ITEM-XXX
    new_file_list = []
    for i, src in enumerate(file_list):
        fn = item_code + '-' + str(i) + '.jpg'
        shutil.move(os.path.join(os.sep, temp_images_directory, src),
                    os.path.join(os.sep, temp_images_directory, fn))
        new_file_list.append(fn)

    # move all the files to public_site_files_path
    for i, fname in enumerate(new_file_list):
        site_filename = os.path.join(public_site_files_path, fname)
        temp_filename = os.path.join(temp_images_directory, fname)
        shutil.move(temp_filename, site_filename)

        # Now auto resize the image
        resize_image(site_filename)
        
        # Url (relative to hostname) of file
        file_url = os.path.join('files', os.path.basename(site_filename))

        # Now update the slideshow
        rte_msg = {'command': 'new_image',
                   'img_id': i+1,
                   'n_images': n_files,
                   'file_url': file_url}
        rte_msg = json.dumps(rte_msg)

        js = "erpnext_ebay_realtime_event('{}', 'update_slideshow', '{}');"
        js = js.format(rte_id, rte_msg)
        frappe.publish_realtime(event='eval_js', message=js,
                                user=frappe.session.user)

    # create the WS_IMAGE from the first photo - no need for slideshow if only 1 image
    #NOW DONE VIA SCRIPT frappe.db.set_value("Item", item_code, "website_image", '/files/' + item_code + '-0' + '.jpg')

    if create_slideshow(slideshow_code):
        create_slideshow_items(slideshow_code, new_file_list)

    else:
        frappe.msgprint("There was a problem creating the slideshow. " +
                        "You will need to do this manually")
        return False

    # Allow the slideshow to close and update to show completion
    rte_msg = {'command': 'done'}
    rte_msg = json.dumps(rte_msg)

    js = "erpnext_ebay_realtime_event('{}', 'update_slideshow', '{}');"
    js = js.format(rte_id, rte_msg)
    frappe.publish_realtime(event='eval_js', message=js,
                            user=frappe.session.user)

    return "success"


#def is_exists_slideshow(item_code, slideshow_code):
    #"""Check if a slideshow exists for this item and slideshow code."""
    ##if not frappe.db.get_value("Item", item_code, "slideshow", slideshow_code):
        ##return False
    ##else:
        ##return True
    #print("is_exists_slideshow: ", item_code, slideshow_code)
    #print(frappe.db.get_value("Item", item_code, "slideshow", slideshow_code))
    #return bool(frappe.db.get_value("Item", item_code, "slideshow", slideshow_code))


def create_slideshow(item_name):

    slideshow_dict = {"doctype": "Website Slideshow",
                      "slideshow_name": item_name,
                      "docstatus": 0,
                      "idx": 0}

    sshow = frappe.get_doc(slideshow_dict)
    sshow.insert(ignore_permissions=True)

    if sshow:
        return True
    else:
        return False


def create_slideshow_items(parent, file_list):
    idx = 0
    filename = ''

    for i in file_list:
        filename = '/files/' + i

        slideshowitem_dict = {
            "doctype": "Website Slideshow Item",
            "parent": parent,
            "parentfield": "slideshow_items",
            "parenttype": "Website Slideshow",
            "image": filename,
            "idx": idx
            #TODO #"heading": 'TEST',
            #TODO"description": 'TEST'
            }
        idx += 1
        sshowitems = frappe.get_doc(slideshowitem_dict)
        sshowitems.insert(ignore_permissions=True)

    return


'''PROCESS ALL EXISTING PHOTOS PRIOR TO USING NEW PROCESS'''


def create_slideshows_from_archive_photos():
    # TODO need to test this
    dlist = list_directories(images_path)

    for l in dlist:
        file_list = list_files(l)
        for f in file_list:
            item_name = f
            create_slideshow('SS' + item_name)
            create_slideshow_items('SS' + parent, file_list)

    return


'''UTILITIES'''


def list_directories(path):

    # requires import os

    directories = filter(os.path.isdir, os.listdir(path))

    return directories


def list_files(path):
    # returns a list of names (with extension, without full path) of all files
    # in folder path

    # requires import os

    files = []
    for name in os.listdir(path):
        if os.path.isfile(os.path.join(path, name)):
            files.append(name)
    return files


def scp_files(local_files):
    # THIS IS OF NO USE AS FILES ARE NOT LOCAL !!?? Unless scp using static ip address?
    # requires import scp

    remote_file = local_files

    client = scp.Client(host=host, user=user, password=password)

    # and then
    client.transfer(local_path + local_file, remote_path + remote_file)

    return
