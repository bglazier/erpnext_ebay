# -*- coding: utf-8 -*-
# Copyright (c) 2015, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins

import frappe, os, shutil
from frappe.model.document import Document
from datetime import date, timedelta

import xml.etree.cElementTree as ET
import requests

from jinja2 import Environment, PackageLoader
import jinja2
import subprocess
import cgi

from ugscommon import get_unsubmitted_prec_qty
import ugssettings.py


IS_TESTING = True
NO_IMAGES = True
USE_SERVER_IMAGES = False


#Save to public directory so one can download
garage_xml_path = '/home/frappe/frappe-bench/sites/site1.local/public/files/xml/'
if(IS_TESTING): garage_xml_path = '/home/frappe/frappe-bench/sites/erpnext.vm/public/files/xml/'


site_files_path= '/home/frappe/frappe-bench/sites/site1.local/public/files/'
if(IS_TESTING): site_files_path= '/home/frappe/frappe-bench/sites/erpnext.vm/public/files/'

images_url = 'http://www.universalresourcetrading.com'



@frappe.whitelist()
def run_cron_create_xml():
    
    #added to apps/frappe/frappe/hooks.py:  @TODO CRON DOES NOT WORK
    frappe.msgprint("Exporting all listings in QC Passed status")
    export_to_garage_sale_xml()
    
    return


def change_status_to_garagesale(item_code):
    
    sql = """
    update `tabItem` it
    set it.ebay_id = AWAITING_GARAGESALE_STATUS
    where it.item_code = '%s'
    """%item_code
    
    
    frappe.db.sql(sql, auto_commit = True)






def export_to_garage_sale_xml():
    post_code = "NP4 0HZ"
    design = "Pro: Classic"
    layout = "thumb gallery"
    decline = 0.9
    accept = 0.1
    duration = 10  # GTC = 1000
    handling_time = 1
    
    write_to_undo_file("New file created on:" + str(date.today()) + "\n")
    
    root = ET.Element("items")
    
    
    
    # Should run sync ebay_ids before running anything else
    
    records = get_item_records_by_item_status()

    for r in records:
        
        title = ""
        
        
        title += r.item_name
        item_code = r.name
        category = lookup_category(r.item_group, r.item_group_ebay)
        
        price = r.price
        
        qty_unsubmit = get_unsubmitted_prec_qty(item_code)
        if not qty_unsubmit: qty_unsubmit = 0
        
        if r.actual_qty:
            quantity = r.actual_qty + qty_unsubmit
        else:
            quantity = qty_unsubmit
        
        if not IS_TESTING: resize_images(item_code)
        #image = r.image
        ws_image = r.website_image
        ss_images_list = get_slideshow_records(r.slideshow)
        
        
        pounds, ounces = kg_to_imperial(r.net_weight)
        
        version = 0
        
        body = "<![CDATA[<br></br>"
        body += jtemplate(version, r.description, r.function_grade, r.grade_details, r.condition, \
                r.tech_details, r.delivery_type, r.accessories_extras, \
                r.power_cable_included, r.power_supply_included, r.remote_control_included, \
                r.case_included, r.warranty_period)
        
        body += "<br><br>The price includes VAT and we can provide VAT invoices."
        body += "<br><br>Universities and colleges - purchase orders accepted - please contact us."
        body += "<br><br>sku: " + r.item_code
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
        
        #EXAMPLE <domesticShippingService serviceAdditionalFee="2.00" serviceFee="12.00">UPS Ground</domesticShippingService>
        dom_ship_free = ET.fromstring("""<domesticShippingService serviceAdditionalFee="0.00" serviceFee="0.00">Other Courier 3-5 days</domesticShippingService>""")
        dom_ship_pallet = ET.fromstring("""<domesticShippingService serviceAdditionalFee="0.00" serviceFee="60.00">Other Courier 3-5 days</domesticShippingService>""")
        dom_ship_collection = ET.fromstring("""<domesticShippingService serviceAdditionalFee="0.00" serviceFee="0.00">Collection in Person</domesticShippingService>""")
        dom_ship_24hour = ET.fromstring("""<domesticShippingService serviceAdditionalFee="0.00" serviceFee="24.00">Other 24 Hour Courier</domesticShippingService>""")
        
        # Make sure there is a domestic default
        doc.append(dom_ship_collection)
        
        if r.delivery_type == 'No GSP':
            doc.append(dom_ship_free)
            doc.append(dom_ship_24hour)
            # ALSO NEED TO DISABLE GSP MANUALLY !!!!!!
        
        
        if r.delivery_type == 'Pallet':
            doc.append(dom_ship_pallet)
        
        
        #if r.delivery_type == 'Collection Only':  No need for this as default is set
        
        if r.delivery_type == 'Standard Parcel':
            doc.append(dom_ship_free)
            doc.append(dom_ship_24hour)
        
        
        #int_ship = ET.SubElement(doc, "internationalShippingService").text = ""
        #int_ship.set("serviceAdditionalFee", "0")
        #int_ship.set("serviceFee","0")
        
        
        
        ET.SubElement(doc, "duration").text = str(duration)
        ET.SubElement(doc, "handlingTime").text = str(handling_time)
        
        if USE_SERVER_IMAGES:
            for ssi in ss_images_list:
                if exists(images_url + ssi.image):
                    if ssi.image:
                        if URL_IMAGES:
                            ET.SubElement(doc, "imageURL").text = images_url + ssi.image
                        
                        else:
                            throw('Problem with image' + ssi.image)
                        
                        # IF there is no slideshow then try the ws_image
                        if(not ssi):
                            if (r.website_image != 'NULL'):
                                ET.SubElement(doc, "imageURL").text = images_url + ws_image



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
        
        if r.warranty_period == "45" or r.warranty_period == "None":
            ET.SubElement(doc, "returnPolicyDescription").text = "Buy with confidence. If you wish to return the item, for whatever reason, you may do so within 45 days."
        else:
            ET.SubElement(doc, "returnPolicyDescription").text = "Buy with confidence. If you wish to return the item, for whatever reason, you may do so within 45 days. \
            This item also includes our Limited Warranty (please see our terms and conditions for details)."
            #This item also includes our " + r.warranty_period + " Day Limited Warranty (please see our terms and conditions for details)."
        
        
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
        tree.write(garage_xml_path + str(date.today()) + "_garageimportfile.xml")
        
        #if r.item_status== 'Pending eBay':
        #    update_item_status('Listed eBay', item_code)
        #if r.item_status== 'Pending eBay But Do Not Ship':
        #    update_item_status('Listed eBay But Do Not Ship', item_code)
                
        change_status_to_garagesale(item_code)
        
        write_to_undo_file("""update `tabItem` it set it.ebay_id = '' where it.item_code = '""" + item_code + """';""")
    
    return

    


