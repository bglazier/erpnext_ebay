# -*- coding: utf-8 -*-
# Copyright (c) 2015, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, os, shutil #, nltk   
from frappe.model.document import Document
from datetime import date, timedelta

import xml.etree.cElementTree as ET
import requests
#import mechanize

from jinja2 import Environment, PackageLoader
import jinja2


IS_TESTING = False
NO_IMAGES = True


#Save to public directory so one can download
garage_xml_path = '/home/frappe/frappe-bench/sites/site1.local/public/files/xml/'
if(IS_TESTING): garage_xml_path = '/home/frappe/frappe-bench/sites/erpnext.vm/public/files/xml/'


site_files_path= '/home/frappe/frappe-bench/sites/site1.local/public/files/'
if(IS_TESTING): site_files_path= '/home/frappe/frappe-bench/sites/erpnext.vm/public/files/'


images_url = 'http://www.universalresourcetrading.com'



def render(tpl_path, context):
    path, filename = os.path.split(tpl_path)
    rendered = jinja2.Environment(
        loader=jinja2.FileSystemLoader(path or './'), autoescape=False
    ).get_template(filename).render(context)
    
    return rendered
    
    
    
    
    

def jtemplate(description, function_grade, grade_details, condition, tech_details, delivery_type, accessories_extras, power_cable_included, power_supply_included, remote_control_included, case_included, warranty_period):


    try:
        context = {
            'description': description,
            'function_grade' : function_grade,
            'grade_details' : grade_details, 
            'condition': condition, 
            'tech_details': tech_details, 
            'delivery_type': delivery_type, 
            'accessories_extras': accessories_extras, 
            'power_cable_included': power_cable_included, 
            'power_supply_included': power_supply_included,
            'remote_control_included': remote_control_included, 
            'case_included': case_included, 
            'warranty_period': warranty_period
        }
        
        result = render('/home/frappe/frappe-bench/apps/erpnext_ebay/erpnext_ebay/item_garage_sale.html', context)
        
    except:
        raise
        result = ""
        
        

    return (result)
    
    

    


@frappe.whitelist()
def run_cron_create_xml(garagesale_export_date):
    
    #added to apps/frappe/frappe/hooks.py:  @TODO CRON DOES NOT WORK
    frappe.msgprint("Exporting all listings created on/after: " + garagesale_export_date)
    
    if garagesale_export_date =="": 
        today = date.today()
        export_date = today.isoformat()
    else:
        export_date = garagesale_export_date
    
    export_to_garage_sale_xml(export_date)
    
    
    return




