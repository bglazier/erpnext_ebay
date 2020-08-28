
# -*- coding: utf-8 -*-
# Copyright (c) 2015, Universal Resource Trading Limited and contributors
# For license information, please see license.txt

import os
from inspect import cleandoc
import shutil
import cgi
import urllib.request
import subprocess
from datetime import date, timedelta

import frappe
from frappe.model.document import Document

import xml.etree.ElementTree as ET
import requests

from jinja2 import Environment, PackageLoader
import jinja2
import pymysql


from ugscommon import get_unsubmitted_prec_qty
import ugssettings
from .ebay_active_listings import update_ebay_data

NO_IMAGES = True
USE_SERVER_IMAGES = True


#Save to public directory so one can download
garage_xml_path = (os.path.join(os.sep, frappe.utils.get_bench_path(), 'garagesale'))
site_files_path = (os.path.join(os.sep, frappe.utils.get_bench_path(), 'sites',
                   frappe.get_site_path(), 'public', 'files'))

images_url = 'https://shop.unigreenscheme.co.uk'
site_url = 'https://shop.unigreenscheme.co.uk'

footer = """<br><br>The price includes VAT and we can provide VAT invoices.\
            <br><br>Universities and colleges - purchase orders accepted - please contact us."""


def is_scotland(item_code):
    """Determine if an item code is a Scottish item by reference to
    stock locations (specifically, if the item is contained in the 'Scotland'
    stock location).
    TODO - this is broken for several obvious reasons
    """
    sl = frappe.db.sql("""
        SELECT sl.container FROM `tabStock Location` AS sl
            WHERE sl.item_code = %s
        """, (item_code,))

    if sl and sl[0][0] == 'Scotland':
        return True
    else:
        return False


def get_draft_sales(item_code):

    return frappe.db.sql("""
    SELECT IFNULL(SUM(qty), 0) AS qty
        FROM `tabSales Invoice Item` AS sii
    LEFT JOIN `tabSales Invoice` AS si
        ON si.name = sii.parent
    WHERE si.docstatus = 0
        AND sii.item_code = %s
    """, (item_code,))[0][0]