def render(tpl_path, context):
    path, filename = os.path.split(tpl_path)
    rendered = jinja2.Environment(
        loader=jinja2.FileSystemLoader(path or './'), autoescape=False
    ).get_template(filename).render(context)
    
    return rendered
    




def jtemplate(version, description, function_grade, grade_details, condition, tech_details, delivery_type, accessories_extras, \
power_cable_included, power_supply_included, remote_control_included, case_included, warranty_period):
        
    
    if accessories_extras:
        ae = add_breaks(accessories_extras)
    else:
        ae = ''
    
    try:
        context = {
            'version': version,
            'description': description,
            'function_grade' : function_grade,
            'grade_details' : grade_details,
            'condition': condition,
            'tech_details': tech_details,
            'delivery_type': delivery_type,
            'accessories_extras': ae,
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









def lookup_condition(con_db, func_db):
    # options:  New, New other, Manufacturer refurbished, Seller refurbished, Used, For parts or not working
    
    condition = "Used"
    
    if con_db == "0":
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


def lookup_category(cat_db, ebay_cat_db):
    
    val = 0
    
    if cat_db:
        val = frappe.get_value("Item Group", str(cat_db), "ebay_category_code")
    
    if ebay_cat_db:
        val = frappe.get_value("Item Group eBay", str(ebay_cat_db), "ebay_category_id")
    
    
    return val





def get_item_records_by_item_status():
    
    sql = """select
        it.creation
        , it.item_code, it.name, it.item_name, it.item_group, it.item_group_ebay
        , it.brand, it.description, it.tech_details
        , it.image, it.website_image, it.slideshow
        , it.accessories_extras, it.power_cable_included, it.power_supply_included, it.remote_control_included, it.case_included
        , it.condition, it.function_grade, it.grade_details
        , it.warranty_period
        , it.net_weight, it.length, it.width, it.height
        , it.standard_rate as price
        , it.delivery_type
        , bin.actual_qty
        , it.item_status
        
        from `tabItem` it
        
        left join `tabBin` bin
        on  bin.item_code = it.name
        
        left join `tabItem Price` ip
        on ip.item_code = it.name
        
        where it.item_status = 'QC Passed'
        and (it.ebay_id is Null or it.ebay_id ='')
        and bin.actual_qty > 0
    """
        
    entries = frappe.db.sql(sql, as_dict=1)
    
    
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

def add_breaks(non_html):
    
    escaped = cgi.escape(non_html.rstrip()).replace("\n", "</li><li>")
    non_html = "<li>%s</li>" % escaped
    
    return non_html
        

def resize_images(item_code):
    
    subprocess.call(['mogrify', '-resize', '1024x768', item_code + '*.jpg'])



def write_to_undo_file(txt):
    
    with open("/home/frappe/undo_status_change.sql", "a") as myfile:
        myfile.write(txt)


