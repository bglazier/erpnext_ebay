from __future__ import unicode_literals
from __future__ import print_function
import __builtin__ as builtins



import frappe
from frappe import msgprint,_
from frappe.utils import cstr




def better_print(*args, **kwargs):
    with open ("/home/frappe/frappe-bench/apps/erpnext_ebay/file-report-kpi", "a") as f:
        builtins.print (file=f, *args, **kwargs)


print = better_print



@frappe.whitelist()
def run():
    
    kpi_report()
    project_checks()
    account_checks()
    stock_checks()
    price_checks()


# UTILITY FUNCTIONS
def print_entries(entries):
    
    #for record in entries:
    #    print (entries):
    
    return
    


#TODO report only paid sales invoices?!!


# EXAMPLE use of db.get.value with multiple returns
def get_invoice_details(self, invoice_no):
        """ Pull details from invoices for referrence """
        
        inv = frappe.db.get_value("Sales Invoice", invoice_no,
            ["posting_date", "territory", "net_total", "grand_total"], as_dict=True)
        return {
            'invoice_date' : inv.posting_date,
            'territory'    : inv.territory,
            'net_total'    : inv.net_total,
            'grand_total'  : inv.grand_total
        }




    

def calc_shipping(weight, length, width, height):
    
    shipper = 'Hermes'
    
    
    if weight > 3.0: shipper = 'Parcelforce'
    if weight > 30: shipper = 'UPS'
    
    if length > 50: shipper = 'UPS'
    
    return shipper



def create_parcelforce_import():
    
    express48 = 'PF48'
    express24 = 'PF24'
    #csv = filler, business_name, address_line_1, address_line_2, address_line_3, post_town, postcode, recipient_phone, ref



def kpi_report():
    
    sql = """select s.supplier where s.type = 'University (UK)' and s.parent = 'NULL'
    """
    sql = """select s.supplier where s.type = 'University (UK) and s.parent = 'NULL' and s.creation_date > '2016-11-01'
    """
    
    print ("KPI REPORT")
    
    print ("Sales KPI")
    
    print ("Num of universitites")
    print ("Num of departments")
    print ("Num signed this month")
    print ("New leads")
    
    

    print ("Financial KPI")
    
    print ("Sales")
    print ("Rebates")
    print ("Cash")
    print ("Cashflow forecast")
    
    
    print ("Operational KPI")
    print ("Value of items listed")
    print ("Days sales in stock")
    print ("Processing speed")
    
    print ("Other")
    print ("Profitability per university")

    

