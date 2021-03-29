# -*- coding: utf-8 -*-
"""Custom methods for Item doctype"""

import json
from pathlib import Path

import frappe

from erpnext_ebay.utils.slideshow_utils import rotate_image

MAX_EBAY_IMAGES = 12


def website_slideshow_validate(doc, _method):
    """On Website Slideshow validate docevent."""

    if doc.number_of_ebay_images > MAX_EBAY_IMAGES:
        frappe.throw(
            f'Number of eBay images must be {MAX_EBAY_IMAGES} or fewer!')
    if doc.number_of_ebay_images < 1:
        frappe.throw('Number of eBay images must be 1 or greater!')


@frappe.whitelist()
def view_slideshow_py(slideshow):
    """Return a list of images from a Website Slideshow"""

    # Whitelisted function; check permissions
    if not frappe.has_permission('Item', 'read'):
        frappe.throw('Need read permissions on Item!',
                     frappe.PermissionError)

    image_dicts = frappe.get_all(
        'Website Slideshow Item',
        fields=['image'],
        filters={'parent': slideshow},
        order_by='idx')

    return [x.image for x in image_dicts]


@frappe.whitelist()
def save_with_rotations(doc):
    """Update (save) an existing Website Slideshow Item, rotating images
    as implied by the __direction attribute.

    :param doc: JSON or dict object with the properties of the document to
        be updated
    """
    if isinstance(doc, str):
        doc = json.loads(doc)

    # Extract directions
    directions = [x.get('__direction', None) for x in doc['slideshow_items']]

    doc = frappe.get_doc(doc)
    if not doc.has_permission("write"):
        raise frappe.PermissionError
    doc._original_modified = doc.modified
    doc.check_if_latest()

    # Check image urls have not been changed to prevent arbitrary files
    # being deleted/renamed
    image_urls = {
        x.image for x in frappe.get_all(
            'Website Slideshow Item',
            fields=['image'],
            filters={'parent': doc.name}
        )
    }
    for ssi in doc.slideshow_items:
        if ssi.image not in image_urls:
            frappe.throw('Not all images recognised')

    # List of files created and to delete
    new_file_paths = []
    delete_paths = []

    try:
        # Re-orient images
        for direction, ssi in zip(directions, doc.slideshow_items):
            if not direction:
                continue

            angle = int(direction) * 90

            # Get curent and new file path
            stripped_url = ssi.image.strip('/')
            if stripped_url.startswith('http'):
                frappe.msgprint(f'Cannot rotate external image {ssi.image}')
            if stripped_url.startswith('private/'):
                frappe.msgprint(f'Cannot rotate private image {ssi.image}!')
                continue
            elif not stripped_url.startswith('files/'):
                frappe.throw('Unknown image URL error! ', ssi.image)
            file_path = Path(frappe.utils.get_files_path(stripped_url[6:]))
            if not file_path.exists():
                frappe.msgprint(f'Cannot find image {ssi.image} to rotate')
                continue
            # Construct new file path
            # TODO - use Path.with_stem when using Python 3.9
            if file_path.stem[-7:] in ('-ROT090', '-ROT180', '-ROT270'):
                new_path_base_stem = file_path.stem[:-7]
                # Naming is in relation to the _original_ angle of the file
                angle_from_orig = (int(file_path.stem[-3:]) + angle) % 360
                angle_suffix = (
                    f'-ROT{angle_from_orig:03d}' if angle_from_orig else ''
                )
            else:
                new_path_base_stem = file_path.stem
                angle_suffix = f'-ROT{angle:03d}'
            new_path = file_path.with_name(
                f'{new_path_base_stem}{angle_suffix}{file_path.suffix}'
            )
            # Now check filename is free
            i = 1
            while new_path.exists():
                new_path = new_path.with_name(
                    f'{new_path_base_stem}-{i}{angle_suffix}{new_path.suffix}'
                )
                i += 1
                if i > 9999:
                    frappe.throw('Too many images already! ', new_path)

            # Rotate image to new filename
            err_message = rotate_image(file_path, new_path, angle)

            if not err_message:
                new_file_paths.append(new_path)
            else:
                frappe.msgprint(
                    f'Unable to rotate image {ssi.image}: {err_message}')
                continue

            # Update doc
            url_index = new_path.parts.index('files')
            new_url = f"""/files/{'/'.join(new_path.parts[url_index+1:])}"""
            ssi.image = new_url

            # Check if in use in other website slideshows or has a File document,
            # and add to list if not
            if frappe.get_all('File', filters={'file_url': ssi.image}):
                continue
            elif frappe.get_all('Website Slideshow Item',
                                filters={
                                    'parent': ['!=', doc.name],
                                    'image': ssi.image
                                }):
                # Another website slideshow uses this image
                continue
            delete_paths.append(file_path)

        doc.save()
        # If we have successfully saved the document, don't delete
        # new files on exit
        new_file_paths = []

    finally:
        # If we have not completed successfully, delete new files
        # (if we have completed successfully, new_file_paths will be empty)
        for new_path in new_file_paths:
            new_path.unlink()

    frappe.db.commit()
    # Try to clear old files (but only raise warning on failure)
    err_messages = []
    for delete_path in delete_paths:
        try:
            delete_path.unlink()
        except Exception as e:
            err_messages.append(f'{delete_path} ({e})')
    if err_messages:
        frappe.msgprint(f"Could not remove files: {', '.join(err_messages)}")

    return doc.as_dict()
