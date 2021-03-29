# -*- coding: utf-8 -*-
# Copyright (c) 2021, Universal Resource Trading Limited and contributors
# For license information, please see license.txt
"""Utilities relating to images and slideshows"""

import imghdr
import os
import subprocess

from PIL import Image
from jpegtran import JPEGImage

import frappe
from frappe.core.doctype.file.file import File as FrappeFileDoc


# Save file hook to shrink and auto-orient images

def erpnext_ebay_save_file_on_filesystem_hook(*args, **kwargs):
    """Intercept all write_file events, and mogrify images

    Replaces the standard write_file event. Obtains the filename, content_type
    etc. Calls the normal backup 'save_file_on_filesystem' with all arguments.
    If we do not handle the attachment specially, this function is entirely
    transparent. However, we can handle specific file types as we see fit - in
    this case we mogrify JPG and JPEG images. save_file_on_filesystem does
    strange things, so we need to reconstruct the filename using analagous
    logic - this could break in future with Frappe changes.

    Also this may now (V12) be called from a File doctype, which means we need
    to check for this and deal with it appropriately.
    """

    if len(args) == 1 and isinstance(args[0], FrappeFileDoc):
        # We are being called from a file-type doc
        ret = args[0].save_file_on_filesystem()
    else:
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


# Functions to resize or rotate images

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
    image_size = int(image_size)

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


def rotate_image(old_path, new_path, angle):
    """Rotate an image (where possible losslessly).
    Only supports angles 90, 180, and 270 degrees.

    Returns an error message on failure; otherwise, None.
    """
    SUPPORTED_FORMATS = ('gif', 'pbm', 'pgm', 'ppm', 'tiff', 'xbm',
                         'jpeg', 'bmp', 'png', 'webp')

    PILLOW_TRANSPOSE = {
        90: Image.ROTATE_90,
        180: Image.ROTATE_180,
        270: Image.ROTATE_270
    }
    JPEGTRAN_ANGLES = {  # JPEGtran rotates are clockwise, not anticlockwise
        90: 270,
        180: 180,
        270: 90
    }

    if angle not in (90, 180, 270):
        frappe.throw('Invalid angle supplied to rotate_image!')

    image_type = imghdr.what(old_path)
    if not image_type:
        return 'Could not identify image type'
    if image_type not in SUPPORTED_FORMATS:
        return f'Unsupported image type {image_type}'
    if image_type == 'jpeg':
        # Lossless JPEG rotation
        image = JPEGImage(str(old_path))
        if image.exif_orientation != 1:
            image = image.exif_autotransform()
        image.rotate(JPEGTRAN_ANGLES[angle]).save(str(new_path))
    else:
        # Use Pillow
        image = Image.open(old_path)
        image_format = image.format
        image = image.transpose(PILLOW_TRANSPOSE[angle])
        image.save(new_path, format=image.format)


# Functions to set up images and thumbnails for the Item/Website Slideshow
# documents

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
                frappe.delete_doc('File', file['name'],
                                  ignore_permissions=True)
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
    try:
        f.insert(ignore_permissions=True)
    except frappe.FileAlreadyAttachedException:
        # If already attached, don't attach again
        pass

    return web_url, thumb_url