def project_checks():
    
    conditions = ''
    filters = ''

    
    
    
    # NOT AFFECTING PROJ REPORTS
    
    # A no purchases other than universities should be COGS
    print ("University Purchase Invoices (pi) should not be COGS. Shows not conforming.")
    
    sql = """select pi.name, pi.supplier, s.supplier_type, pi.against_expense_account, pii.name as `pii_name`, pii.expense_account
           	from `tabPurchase Invoice` pi
            left join `tabSupplier` s
            on s.name = pi.supplier
            left join `tabPurchase Invoice Item` pii
            on pii.parent = pi.name
            where s.supplier_type <> 'University (UK)' and
            (pi.against_expense_account = 'Cost of Goods Sold - URTL'
            or pii.expense_account = 'Cost of Goods Sold - URTL'
            )"""
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
        
    for r in records:
        print ("Errors can only be fixed manually. Run the following:")
        fix = """update `tabPurchase Invoice Item` pii set pii.expense_account = 'XX' where pii.name = '""" + r.pii_name + """'"""
        print (fix)
        fix = """update `tabPurchase Invoice` pi set pi.against_account = 'XX' where pi.name = '""" + r.name + """'"""
        print (fix)
            
    
    # B Purchase Invoice (Items) of supplier type University, should only be cost of goods sold
    print ("University Purchase Invoice Items (pii) should be COGS. Query shows non conforming.")
    
    sql = """select pii.name, pii.parent, pii.expense_account
            from `tabPurchase Invoice Item` pii
            inner join `tabPurchase Invoice` pi
            on pi.name = pii.parent
            inner join `tabSupplier` s
            on s.name = pi.supplier
            where s.supplier_type = 'University (UK)'
            and pii.expense_account <> 'Cost of Goods Sold - URTL'
            """
    
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
        
    # B FIX: can be automatically e.g.run weekly
    sql = """update `tabPurchase Invoice Item` pii
    inner join `tabPurchase Invoice` pi
    on pi.name = pii.parent
    inner join `tabSupplier` s
    on s.name = pi.supplier
    set pii.expense_account = 'Cost of Goods Sold - URTL'
    where s.supplier_type = 'University (UK)'
    """
    print (Fixing these errors now...)
    records = frappe.db.sql(fix, as dict=1)
    
    
    # C (B can be replaced by this) Purchase Invoices  of supplier type University, should only be cost of goods sold
    print ("Purchase Incoices of type Univerisity should be COGS. Query shows non conforming.")
    sql = """select pi.name, pi.supplier, s.supplier_type, pi.against_expense_account, pii.name, pii.expense_account
           	from `tabPurchase Invoice` pi
            left join `tabSupplier` s
            on s.name = pi.supplier
            left join `tabPurchase Invoice Item` pii
            on pii.parent = pi.name
            where s.supplier_type = 'University (UK)' and
            (pi.against_expense_account <> 'Cost of Goods Sold - URTL'
            or pii.expense_account <> 'Cost of Goods Sold - URTL'
            )
        """
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
        
    # C FIX: can be run automatically, e.g . weekly
    sql = """update `tabPurchase Invoice` pi
    inner join `tabSupplier` s
    on s.name = pi.supplier
    set pi.against_expense_account = 'Cost of Goods Sold - URTL'
    where s.supplier_type = 'University (UK)'
    """
    print ("Auto fixing these errors now...")
    records = frappe.db.sql(sql, as dict=1)
    
    
    
    # F Projects with no purchase reciept
    print ("Projects with no PREC")
    sql = """select prj.name, pr.name, pr.project, pr.supplier
        from `tabProject` prj
        left join `tabPurchase Receipt` pr
        on pr.project = prj.name
        where pr.name is NULL
        """
    
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
        
    print ("Fix must be entered manually. Create a PREC for these projects")
    
    # G Purchase receipts with no project
    print ("PREC's with no PROJ")
    sql = """select pr.name, pr.project, s.name as `s_name`
        from `tabPurchase Receipt` pr
        inner join `tabSupplier` s
        on s.name = pr.supplier
        where pr.project is NULL and s.supplier_type = 'University (UK)'
        """
    
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
    
    #fix
    print ("Run the following SQL", fix)
    for r in records:
        fix = """update `tabProject` pr set pr.project = 'XXX' where pr.name = '""" + r.name + """';"""
        print fix
    





        
    #H Purchase receipts items with no project
    print ("PREC ITEMS with no project")
    
    sql = """select pri.name, pri.project, s.name s_name, pr.project, pr.name
        from `tabPurchase Receipt Item` pri
        inner join `tabPurchase Receipt` pr
        on pr.name = pri.parent
        inner join `tabSupplier` s
        on s.name = pr.supplier
        where pri.project is NULL and s.supplier_type = 'University (UK)'
        """
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
        
    #H FIX:
    print ("FIXING")
    fix = """update `tabPurchase Receipt Item` pri
        inner join `tabPurchase Receipt` pr
        on pr.name = pri.parent
        set pri.project = pr.project
        where pri.project is NULL and pr.project is not NULL
        """
    records = frappe.db.sql(fix, as dict=1)
    
    
    # I Univeristy Purchase invoice Items with no project (Purchase Invoice has no project field so we cannot show this!)
    # we are adding prec code to get an idea what project the item relates
    #TODO may need to do this exercise for Purchase Order Items
    
    print ("University Purchase invoice Items with no project")
    sql = """select pii.name `pii name`, pii.parent, pi.supplier, pii.project, pii.item_code, pri.parent
        from `tabPurchase Invoice Item` pii
        inner join `tabPurchase Invoice` pi
        on pi.name = pii.parent
        inner join `tabSupplier` s
        on s.name = pi.supplier
        left join `tabPurchase Receipt Item` pri
        on pri.item_code = pii.item_code
        where s.supplier_type = 'University (UK)' and pri.docstatus = 1
        """
    
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    # I FIX: TODO need to backtrack to see what projects should be set

    
    # O ITEM default supplier != prec item supplier
    print ("ITEM default supplier != prec item supplier")
    sql = """select it.name, it.default_supplier, pri.name, pr.name, pr.supplier
            from `tabItem` it
            left join `tabPurchase Receipt Item` pri
            on pri.item_code = it.name
            left join `tabPurchase Receipt` pr
            on pr.name = pri.parent
            where pr.supplier <> it.default_supplier
        """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)

    #O FIX
    sql = """update `tabItem` it
    set it.default_supplier = ''
    where it.item_code = ''
    """


    
    # S Items on multiple purchase receipts
    print ("Items on multiple purchase receipts")
    
    sql = """select it.item_code, it.item_name, pr.name
        from `tabItem` it
        left join `tabPurchase Receipt Item` pri
        on  pri.item_code = it.item_code
        left join `tabPurchase Receipt` pr
        on pr.name = pri.parent
        group by pr.name
        """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)



    
    
    #J Unclosed projects where all stock sold
    print ("Unclosed projects where all stock is sold")
    sql = """select prj.name
        from `tabProject` prj
        where (select * from `tabPurchase Receipt Item` pri
                    inner join `tabPurchase Receipt` pr
           	        on pr.name = pri.parent
                    inner join `tabBin` bin
                    on  bin.item_code = pri.item_code)
        """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    
    # Q Project has no supplier, no start date.
    print ("Project has no supplier or start date")
    
    sql = """select prj.name
        from `tabProject` prj
        where prj.start_date is NULL
        """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
        
    # set project start dates to prec dates
    sql = """update `tabProject` prj set prj.start_date = 'PREC_POSTING_DATE' where prj.start_date =
    """
        