@frappe.whitelist()
def run_cron_create_xml():
    """
    # NOTE Should run sync ebay_ids before running anything else so database is up to date

    If is_auction then specify a startingBid which switches on auction mode
    """

    frappe.msgprint("Exporting all listings in QC Passed status")

    #Before doing anything sync the ebay_id to Erpnext
    update_ebay_data(multiple_error_sites=['UK'])

    design = "Pro: Classic"
    layout = "thumb gallery"
    #decline = 0.9
    #accept = 0.1
    duration = 10  # GTC = 1000
    handling_time = 1

    root = ET.Element("items")

    records = get_item_records_by_item_status()

    for r in records:
        item_code = r.name

        post_code = "NP4 0HZ"
        if is_scotland(item_code):
            post_code = "DG1 3PH"

        is_auction = False

        quantity = r.actual_qty + r.unsubmitted_prec_qty - get_draft_sales(item_code)

        # Don't run if quantity not matching stock locations qty
        # Items only come through if ebay_id is Null or blank - no need to exclude e.g Awaiting
        # Garagesale (see sql query)
        #if quantity > 0.0 and quantity == r.sum_sl: FUDGE THIS FOR THE MOMENT
        if quantity > 0.0 and r.sum_sl > 0.0:
            if r.sum_sl < quantity:
                quantity = r.sum_sl

            title = ""
            title += r.item_name
            category = lookup_category(r.item_group, r.item_group_ebay)

            # if an item_price use that otherwise try item.standard_rate (either case ifnull=0)
            if r.item_price == 0.0:
                ebay_price = r.price * ugssettings.VAT
            else:
                ebay_price = r.item_price * ugssettings.VAT

            #resize_images(item_code)
            #image = r.image
            ws_image = r.website_image
            ss_images_list = get_slideshow_records(r.slideshow)

            pounds, ounces = kg_to_imperial(r.net_weight)

            version = 0

            body = "<![CDATA[<br></br>"
            body += jtemplate(version, r.description, r.function_grade, r.grade_details,
                              r.condition, r.tech_details, r.delivery_type, r.accessories_extras,
                              r.power_cable_included, r.power_supply_included,
                              r.remote_control_included, r.case_included, r.warranty_period)

            body += footer
            body += """<br><br>sku: {}""".format(item_code)
            #body += """<br>approx (unit) weight: {}""".format(r.weight_per_unit)
            #body += """<br>approx l x w x h: {} x {} x {}""".format(r.length, r.width, r.height)
            body += "]]"

            doc = ET.SubElement(root, "item")

            ET.SubElement(doc, "bestOffer").text = "true"
            #ET.SubElement(doc, "bestOfferAutoAcceptPrice").text = str(price - (price * accept))
            #ET.SubElement(doc, "bestOfferAutoDeclinePrice").text = str(price - (price * decline))
            ET.SubElement(doc, "buyItNowPrice").text = str(ebay_price)
            ET.SubElement(doc, "category").text = category
            #ET.SubElement(doc, "category2").text =

            condition_desc, condition_id = lookup_condition(r.condition, r.function_grade)
            ET.SubElement(doc, "condition").text = str(condition_desc)
            ET.SubElement(doc, "conditionDescription").text = r.grade_details

            ET.SubElement(doc, "convertDescriptionToHTML").text = "false"
            ET.SubElement(doc, "convertMarkdownToHTML").text = "false"
            ET.SubElement(doc, "description").text = body
            ET.SubElement(doc, "design").text = design

            # Ensure that blank brands are set as unbranded
            if r.brand == '':
                brand = 'Unbranded'
            else:
                brand = frappe.db.escape(r.brand)

            try:
                st = """<customSpecific> <specificName>Brand</specificName> <specificValue>{}</specificValue></customSpecific>""".format(brand)
                brand_xml = ET.fromstring(st)
                doc.append(brand_xml)
            except Exception:
                print('Problem with this brand: ', brand)

            if r.delivery_type == 'Pallet':
                ET.SubElement(doc, "shippingProfile").text = 'B. Pallet Shipping'
            if r.delivery_type == 'Standard Parcel': 
                pounds, ounces = kg_to_imperial(29)
                ET.SubElement(doc, "shippingProfile").text = 'A. Standard Parcel'
            if r.delivery_type == 'Collection Only': 
                ET.SubElement(doc, "shippingProfile").text = 'Collection in person.'

            ET.SubElement(doc, "duration").text = str(duration)
            ET.SubElement(doc, "handlingTime").text = str(handling_time)

            if USE_SERVER_IMAGES:
                for ssi in ss_images_list:
                    print(ssi)
                    if ssi.image:  # and exists(images_url + ssi.image):
                        ET.SubElement(doc, "imageURL").text = images_url + ssi.image
                        '''''
                            # IF there is no slideshow then try the ws_image
                            if not ssi:
                                if r.website_image != 'NULL':
                                    ET.SubElement(doc, "imageURL").text = images_url + ws_image
                        '''

            ET.SubElement(doc, "layout").text = layout
            #ET.SubElement(doc, "lotSize").text = "1"
            if r.height:
                ET.SubElement(doc, "packageDepth").text = str(r.height)
            if r.length:
                ET.SubElement(doc, "packageLength").text = str(r.length)
            ET.SubElement(doc, "packageOunces").text = str(ounces)
            ET.SubElement(doc, "packagePounds").text = str(pounds)
            if r.width:
                ET.SubElement(doc, "packageWidth").text = str(r.width)
            #ET.SubElement(doc, "paymentInstructions").text = ""
            ET.SubElement(doc, "privateAuction").text = "false"
            ET.SubElement(doc, "quantity").text = str(quantity)

            if r.warranty_period == "45" or r.warranty_period == "None":
                ET.SubElement(doc, "returnPolicyDescription").text = "Buy with confidence. If you wish to return the item, for whatever reason, you may do so within 45 days."
            else:
                ET.SubElement(doc, "returnPolicyDescription").text = "".join([
                             """Buy with confidence. If you wish to return the item, """,
                             """for whatever reason, you may do so within 45 days. """,
                             """This item also includes our Limited Warranty """,
                             """(please see our terms and conditions for details)."""
                             ])
                # TODO This item also includes our " + r.warranty_period + " Day Limited Warranty 
                # (please see our terms and conditions for details)."

            ET.SubElement(doc, "returnsAccepted").text = "true"
            ET.SubElement(doc, "returnsWithinDays").text = "45"

            #ET.SubElement(doc, "reservePrice").text = ""
            #ET.SubElement(doc, "siteName").text = ""
            ET.SubElement(doc, "SKU").text = item_code
            if is_auction:
                ET.SubElement(doc, "startingBid").text = str(ebay_price)
            #ET.SubElement(doc, ****storCategory).text = ""
            #ET.SubElement(doc, "subTitle").text = sub_title
            ET.SubElement(doc, "title").text = title
            #ET.SubElement(doc, "variation").text = ""
            ET.SubElement(doc, "zipCode").text = post_code

            tree = ET.ElementTree(root)
            file_name = (os.path.join(os.sep, garage_xml_path, str(date.today()) + "_garageimportfile.xml"))
            # must create xml directory for this to work
            tree.write(file_name)

            # Update ebay_id to 'Awaiting Garagesale' marker
            frappe.db.set_value(
                'Item', item_code, 'ebay_id',
                ugssettings.AWAITING_GARAGESALE_STATUS)

    # Xml file created now download it (does not work properly)
    #download_xml(site_url + '/files/xml/' + str(date.today()) + "_garageimportfile.xml",
    #             str(date.today()) + "_garageimportfile.xml")

    frappe.msgprint("Export completed.")


