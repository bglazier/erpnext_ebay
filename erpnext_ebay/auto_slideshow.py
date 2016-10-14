# -*- coding: utf-8 -*-
# Copyright (c) 2015, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, os, shutil #, nltk   
from frappe.model.document import Document
from datetime import date

import xml.etree.cElementTree as ET



IS_TESTING = True


#Save to public directory so one can download
garage_xml_path = '/home/frappe/frappe-bench/sites/site1.local/public/files/xml/'
if(IS_TESTING): garage_xml_path = '/home/frappe/frappe-bench/sites/erpnext.vm/garagesale/xml/'


site_files_path= '/home/frappe/frappe-bench/sites/site1.local/public/files/'
if(IS_TESTING): site_files_path= '/home/frappe/frappe-bench/sites/erpnext.vm/public/files/'

temp_site_files_path= '/home/uploads/'

site_url = 'http://www.universaleresourcetrading.com'
if(IS_TESTING): site_url = 'http://127.0.0.1:8000'



@frappe.whitelist(allow_guest=True)
def process_new_images(item_code):
    
    # Called from a button on item page


    # Check docstatus - if not saved quit



    # Get user
    current_user = frappe.db.get_value("User", frappe.session.user, ["username"])
    temp_images_directory = temp_site_files_path + current_user + '/'

    # If slideshow exists then quit
    slideshow_code = 'SS-' + item_code
    
    if(is_exists_slideshow(item_code, slideshow_code)):
        frappe.throw(("Slideshow already created. Cannot create another."))
        return False
    
    
    # Images should already be uploaded onto local temp directory
    file_list = list_files(temp_images_directory)
    
    if(len(file_list) == 0): 
        frappe.throw(("There are no images to process. Please upload images first."))
        return False
    
    # Rename the files to ITEM-XXX
    idx = 0
    for src in file_list:
        #os.rename(temp_images_directory + src, temp_images_directory + item_code + '-' + str(idx) + '.jpg')
        shutil.move(temp_images_directory + src, temp_images_directory + item_code + '-' + str(idx) + '.jpg')
        idx += 1
    
    # move all the files to  site_files_path 
    new_file_list = list_files(temp_images_directory)
    for fname in new_file_list:
        #no point copying as on server anyway 
        shutil.move(temp_images_directory + fname, site_files_path + fname)
    
    
    # create the WS_IMAGE from the first photo - no need for slideshow if only 1 image
    #NOW DONE VIA SCRIPT frappe.db.set_value("Item", item_code, "website_image", '/files/' + item_code + '-0' + '.jpg')
    

     
    if(create_slideshow(slideshow_code)): 
        create_slideshow_items(slideshow_code, new_file_list)
        # ch = addchild(self.doc, 'slideshow', 'Slideshow', self.doclist)
        
        # Now slideshow created, need to link it to the item
        #NOW DONE VIA SCRIPT frappe.db.set_value("Item", item_code, "slideshow", slideshow_code)

    else: 
        frappe.throw(("There was a problem creating the slideshow.  You will need to do this manually"))
        return False

    return True


    
    
    
def is_exists_slideshow(item_code, slideshow_code):
    if not frappe.db.get_value("Item", item_code, "slideshow", slideshow_code):
        return False
    else:
        return True
    
def create_slideshow(item_name):
    
        
    slideshow_dict = {"doctype": "Website Slideshow", "slideshow_name": item_name, "docstatus": 0, "idx": 0}
    
    
    sshow = frappe.get_doc(slideshow_dict)
    sshow.insert(ignore_permissions = True)
    
    if sshow:
        return True
    else:
        return False


def create_slideshow_items(parent, file_list):
    idx = 0
    filename = ''
    
    for i in file_list:
        filename = '/files/' + i
        
        slideshowitem_dict = {"doctype": "Website Slideshow Item",
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
        sshowitems.insert(ignore_permissions = True)
        
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


    