def account_checks():
    
    # M Van Hire and fuel with no project set
    print ("Attributable costs where no project set")
    
    sql = """select pi.posting_date, pii.name `pii_name`, pii.parent `Prec`, pi.supplier, pii.project, pii.expense_account
        from `tabPurchase Invoice Item` pii
        left join `tabPurchase Invoice` pi
        on pi.name = pii.parent
        where (pii.expense_account like '%Fuel%'
        or pii.expense_account like '%Hire%'
        or pii.expense_account like '%Collections%'
        or pii.expense_account like '%Subsistence%'
        ) and pii.project is NULL
        """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print("You need to run the following SQL:")
        sql = """update `tabPurchase Invoice Item` pii
        set pii.project = 'XX'
        where pii.name = '""" + r.ppi_name + """'
        """
        print(sql)
    
    # K Expenses with no payment entries
    print ("Expenses with no payment entries")
    
    sql = """select ec.name, ec.employee_name, ec.project
           	from `tabExpense Claim` ec
            where ec.total_amount_reimbursed = 0.0 and ec.docstatus = 1
        """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    
    
    
    # L Expense claim with no project set
    print ("Expense claim with no project set.")
    
    sql = """select ec.name, ec.project
           	from `tabExpense Claim` ec
            where ec.project is NULL or ec.project = ''
        """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    
    
    
    # Activities without a cost

    
    
    # V Null mode_of_payment
    
    sql = """select si.name
       	from `tabSales Invoice` si
        where si.mode_of_payment is NULL
        """
    print ("SI with Null mode of payment. Should not be Null")
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
        
    print ("Fix:")
    for r in records:
        #V FIX
        fix = """update `tabSales Invoice` si set mode_of_payment = 'Paypal' where si.name = '""" + r.name """"'"""
        print (fix)
        
        
    # N Purchase invoice items with a project not NULL but are expense_accounts not likely to have projects set
    sql = """select pii.name `pii_name`, pii.parent `Prec`, pi.supplier, pii.project `pii project`, pii.expense_account `pii expense account`
        from `tabPurchase Invoice Item` pii
        inner join `tabPurchase Invoice` pi
        on pi.name = pii.parent
        where pii.project <> '' and
        (pii.expense_account like 'Accountancy - URTL'
        or pii.expense_account like '%Bank%'
        or pii.expense_account like '%Commission%'
        or pii.expense_account like 'Consultancy - URTL'
        or pii.expense_account like 'Depreciation - URTL'
        or pii.expense_account like 'Entertainment - URTL'
        or pii.expense_account like 'Insurance - URTL'
        or pii.expense_account like 'Internet - URTL'
        or pii.expense_account like 'Legal - URTL'
        or pii.expense_account like 'Marketing - URTL'
        or pii.expense_account like '%Miscellaneous%'
        or pii.expense_account like 'Insurance - URTL'
        or pii.expense_account like 'Rent - URTL'
        or pii.expense_account like '%Utility%'
        or pii.expense_account like '%Print%'
        or pii.expense_account like '%Repairs%'
        or pii.expense_account like '%Round%'
        or pii.expense_account like 'Software - URTL'
        or pii.expense_account like 'Subscriptions - URTL'
        or pii.expense_account like 'Telephone - URTL'
        or pii.expense_account like '%Directors%'
        or pii.expense_account like '%Employee%'
        or pii.expense_account like '%Salaries%'
        or pii.expense_account like '%Subcontractors%'
        )
        """
        
    print ("General Expense accounts e.g. Internet with projects. Should be NULL.")
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
        print ("FIXING NOW...")
        fix = """update `tabPurchase Invoice Item` pii
        set pii.project = NULL
        where pii.name = '""" + r.ppi_name + """'
        """
        frappe.db.sql(fix, as dict=1)
        
    