def export_to_garage_sale_xml(creation_date):
    post_code = "NP4 0HZ"
    design = "Pro: Classic"
    layout = "thumb gallery"
    decline = 0.9
    accept = 0.1
    duration = 1000  # GTC = 1000
    handling_time = 1

    
    root = ET.Element("items")

    records = get_item_records_by_creation(creation_date)

    for r in records:
        title = ""
        
        #if r.brand: title = r.brand + " "
        #else: title = ""
        
        
        
        title += r.item_name
        item_code = r.name
        category = lookup_category(r.item_group)
        
        price = r.price
        quantity = r.actual_qty
        
        #image = r.image
        ws_image = r.website_image
        ss_images_list = get_slideshow_records(r.slideshow)
                
        
        pounds, ounces = kg_to_imperial(r.net_weight)
        
        
        body = "<![CDATA[<br></br>"
        body += jtemplate(r.description, r.function_grade, r.grade_details, r.condition, r.tech_details, r.delivery_type, r.accessories_extras, r.power_cable_included, \
        r.power_supply_included, r.remote_control_included, r.case_included, r.warranty_period)
        
        body += "<br>sku: " + r.item_code
        body += "]]"
        
        
        if(not price):
            price = 0.0  
            #TODO Probably better writing this to a LOG file and not exporting it?
        
        #quantity = 1
        if(not quantity):
            quantity = 1
            # or break ??        
        
        doc = ET.SubElement(root, "item")

        ET.SubElement(doc, "bestOffer").text = "true"
        #ET.SubElement(doc, "bestOfferAutoAcceptPrice").text = str(price - (price * accept))
        #ET.SubElement(doc, "bestOfferAutoDeclinePrice").text = str(price - (price * decline))         
        ET.SubElement(doc, "buyItNowPrice").text = str(price)
        ET.SubElement(doc, "category").text = category 
        #ET.SubElement(doc, "category2").text =
        ET.SubElement(doc, "condition").text = lookup_condition(r.condition, r.function_grade)
        ET.SubElement(doc, "conditionDescription").text = r.grade_details
        ET.SubElement(doc, "convertDescriptionToHTML").text = "false"
        ET.SubElement(doc, "convertMarkdownToHTML").text = "false"
        ET.SubElement(doc, "description").text = body
        ET.SubElement(doc, "design").text = design
        
        
        if r.delivery_type == 'No GSP':
            print ("No GSP currently no way to handle this")
            
        if r.delivery_type == 'Pallet':
            print ('Pallet')
            
        if r.delivery)_type == 'Collection Only':
            print ('Collection Only')
            dom_ship = ET.SubElement(doc, "domesticShippingService").text = "Collection in Person"
            dom_ship.set("serviceAdditionalFee", "0")
            dom_ship.set("serviceFee", "0")

        if r.delivery)_type == 'Standard Parcel':
            dom_ship = ET.SubElement(doc, "domesticShippingService").text = "Other Courier 3-5 days"
            dom_ship.set("serviceAdditionalFee", "0")
            dom_ship.set("serviceFee", "0")
            dom_ship = ET.SubElement(doc, "domesticShippingService").text = "Collection in Person"
            dom_ship.set("serviceAdditionalFee", "0")
            dom_ship.set("serviceFee", "0")
            dom_ship = ET.SubElement(doc, "domesticShippingService").text = "Other 24 Hour Courier"
            dom_ship.set("serviceAdditionalFee", "12.95")
            dom_ship.set("serviceFee", "0")
            
            
        #dom_ship = ET.SubElement(doc, "domesticShippingService").text =
        #dom_ship.set("serviceAdditionalFee", "0")
        #dom_ship.set("serviceFee", "0")
        
        #int_ship = ET.SubElement(doc, "internationalShippingService").text = ""
        #int_ship.set("serviceAdditionalFee", "0")
        #int_ship.set("serviceFee","0")
        
        
        
        ET.SubElement(doc, "duration").text = str(duration)
        ET.SubElement(doc, "handlingTime").text = str(handling_time)          


        #for ssi in ss_images_list:
            #if exists(images_url + ssi.image):
            #if ssi.image: 
                #if URL_IMAGES: 
                    #ET.SubElement(doc, "imageURL").text = images_url + ssi.image
                    
            #else:
            #    throw('Problem with image' + ssi.image)

        # IF there is no slideshow then try the ws_image
        #if(!ssi):
        #    if (r.website_image != 'NULL'):
        #        ET.SubElement(doc, "imageURL").text = images_url + ws_image
        


        ET.SubElement(doc, "layout").text = layout
        #ET.SubElement(doc, "lotSize").text = "1"
        if r.height: ET.SubElement(doc, "packageDepth").text = str(r.height)
        if r.length: ET.SubElement(doc, "packageLength").text = str(r.length)
        ET.SubElement(doc, "packageOunces").text = str(ounces)
        ET.SubElement(doc, "packagePounds").text = str(pounds)
        if r.width: ET.SubElement(doc, "packageWidth").text = str(r.width)
        #ET.SubElement(doc, "paymentInstructions").text = ""
        ET.SubElement(doc, "privateAuction").text = "false"
        ET.SubElement(doc, "quantity").text = str(quantity)
        
        if r.warranty_period == "45" or warranty_period == "None":
            ET.SubElement(doc, "returnPolicyDescription").text = "Buy with confidence. If you wish to return the item, for whatever reason, you may do so within 45 days."
        else
            ET.SubElement(doc, "returnPolicyDescription").text = "Buy with confidence. If you wish to return the item, for whatever reason, you may do so within 45 days. \
            This item also includes our " + r.warranty_period + " Day Limited Warranty (please see our terms and conditions for details)."
        
        
        ET.SubElement(doc, "returnsAccepted").text = "true"
        ET.SubElement(doc, "returnsWithinDays").text = "45"
        
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
        tree.write(garage_xml_path + creation_date + "_garageimportfile.xml")

        

    return




def lookup_condition(con_db, func_db):
    # options:  New, New other, Manufacturer refurbished, Seller refurbished, Used, For parts or not working
    
    condition = "Used"

    if con_db == "1":
        condition = "Used"
    if con_db == "1":
        condition = "New"
    if con_db == "2":
        condition = "Used"
    if con_db == "3":
        condition = "Used"
    if con_db == "4":
        condition = "Used"
    if con_db == "5":
        condition = "Used"
        
    if func_db == "5":
        condition = "For parts or not working"

    return condition


def lookup_category(cat_db):
    
    val = 0

    if cat_db:
        val = frappe.get_value("Item Group", str(cat_db), "ebay_category_code")


    return val



def rid_html(txt):

    return txt
    
    
    

def get_item_records_by_item(item_code):
    
    entries = frappe.db.sql("""select

        where it.name = '""" + item_code + """'
        """ , as_dict=1)

    
    return entries

    
def get_item_records_by_creation(creation_date):
    
    entries = frappe.db.sql("""select
        it.item_code, it.name, it.item_name, it.item_group
        , it.brand, it.description, it.tech_details
        , it.image, it.website_image, it.slideshow
        , it.accessories_extras, it.power_cable_included, it.power_supply_included, it.remote_control_included, it.case_included
        , it.condition, it.function_grade, it.grade_details
        , it.warranty_period
        , it.net_weight, it.length, it.width, it.height
        , bin.actual_qty
        , it.standard_rate as price
        
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
    
def kg_to_imperial(kg):
    
    ounces = kg * 35.27396195
    pounds = kg * 2.2046226218
    ounces = ounces - (pounds * 12.0)
    
    return pounds, ounces


def first_lower(s):
    if not s:
        return ""
    return s[0].lower() + s[1:]


def exists(path):
    r = requests.head(path)
    return r.status_code == requests.codes.ok


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


    

#<div style="text-align: center; background: url(http://www.iwascoding.de/GarageSale/defaultFooterBG.png) no-repeat center center scroll; clear: both; margin-top: 15px; -webkit-filter: blur(0px);" id="gs-garageSaleBadge"><a href="http://www.iwascoding.com/GarageSale/" target="_blank"><img src="http://www.iwascoding.com/GarageSale/MadeWithGarageSale.png" border="0" alt="Created with GarageSale" width="88" height="33" title="Created with GarageSale - the most advanced listing tool for Mac OS X."></a></div>
