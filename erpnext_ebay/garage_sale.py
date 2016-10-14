# -*- coding: utf-8 -*-
# Copyright (c) 2015, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, os, shutil #, nltk   
from frappe.model.document import Document
from datetime import date

import xml.etree.cElementTree as ET
import requests
#import mechanize

IS_TESTING = True


#Save to public directory so one can download
garage_xml_path = '/home/frappe/frappe-bench/sites/site1.local/public/files/xml/'
if(IS_TESTING): garage_xml_path = '/home/frappe/frappe-bench/sites/erpnext.vm/public/files/xml/'


site_files_path= '/home/frappe/frappe-bench/sites/site1.local/public/files/'
if(IS_TESTING): site_files_path= '/home/frappe/frappe-bench/sites/erpnext.vm/public/files/'



images_url = 'http://www.universaleresourcetrading.com'



def exists(path):
    r = requests.head(path)
    return r.status_code == requests.codes.ok


'''
def exists2(path):
    br = mechanize.Browser()
    br.set_handle_redirect(False)
    try:
        br.open_novisit(path)
        return True
    except:
        return False
'''

'''GARAGE SALE STUFF'''

@frappe.whitelist()
def run_cron_create_xml():
    
    #added to apps/frappe/frappe/hooks.py:
    # "unigreenscheme.unigreenscheme.doctype.booking.booking.run_cron_create_xml",
    today = date.today()
    
    export_to_garage_sale_xml(today.isoformat())
    
    return




def export_to_garage_sale_xml(creation_date):
    post_code = "NP4 0HZ"
    design = "Pro: Classic"
    layout = "thumb gallery"
    decline = 0.9
    accept = 0.1
    duration = 30
    handling_time = 3

    
    root = ET.Element("items")

    records = get_item_records_by_creation(creation_date)
    #records = get_item_records_by_item(code)
    
    for r in records:
        title = r.item_name
        item_code = r.name
        price = r.price_list_rate
        quantity = r.actual_qty
        ws_image = r.website_image
        ss_images_list = get_slideshow_records(r.slideshow)
        condition_description = r.grade_details
        category = lookup_category(r.item_group)
                
        body = r.description
        if r.accessories_extras: body += r.accessories_extras
        body += "<b>No cables, remotes, accessories, power supplies, consumables or any other item is included unless show in the item photo or description</b>"
        body += "<h3>Grade</h3>"
        body += grade(r.condition, r.function_grade)
        body += "<br>"
        if condition_description: body += condition_description
        body += "<h3>Detailed Description</h3>"
        
        
        if(not price):
            price = 0.0  
            #TODO Probably better writing this to a LOG file and not exporting it?
        
        #quantity = 1
        if(not quantity):
            quantity = 1
            # or break ??        
        
        doc = ET.SubElement(root, "item")

        ET.SubElement(doc, "bestOffer").text = "true"
        ET.SubElement(doc, "bestOfferAutoAcceptPrice").text = str(price - (price * accept))
        ET.SubElement(doc, "bestOfferAutoDeclinePrice").text = str(price - (price * decline))         
        ET.SubElement(doc, "buyItNowPrice").text = str(price)
        ET.SubElement(doc, "category").text = category 
        #ET.SubElement(doc, "category2").text =
        ET.SubElement(doc, "condition").text = lookup_condition(r.condition)
        ET.SubElement(doc, "conditionDescription").text = condition_description
        ET.SubElement(doc, "convertDescriptionToHTML").text = "true"
        ET.SubElement(doc, "convertMarkdownToHTML").text = "true"
        ET.SubElement(doc, "description").text = body
        ET.SubElement(doc, "design").text = design
        #dom_ship = ET.SubElement(doc, "domesticShippingService").text =
        #dom_ship.set("serviceAdditionalFee", "0")
        #dom_ship.set("serviceFee", "0")
        ET.SubElement(doc, "duration").text = str(duration)
        ET.SubElement(doc, "handlingTime").text = str(handling_time)          


        for ssi in ss_images_list:
            if exists2('127.0.0.1:8000/' + ssi.image):
                ET.SubElement(doc, "imageURL").text = images_url + ssi.image
            else:
                throw('Problem with image' + ssi.image)

        # IF there is no slideshow then try the ws_image
        #if(!ssi):
        #    if (r.website_image != 'NULL'):
        #        ET.SubElement(doc, "imageURL").text = images_url + ws_image
        
        #int_ship = ET.SubElement(doc, "internationalShippingService").text = ""
        #int_ship.set("serviceAdditionalFee", "0")
        #int_ship.set("serviceFee","0")        

        ET.SubElement(doc, "layout").text = layout
        #ET.SubElement(doc, "lotSize").text = "1"
        #ET.SubElement(doc, "packageDepth").text = ""
        #ET.SubElement(doc, "packageLength").text = ""
        #ET.SubElement(doc, "packageOunces").text = ""
        #ET.SubElement(doc, "packagePounds").text = ""
        #ET.SubElement(doc, "packageWidth").text = ""
        #ET.SubElement(doc, "paymentInstructions").text = ""
        ET.SubElement(doc, "privateAuction").text = "false"
        ET.SubElement(doc, "quantity").text = str(quantity)
        #ET.SubElement(doc, "reservePrice").text = ""
        #ET.SubElement(doc, "siteName").text = ""
        ET.SubElement(doc, "SKU").text = item_code
        #ET.SubElement(doc, "startingBid").text = ""
        #ET.SubElement(doc, ****storCaterogry).text = ""
        #ET.SubElement(doc, "subTitle").text = sub_title
        ET.SubElement(doc, "title").text = title
        #ET.SubElement(doc, "variation").text = ""
        ET.SubElement(doc, "zipCode").text = post_code
        
            
        tree = ET.ElementTree(root)
        today = date.today()
        tree.write(garage_xml_path + today.isoformat() + "_garageimportfile.xml")

        

    return