def stock_checks():
    
    
    # P Stock where received and sold is not equal to actual stock
    
    
    
    # R Minus stock
    
    sql = """select it.item_code, it.item_name
        from `tabItem` it
        inner join `tabBin` bin
        on  bin.item_code = it.item_code
        where bin.actual_qty < 0
        """
    
    print ("Negative Stock")
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    print ("Manual Fix: Determine transactions that caused stock changes")
    
    # T Stock with no dimensions
    sql = """select it.item_code
        from `tabItem` it
        where it.length <= 0.0
        or it.width <= 0.0
        or it.height <= 0.0
    """
    
    print ("Stock with no dimensions")
    sql = """select it.item_code from `tabItem` where it.length <= 0 or it.width <=0 or it.height <=0 """
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    print ("Manual fix:")
    for r in records:
        fix = """update `tabItem` it set it.length = 'XX', it.width = 'XX', it.height = 'X' where it.item_code = '""" + r.item_code + '"""
        print (fix)
    
    
    # T Stock with no weight
    sql = """select it.item_code, it.net_weight
        from `tabItem` it
        where it.net_weight <= 0.0
        """
    print ("Qty > 0 Stock with no weight")
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    print ("Manual fix:")
    for r in records:
        fix = """update `tabItem` set net_weight = 'XX' where it.item_code = '""" + r.item_code + '"""
        print (fix)
    
    # W Stock where eBay Qty not equal to Stock Qty
    
    
    # remove items from website when stock is 0
    print ("Items with no website images")
    sql = "select it.qty, it.image, it.website_image, it.thumbnail, it.show_in_website from `tabItem` it;"
    
    records = frappe.db.sql(dsql, as dict=1)
    
    for r in records:
        print (r)
    
    print ("Removing zero stock items from website")
    sql = "update `tabItem` it set it.show_in_website = 0 where it.qty <= 0"
    
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)





def price_checks():
    
    # U Stock with price = 0.0
    sql = """select it.item_code, pri.base_price_list_rate
       	from `tabPurchase Receipt Item` pri
        inner join `tabPurchase Receipt` pr
       	on pr.name = pri.parent
       	inner join `tabItem` it
        on  it.item_code = pri.item_code
        where pri.base_price_list_rate <= 0.0  #TODO check this is the correct price
        """
    print ("Stock with price = 0 and qty > 0")
    records = frappe.db.sql(dsql, as dict=1)
    for r in records:
        print (r)
    print ("Manual Fix")
    for r in records:
        fix = r.item_code
        print (fix)





        


def fixes():
    
    # Change project of a timesheet
    sql = """select tsd.name
    from `tabTimesheet Detail` tsd
    inner join `tabTimesheet` ts
    on ts.name = tsd.parent
    where tsd.project like '%05%'
        FIX
        update `tabTimesheet Detail` tsd
        set tsd.project = '40'
        where tsd.name = '8a105bfd0d'
    """
    
    
    
    sql = """update `tabPurchase Invoice Items` pii
    set pii.project = 'XXX'
    where pii.project is NULL
    """
    



    
    #T FIX
    #make these default fields
    


def kanban():
    
    sql = """select prjt.parent, prjt.name, prjt.title, prjt.status
   	from `tabProject Task` prjt
    """
    #% conditions, filters, as_dict=1)
    
    return

            

# OTHER REPORTING
# OTHER REPORTING
# OTHER REPORTING
# OTHER REPORTING

def project_reports():
    
    
    print ("List of all projects")
    # D List of all projects
    sql = """select pr.name, pr.project, s.name
        from `tabPurchase Receipt` pr
        join `tabSupplier` s
        on s.name = pr.supplier
        where pr.docstatus=1 and s.supplier_type = 'University (UK)';
        """
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
    
    print ("All projects and PREC")
    #E All projects and linked prec's
    sql = """select prj.name, pr.name, pr.project, pr.supplier
        from `tabProject` prj
        left join `tabPurchase Receipt` pr
        on pr.project = prj.name
        """
    records = frappe.db.sql(sql, as dict=1)
    for r in records:
        print (r)
    
    
    



