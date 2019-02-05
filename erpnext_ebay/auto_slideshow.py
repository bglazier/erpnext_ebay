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

import json
import frappe

uploads_path = os.path.join(os.sep, 'home', 'uploads')
#uploads_path= os.path.join(os.sep, 'Users', 'ben', 'uploads')

site_url = 'http://www.universaleresourcetrading.com'

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
    js = "erpnext_ebay_realtime_event('{}', '{}', '{}', '{}');"
    js = js.format(rte_id, tag, event, rte_msg)
    frappe.publish_realtime(event='eval_js', message=js,
                            user=frappe.session.user)


def resize_image(filename, out=None, thumbnail=False):
    """
    Use convert or mogrify to resize images
    Uses one of the below commands:

    mogrify -auto-orient -resize LxL> filename
    convert -auto-orient -resize LxL> filename out

    Resizes, rotates according to EXIF information, and resizes to fit into
    an L x L size box (trailing '>' symbol means that images will never
    be enlarged). The image size is taken from the ebay_image_size or
    ebay_thumbnail_size setting in Ebay_Settings_Manager.

    If out is set, the resized version is output to a new file (convert).
    Otherwise the modification takes place on the original file (mogrify).
    """

    if thumbnail:
        image_size = frappe.db.get_value(
            'eBay Manager Settings', filters=None,
            fieldname='ebay_thumbnail_size')
    else:
        image_size = frappe.db.get_value(
            'eBay Manager Settings', filters=None,
            fieldname='ebay_image_size')

    if image_size < 1:
        frappe.throw('Invalid image size: ' + str(image_size))

    size_string = '{}x{}>'.format(image_size, image_size)
    if out is not None:
        subprocess.call(
            ['convert', '-auto-orient', '-resize', size_string,
             filename, out])
    else:
        subprocess.call(
            ['mogrify', '-auto-orient', '-resize', size_string, filename])


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
        file_path = os.path.abspath(
            frappe.get_site_path('private', 'files', file_name))
    else:
        file_path = os.path.abspath(
            frappe.get_site_path('public', 'files', file_name))

    extension = os.path.splitext(file_name)[1].lower()

    if extension in ('.jpg', '.jpeg'):
        # Resize and autoorient this image
        resize_image(file_path)

    return ret


@frappe.whitelist(allow_guest=True)
def view_slideshow_py(slideshow):

    images_path = os.path.abspath(frappe.get_site_path('public'))

    sql = ("select image from `tabWebsite Slideshow Item` "
           "where parent='{}' order by idx").format(slideshow)
    image_list = frappe.db.sql(sql, as_dict=False)
    image_list = [x[0] for x in image_list]

    return image_list


@frappe.whitelist(allow_guest=True)
def process_new_images(item_code, rte_id, tag):
    """Read images from 'uploads' folder, sort and rename them, resize and
    auto-orient them, copy them to the site public images folder and finally
    create a website slideshow.

    Server-side part of auto-slideshow, called from a button on item page.
    """

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
    comment = frappe.get_doc("Item", item_code).add_comment(
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


def create_website_image(fname, item):
    """Create a symbolic link and a thumbnail, and set up file docs,
    ready to use as a Website Image.
    """

    public_site_files_path = os.path.abspath(
        frappe.get_site_path('public', 'files'))

    # Create a symbolic link and a thumbnail for the website image
    path, ext = os.path.splitext(fname)
    web_fname = path + '_web' + ext
    thumb_fname = path + '_thumb' + ext

    # Full paths to original file, web image symlink and thumbnail
    file_fpath = os.path.join(public_site_files_path, fname)
    web_fpath = os.path.join(public_site_files_path, web_fname)
    thumb_fpath = os.path.join(public_site_files_path, thumb_fname)

    # URLs on website for web image symlink and thumbnail
    web_url = '/' + os.path.join('files', web_fname)
    thumb_url = '/' + os.path.join('files', thumb_fname)

    # Create the symbolic link and create the thumbnail
    try:
        os.symlink(file_fpath, web_fpath)
    except OSError:
        if os.path.islink(web_fpath):
            os.remove(web_fpath)
            files = frappe.get_all(
                'File', filters={'file_url': web_url})
            for file in files:
                frappe.delete_doc('File', file['name'])
            os.symlink(file_fpath, web_fpath)
        else:
            raise
    resize_image(file_fpath, out=thumb_fpath, thumbnail=True)

    # Document for web image
    f = frappe.get_doc({
        "doctype": "File",
        "file_url": web_url,
        "file_name": web_fname,
        "attached_to_doctype": "Item",
        "attached_to_name": item,
        "attached_to_field": None,
        "folder": 'Home/Attachments',
        "file_size": os.path.getsize(web_fpath),
        "is_private": 0
    })
    f.insert(ignore_permissions=True)

    # Document for the thumbnail is not required.
    ## Document for thumbnail image
    #f = frappe.get_doc({
        #"doctype": "File",
        #"file_url": thumb_url,
        #"file_name": thumb_fname,
        #"attached_to_doctype": "Item",
        #"attached_to_name": item,
        #"attached_to_field": None,
        #"folder": 'Home/Attachments',
        #"file_size": os.path.getsize(thumb_fpath),
        #"is_private": 0
    #})
    #f.insert(ignore_permissions=True)

    return web_url, thumb_url


'''PROCESS ALL EXISTING PHOTOS PRIOR TO USING NEW PROCESS'''


#def create_slideshows_from_archive_photos():
    ## TODO need to test this
    #dlist = list_directories(images_path)

    #for l in dlist:
        #file_list = list_files(l)
        #for f in file_list:
            #item_name = f
            #create_slideshow('SS' + item_name)
            #create_slideshow_items('SS' + parent, file_list)

    #return


'''UTILITIES'''


#def list_directories(path):

    ## requires import os

    #directories = filter(os.path.isdir, os.listdir(path))

    #return directories


def list_files(path):
    # returns a list of names (with extension, without full path) of all files
    # in folder path

    # requires import os

    files = []
    for name in os.listdir(path):
        if os.path.isfile(os.path.join(path, name)):
            files.append(name)
    return files


#def scp_files(local_files):
    ## THIS IS OF NO USE AS FILES ARE NOT LOCAL !!?? Unless scp using static ip address?
    ## requires import scp

    #remote_file = local_files

    #client = scp.Client(host=host, user=user, password=password)

    ## and then
    #client.transfer(local_path + local_file, remote_path + remote_file)

    #return