def grade(cond, func):

    c1 = ''
    f1 = ''
    c2 = ''
    f2 = ''
    c3 = ''
    f3 = ''
    c4 = ''
    f4 = ''
    c5 = ''
    f5 = ''

    grade = ''

    if cond and func:
        grade += '<table>'

        grade += '<tr>'
        grade += '<td>Grade 1</td>'
        if cond == '1': grade += '<td><b>' + c1 + '</b></td>' else: grade += '<td>' + c1 + '</td>'
        if func == '1': grade += '<td><b>' + c1 + '</b></td>' else: grade += '<td>' + c1 + '</td>'

        grade += '</tr>'

        grade += '<tr>'
        grade += '<td>Grade 2</td>'
        if cond == '2': grade += '<td><b>' + c2 + '</b></td>' else: grade += '<td>' + c2 + '</td>'
        if func == '2': grade += '<td><b>' + c2 + '</b></td>' else: grade += '<td>' + c2 + '</td>'
        grade += '</tr>'

        grade += '<tr>'
        grade += '<td>Grade 3</td>'
        if cond == '3': grade += '<td><b>' + c3 + '</b></td>' else: grade += '<td>' + c3 + '</td>'
        if cond == '3': grade += '<td><b>' + c3 + '</b></td>' else: grade += '<td>' + c3 + '</td>'
        grade += '</tr>'

        grade += '<tr>'
        grade += '<td>Grade 4</td>'
        if cond == '4': grade += '<td><b>' + c4 + '</b></td>' else: grade += '<td>' + c4 + '</td>'
        if cond == '4': grade += '<td><b>' + c4 + '</b></td>' else: grade += '<td>' + c4 + '</td>'
        grade += '</tr>'

        grade += '<tr>'
        grade += '<td>Grade 5</td>'
        if cond == '5': grade += '<td><b>' + c5 + '</b></td>' else: grade += '<td>' + c5 + '</td>'
        if cond == '5': grade += '<td><b>' + c5 + '</b></td>' else: grade += '<td>' + c5 + '</td>'
        grade += '</tr>'

        grade += '</table>'

    return grade


def lookup_condition(con_db):
    # options:  New, New other, Manufacturer refurbished, Seller refurbished, Used, For parts or not working
    
    condition = "Used"

    if con_db == "1":
        condition = "New"

    return condition


def lookup_category(cat_db):
    
    category = "1"

    if cat_db == "Av":
        category = "111"    

    return category



def rid_html(txt):

    return txt
    
    
    

def get_item_records_by_item(item_code):
    
    entries = frappe.db.sql("""select
        it.item_code, it.name, it.item_name, it.description, it.website_image, it.slideshow, it.accessories, it.condition, it.function_grade
        , bin.actual_qty
        , ip.price_list_rate
        
        from `tabItem` it
        
        left join `tabBin` bin
        on  bin.item_code = it.name
        
        left join `tabItem Price` ip
        on ip.item_code = it.name
        
        
        where it.name = '""" + item_code + """'
        """ , as_dict=1)

    
    return entries

    
def get_item_records_by_creation(creation_date):
    
    entries = frappe.db.sql("""select
        it.item_code, it.name, it.item_name, it.description, it.website_image, it.slideshow, it.accessories_extras, it.condition
        , it.function_grade, it.grade_details, it.tech_details
        , bin.actual_qty
        , ip.price_list_rate
        
        from `tabItem` it
        
        left join `tabBin` bin
        on  bin.item_code = it.name
        
        left join `tabItem Price` ip
        on ip.item_code = it.name
        
        where it.creation >= '""" + creation_date + """'
        """ , as_dict=1)
        

    return entries


def get_slideshow_records(parent):
    
    records = []
    if (parent!= None):
        records = frappe.db.sql("""select
        wsi.image 
        from `tabWebsite Slideshow Item` wsi
        
        where wsi.parent = '""" + parent + """'
        """ , as_dict=1)
    
    
    return records






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


    