def other():
    #Sales by Country
    sql = """select ad.country, sum(sii.net_amount)
        from
        `tabSales Invoice Item` sii
        
        inner join `tabSales Invoice` si
        on si.name = sii.parent
        
        inner join `tabCustomer` cu
        on cu.name = si.customer
        
        left join `tabAddress` ad
        on ad.customer = cu.name
        
        group by ad.country;
    """

    
    #Projects By University, and quantities recieved
    
    sql = """select proj.name, proj.project_type, pr.supplier, s.parent, sum(pri.received_qty)
    from `tabPurchase Receipt` pr
        
        left join `tabProject` proj
        on proj.name = pr.project
	    
	    inner join `tabSupplier` s
	    on s.name = pr.supplier
	    
	    left join `tabPurchase Receipt Item` pri
	    on pri.parent = pr.name
        where pr.docstatus < 2
        group by s.parent;
    """




def stock_analysis():
    
    print ("STOCK ANALYSIS")
    
    # Stock older than X months
    print ("Stock older than date: ")
    sql = """select pr.posting_date, pri.item_code, bin.actual_qty
        from `tabPurchase Receipt Item` pri
        inner join `tabPurchase Receipt` pr
       	on pr.name = pri.parent
        inner join `tabBin` bin
        on  bin.item_code = pri.item_code
        where bin.actual_qty > 0 and pr.posting_date < '2016-03-01'
        """

def other2():

    
    # Purchase Invoices for a project
    sql = """select
            pr.project as prproject
            ,pii.creation, pii.name, pii.item_name, pii.item_name as purchase_type, pii.base_net_amount
            , pr.supplier, pi.name
            from `tabPurchase Invoice Item` pii
            
            inner join `tabPurchase Invoice` pi
            on pi.name = pii.parent
            left join `tabPurchase Receipt` pr
            on pr.project = pii.project
            where pii.docstatus = 1 and pii.project = '04';
            """

        
    # Fix
    sql = """update `tabPurchase Invoice Item` pii
        set pii.project = NULL
        where pii.name = '8f26b07c5b'
        """

        
    sql = """select mode_of_payment, parent from  `tabSales Invoice Payment` limit 2;"""

        
    sql = """Update Purchase Receipts incorrectly posted to Stock Received But Not Billed"""
    sql = """select name, against_expense_account from  `tabPurchase Invoice` where against_expense_account like 'Stock%' and not memset, etc; """
    sql = """select name, account, parent, party, against from `tabGL Entry` where account like 'Stock Received But Not Billed - URTL';"""
        
        # need to update both GKL Entry and the PINV, etc
        
    sql = """update `tabPurchase Invoice` set against_expense_account = 'Cost of Goods Sold - URTL'
        where against_expense_account = 'Stock Received But Not Billed - URTL';
        """
        # and supplier_type= 'University (UK)';
        
    sql = """update `tabPurchase Invoice Item` set account = ''Cost of Goods Sold"
        where account = "Stock Received But Not Billed - URTL' and supplier_type= 'University (UK)'
        """
        
        
        # Fix mispost to Stock Received But Not Billed
        # Tables affected by this could be: PREC, PINV, GL, Journal Entry, Journal Entry Account, Party Account, Payment Entry, PINV Item, Stock Ledger Entry, Item Supplier
    sql = """update set where = 'Stock Recieved But Not Billed'"""
    sql = """update `tabGL Entry` set account = 'Cost of Goods Sold - URTL' where name = 'GLXXXXX';"""





def project_sales():

        
    sql = """select
    		si_item.qty, si_item.item_code, si_item.item_name, si_item.net_amount as si_sales_revenue, si_item.item_group
    		, si.name as si_code, si.posting_date, si.customer, si.customer_group, si.return_against
            , it.default_supplier, it.item_group, it.parts_cost, it.cost_of_repairs, it.processing_time_end, it.processing_start as processing_time_start
            , it.net_weight as per_item_weight, it.floorspace_recouped, it.length, it.width, it.height, it.year_of_manufacture, it.price_of_equivalent_new_item, it.metal, it.wood, it.plastic
            , pri.parent as pri_code, pri.creation
            , pr.posting_date as pr_posting_date, pr.name as prec_code
       	from
    		`tabSales Invoice Item` si_item
    	
    	inner join `tabSales Invoice` si
    		on si.name = si_item.parent
        
        inner join `tabItem` it
        	on  it.item_code = si_item.item_code
        
        inner join `tabPurchase Receipt Item` pri
       		on pri.item_code = it.item_code
        
        inner join `tabPurchase Receipt` pr
       		on pr.name = pri.parent
        
        where si.docstatus = 1 and pri.docstatus = 1 and it.default_supplier != 'Michael McLeod'
        and pr.project = '61 Bham Bio Lab Cupboards'
        order by it.default_supplier, si.posting_date desc\
        """