def download_xml(url, file_name):
    """
    Saves a file to local machine
    """

    urllib.request.urlretrieve(url, os.path.join(os.path.expanduser("~"), 'Downloads', file_name))

    print(url)
    print(os.path.join(os.path.expanduser("~"), 'Downloads', file_name))


def render(tpl_path, context):
    """
    rende
    """

    path, filename = os.path.split(tpl_path)
    rendered = jinja2.Environment(
        loader=jinja2.FileSystemLoader(path or './'), autoescape=False
    ).get_template(filename).render(context)

    return rendered


def jtemplate(version, description, function_grade, grade_details, condition, tech_details,
              delivery_type, accessories_extras, power_cable_included, power_supply_included,
              remote_control_included, case_included, warranty_period):
    """
    jtemplate
    """

    if accessories_extras:
        ae = add_breaks(accessories_extras)
    else:
        ae = ''

    context = {
        'version': version,
        'description': description,
        'function_grade': function_grade,
        'grade_details': grade_details,
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

    result = render(os.path.join(os.sep, frappe.get_app_path('erpnext_ebay'),
                                 'item_garage_sale.html'), context)

    return result


def lookup_condition(con_db, func_db):
    """
    Given an erpNext condition grade
    returns condition string and condition_id (int)
    options:  New, New other, Manufacturer refurbished, Seller refurbished,
    Used, For parts or not working
    see below for more details
    """

    condition = "Used"
    condition_id = 3000

    if con_db == "0":
        condition = "Used"
    if con_db == "1":
        condition = "New"
        condition_id = 1000
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
        condition_id = 7000

    """Note: eBay's condition ids are:

        ID      Typical Name    Typical Definition
        1000    New
                    A brand-new, unused, unopened, unworn, undamaged item. Most categories support 
                    this condition (as long as condition is an applicable concept).
        1500    New other (see details)
                    A brand-new new, unused item with no signs of wear. Packaging may be missing 
                    or opened. The item may be a factory second or have defects.
        1750    New with defects
                    A brand-new, unused, and unworn item. The item may have cosmetic defects, 
                    and/or may contain mismarked tags (e.g., incorrect size tags from the 
                    manufacturer). Packaging may be missing or opened. The item may be a new 
                    factory second or irregular.
        2000    Manufacturer refurbished
                    An item in excellent condition that has been professionally restored to working
                    order by a manufacturer or manufacturer-approved vendor. 
                    The item may or may not be in the original packaging.
        2500    Seller refurbished
                    An item that has been restored to working order by the eBay seller or a third 
                    party who is not approved by the manufacturer. This means the seller indicates 
                    that the item is in full working order and is in excellent condition. The item 
                    may or may not be in original packaging.
        3000    Used
                    An item that has been used previously. The item may have some signs of cosmetic
                    wear, but is fully operational and functions as intended. This item may be a 
                    floor model or store return that has been used. Most categories support this 
                    condition (as long as condition is an applicable concept).
        4000    Very Good
                    An item that is used but still in very good condition. No obvious 
                    damage to the cover or jewel case. No missing or damaged pages or liner notes. 
                    The instructions (if applicable) are included in the box. May have very minimal 
                    identifying marks on the inside cover. Very minimal wear and tear.
        5000    Good
                    An item in used but good condition. May have minor external damage including 
                    scuffs, scratches, or cracks but no holes or tears. For books, liner notes, or 
                    instructions, the majority of pages have minimal damage or markings 
                    and no missing pages.
        6000    Acceptable
                    An item with obvious or significant wear, but still operational. For books, 
                    liner notes, or instructions, the item may have some damage to the cover but 
                    the integrity is still intact. Instructions and/or box may be missing. For 
                    books, possible writing in margins, etc., but no missing pages or anything 
                    that would compromise the legibility or understanding of the text.
        7000    For parts or not working
                    An item that does not function as intended and is not fully operational. 
                    This includes items that are defective in ways that render them difficult 
                    to use, items that require service or repair, or items missing essential 
                    components. Supported in categories where parts or non-working items are of 
                    interest to people who repair or collect related items.
        """

    return condition, condition_id


def lookup_category(cat_db, ebay_cat_db):
    """
    lookup_category
    """

    val = 0

    if cat_db:
        val = frappe.get_value("Item Group", str(cat_db), "ebay_category_code")

    if ebay_cat_db:
        val = frappe.get_value("Item Group eBay", str(ebay_cat_db), "ebay_category_id")

    return val


def get_item_records_by_item_status():
    """
    Gets all the QC Passed items that are not on eBay

    #having sum(sl.qty) > 0 and sum(sl.qty) = sum(bin.actual_qty) WILL NOT WORK WITH DRAFT PREC
    # Therefore See alternative method in main function using get_unsubmitted_prec

    Note: do not sum actual_qty as this will be multiplied by any occurence of 1+ locations.
    """

    sql2 = """
        select
        it.creation,
        it.item_code,
        it.name,
        it.item_name,
        it.is_auction,
        it.item_group,
        it.item_group_ebay,
        ifnull(it.brand, '') as brand,
        it.description,
        it.tech_details,
        it.image,
        it.website_image,
        it.slideshow,
        it.accessories_extras,
        it.power_cable_included,
        it.power_supply_included,
        it.remote_control_included,
        it.case_included,
        it.condition,
        it.function_grade,
        it.grade_details,
        it.warranty_period,
        ifnull(it.weight_per_unit,0.0) as weight_per_unit,
        ifnull(it.length, 0.0) as length,
        ifnull(it.width, 0.0) as width,
        ifnull(it.height,0.0) as height,

        it.delivery_type,
        ifnull(it.standard_rate,0.0) as price,
        ifnull(ip.price_list_rate,0.0) as item_price,
        (ifnull(bin.actual_qty, 0.0)) as actual_qty,
        it.item_status,
        sum(ifnull(sl.qty, 0.0)) as sum_sl,
        ifnull((
            select ifnull(sum(pri.received_qty), 0.0)
            from `tabPurchase Receipt Item` pri
            where pri.docstatus = 0
            and pri.docstatus = 0
            and pri.item_code = it.item_code
            group by pri.item_code
        ),0.0) as unsubmitted_prec_qty

        from `tabItem` it

        left join `tabBin` bin
        on  bin.item_code = it.name

        left join `tabItem Price` ip
        on ip.item_code = it.name

        left join `tabStock Location` sl
        on sl.item_code = it.item_code

        where 
        it.item_status = 'QC Passed'
        and (it.ebay_id is Null or it.ebay_id ='')

        and (actual_qty > 0 or 
        (
        select ifnull(sum(pri.received_qty), 0.0)
        from `tabPurchase Receipt Item` pri
        where pri.docstatus = 0
        and pri.docstatus = 0
        and pri.item_code = it.item_code
        group by pri.item_code
        ) >0)

        group by it.item_code
        order by it.item_code
    """

    #LIMIT to IP and ip.selling = 1

    entries = frappe.db.sql(sql2, as_dict=1)

    return entries


def get_slideshow_records(ss_name):
    """
    Returns slideshow records for an item
    """
    records = []

    if ss_name is not None:
        sql = """
            select
            wsi.image
            from `tabWebsite Slideshow Item` wsi

            where wsi.parent = '{}'
            order by wsi.idx
            """.format(ss_name)

        records = frappe.db.sql(sql, as_dict=1)

    return records


'''UTILITIES'''


def kg_to_imperial(kg):
    """
    Convert Kg to imperial
    TODO - fix exceptions
    """

    try:
        ounces = kg * 35.27396195
        pounds = kg * 2.2046226218
        ounces = ounces - (pounds * 12.0)
    except Exception:
        pounds = 0.0
        ounces = 0.0
    return pounds, ounces


def first_lower(s):
    """
    Changes first char in string to lowercase
    """

    if not s:
        return ""
    return s[0].lower() + s[1:]


def exists(path):
    """
    Check if path exists
    """

    #r = requests.head(path)
    #return r.status_code == requests.codes.ok
    return True


def add_breaks(non_html):
    """
    Replace linebreak with <li>
    """

    escaped = cgi.escape(non_html.rstrip()).replace("\n", "</li><li>")
    non_html = "<li>%s</li>" % escaped

    return non_html
