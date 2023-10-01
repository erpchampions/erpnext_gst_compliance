# -*- coding: utf-8 -*-
# Copyright (c) 2021, Frappe and contributors
# For license information, please see license.txt

from __future__ import unicode_literals

import six
import frappe
from frappe import _
from json import loads, dumps
from frappe.model import default_fields
from frappe.model.document import Document
from frappe.utils.data import cint, format_date, getdate, flt, get_link_to_form
from frappe.core.doctype.version.version import get_diff
import random
from erpnext_gst_compliance.efris_utils import efris_log_info, get_ug_time_str

#from erpnext.regional.india.utils import get_gst_accounts
GST_ACCOUNT_FIELDS = (
    "account",    
)

class EInvoice(Document):
	def validate(self):
		self.validate_uom()
		self.validate_items()
	
	def before_submit(self):
		if not self.irn:
			msg = _("Cannot submit e-invoice without EFRIS.") + ' '
			msg += _("You must generate EFRIS for the sales invoice to submit this e-invoice.")
			frappe.throw(msg, title=_("Missing EFRIS"))

	def on_update(self):
		self.update_sales_invoice()

	def on_update_after_submit(self):
		self.update_sales_invoice()

	def update_sales_invoice(self):
		frappe.db.set_value('Sales Invoice', self.invoice, {
			'irn': self.irn,
			'ack_no': self.ack_no,
			'e_invoice': self.name,
			'ack_date': self.ack_date,
			'ewaybill': self.ewaybill,
			'einvoice_status': self.status,
			'qrcode_image': self.qrcode_path,
			'irn_cancel_date': self.irn_cancel_date,
			'eway_bill_validity': self.ewaybill_validity
		}, update_modified=False)

	def on_cancel(self):
		frappe.db.set_value('Sales Invoice', self.invoice, 'e_invoice', self.name, update_modified=False)

	@frappe.whitelist()
	def fetch_invoice_details(self):
		efris_log_info("fetch_invoice_details...")

		self.set_sales_invoice()
		efris_log_info("set_sales_invoice OK")
		
		self.set_invoice_type()
		efris_log_info("set_invoice_type OK")
		
		self.set_supply_type()
		efris_log_info("set_supply_type OK")
		
		self.set_basic_information()
		efris_log_info("set_basic_information OK")
  
		self.set_seller_details()
		efris_log_info("set_seller_details OK")

		self.set_buyer_details()
		efris_log_info("set_buyer_details OK")
		#self.set_buyer_extend()


		self.set_item_details()
		efris_log_info("set_item_details OK")
		#self.set_value_details()
		self.set_tax_details()
		efris_log_info("set_tax_details OK")
		
		self.set_summary_details()
		efris_log_info("set_summary_details OK")
		
  
	def set_basic_information(self):
     
		service_provider = frappe.db.get_single_value('E Invoicing Settings', 'service_provider')
		if not service_provider:
			return False

		# URA set fields
		self.invoiceNo = ""
		self.antifakeCode = ""

		# Get Device Code For Each Company
		doc =  frappe.get_doc("ERP Champions Settings")
		for entry in doc.credentials:
			if entry.company == self.sales_invoice.company:
				self.device_no = entry.device_no
  
		self.issuedDate = self.sales_invoice.creation
		self.operator = self.sales_invoice.modified_by
		self.currency = self.sales_invoice.currency
		self.oriInvoiceId = ""
		self.invoiceType = self.set_invoice_type()
		self.invoiceKind = 1 # Hardcode for now
		self.dataSource = 101 # Hardcode for now
		self.invoiceIndustryCode = 101 # Harccode for now
		self.isBatch = 0 # Hardcode for now
  
	def set_buyer_extend(self):
		# Leave fields blank for phase 1
		self.propertyType = ""
		self.district = ""
		self.municipalityCounty = ""
		self.divisionSubcounty = ""
		self.town = ""
		self.cellVillage = ""
		self.effectiveRegistrationDate = ""
		self.meterStatus = ""
  
	def set_summary_details(self):
		self.net_amount = self.sales_invoice.net_total
		if len(self.sales_invoice.taxes) > 0:
			self.tax_amount = self.sales_invoice.taxes[0].tax_amount
		else:
			self.tax_amount = 0
		
		self.gross_amount = self.sales_invoice.grand_total
		self.item_count = len(self.sales_invoice.items)
		self.mode_code = 1 # Hardcode for now
		self.remarks = ""
		self.qr_code = ""




	def set_sales_invoice(self):
		self.sales_invoice = frappe.get_doc('Sales Invoice', self.invoice)

	def set_invoice_type(self):
		# 1:Invoice/Receipt 
		# 5:Credit Memo/rebate 
		# 4:Debit Note
		return 1 # Hardcode to Invoice/receipt for now

	def set_supply_type(self):
		gst_category = self.sales_invoice.gst_category
		# Modified to URA standards
		if gst_category == 'B2B': self.supply_type = 0
		elif gst_category == 'B2C': self.supply_type = 1
		elif gst_category == 'Foreigner': self.supply_type = 2
		elif gst_category == 'B2G': self.supply_type = 3
  
	def set_tax_details(self):
		efris_log_info("set_return_doc_reference()..")
		# MOKI TODO: more work here to handle all  tax rate types (Standard, Excempt, 0-rated,..)
					
		taxes_list = []

		for tax_item in self.sales_invoice.taxes:

			efris_log_info("tax_item rate/total :" + str(tax_item.rate) + "/" + str(tax_item.total) )		
			taxes = frappe._dict({
				"tax_category_code" : "01", # TODO: handle multiple categories
				"net_amount" : self.sales_invoice.net_total, # TODO: handle multiple categories
				"tax_rate" : tax_item.rate/100,
				"tax_amount" : tax_item.tax_amount,
				"gross_amount" : tax_item.total, # TODO: handle multiple categories
				"excise_unit" : "",
				"excise_currency" : "",
				"tax_rate_name" : ""
			})
			taxes_list.append(taxes)
		efris_log_info("clearing taxes table here")
		self.taxes = []
		self.append("taxes", taxes)
		#else:
		#	return
		
	
	def set_seller_details(self):
		company_address = self.sales_invoice.company_address
		if not company_address:
			frappe.throw(_('Company address must be set to be able to generate e-invoice.'))

		seller_address = frappe.get_all('Address', {'name': company_address}, ['*'])[0]
		# mandatory_field_label_map = {
		# 	'gstin': 'GSTIN',
		# 	'address_line1': 'Address Lines',
		# 	'city': 'City',
		# 	'pincode': 'Pincode',
		# 	'gst_state_number': 'State Code',
		# 	'email_id': 'Email Address',
		# 	'phone': 'Phone'
		# }
		# for field, field_label in mandatory_field_label_map.items():
		# 	if not seller_address[field]:
		# 		frappe.throw(_('Company address {} must have {} set to be able to generate e-invoice.')
		# 			.format(company_address, field_label))
    
		# if not self.sales_invoice.seller_reference_no:
		# 	frappe.throw(_('Reference No must be set'))

		self.seller_legal_name = self.company
		#company = frappe.get_doc("Company",self.company)
		
		self.seller_gstin = self.sales_invoice.company_tax_id
		efris_log_info("self.seller_gstin:" + str(self.seller_gstin))

		self.seller_phone = seller_address.phone
		# Added fields
		self.seller_email = seller_address.email_id
		# Use invoice name instead
		self.seller_reference_no = self.sales_invoice.seller_reference_no
		efris_log_info("self.seller_reference_no:" + str(self.seller_reference_no))
		if not self.seller_reference_no:
			self.seller_reference_no = self.sales_invoice.name
		self.seller_trade_name = self.company

	def set_buyer_details(self):
		#customer_address = self.sales_invoice.customer_address
		
		#frappe.log_error("set_buyer_details...")
		customer_name = self.sales_invoice.customer
		if not customer_name:
			frappe.throw(_('customer must be set to be able to generate e-invoice.'))
		
			
		customer = frappe.get_doc('Customer', customer_name)
		self.buyer_gstin = customer.tax_id
		frappe.log_error("self.buyer_gstin: " + str(self.buyer_gstin))

		gst_category = self.sales_invoice.gst_category
		
		# Modified to URA standards
		if gst_category == 'B2B' and not self.buyer_gstin: 
			frappe.throw(_('TaxID/TIN must be set for B2B Customer (GST Category). See Tax tab on Customer profile.'))
		#elif gst_category == 'B2C'
		#elif gst_category == 'Foreigner':
		#elif gst_category == 'B2G': 

		
		self.buyer_legal_name = customer.customer_name #self.sales_invoice.customer
		#frappe.log_error("self.buyer_legal_name: " + str(self.buyer_legal_name))

		
		self.buyer_nin_or_brn = customer.nin_or_brn 
		#pass_num = frappe.get_list("Customer", fields="*", filters={'name':self.sales_invoice.customer})[0].buyer_pass_num
		#self.buyerPassportNum = "" if pass_num is None else  pass_num
		#self.buyer_phone = buyer_address.phone # Picked from customer phone field
		self.buyer_citizenship = "" # Hardcode for now
		self.buyer_sector = "" # Hardcode for now
		self.buyer_reference_no = "" # Hardcode for now
		self.non_resident_flag = 0 # Hardcode for now

		#if is_export:
			#self.buyer_gstin = 'URP'
			#self.buyer_state_code = 96
			#self.buyer_pincode = 999999
		#	self.buyer_place_of_supply = 96
	
	def set_shipping_details(self):
		shipping_address_name = self.sales_invoice.shipping_address_name
		if shipping_address_name:
			is_export = self.supply_type == 'EXPWOP'
			shipping_address = frappe.get_all('Address', {'name': shipping_address_name}, ['*'])[0]

			self.shipping_legal_name = shipping_address.address_title
			self.shipping_gstin = shipping_address.gstin
			self.shipping_location = shipping_address.city
			self.shipping_pincode = shipping_address.pincode
			self.shipping_address_line_1 = shipping_address.address_line1
			self.shipping_address_line_2 = shipping_address.address_line2
			self.shipping_state_code = shipping_address.gst_state_number

			if is_export:
				self.shipping_gstin = 'URP'
				self.shipping_state_code = 96
				self.shipping_pincode = 999999
				self.shipping_place_of_supply = 96

	def set_dispatch_details(self):
		dispatch_address_name = self.sales_invoice.dispatch_address_name
		if dispatch_address_name:
			dispatch_address = frappe.get_all('Address', {'name': dispatch_address_name}, ['*'])[0]

			self.dispatch_legal_name = dispatch_address.address_title
			self.dispatch_location = dispatch_address.city
			self.dispatch_pincode = dispatch_address.pincode
			self.dispatch_address_line_1 = dispatch_address.address_line1
			self.dispatch_address_line_2 = dispatch_address.address_line2
			self.dispatch_state_code = dispatch_address.gst_state_number

	def set_item_details(self):
		sales_invoice_item_names = [d.name for d in self.sales_invoice.items]
		e_invoice_item_names = [d.si_item_ref for d in self.items]
		item_added_or_removed = sales_invoice_item_names != e_invoice_item_names
		efris_log_info("item_added_or_removed:" +str(item_added_or_removed))
		self.update_items_from_invoice()	
		#if item_added_or_removed:
		#	self.update_items_from_invoice()
		#else:
		#	self.fetch_items_from_invoice()

	def fetch_items_from_invoice(self):
		efris_log_info("fetch_items_from_invoice")
		item_taxes = loads(self.sales_invoice.taxes[0].item_wise_tax_detail)
		
		for i, item in enumerate(self.sales_invoice.items):
			frappe.log_error(title="Sales Item Picking", message=item.as_dict())
			if not item.gst_hsn_code:
				frappe.throw(_('Row #{}: Item {} must have HSN code set to be able to generate e-invoice.')
					.format(item.idx, item.item_code))

			is_service_item = item.gst_hsn_code[:2] == "99"

			if flt(item.qty) == 0.0:
				rate = abs(item.taxable_value)
			else:
				rate = abs((abs(item.taxable_value)) / item.qty)

			einvoice_item = frappe._dict({
				'si_item_ref': item.name,
				'item_code': item.item_code,
				'item_name': item.item_name,
				'is_service_item': is_service_item,
				'gst_hsn_code': item.gst_hsn_code,
				'quantity': abs(item.qty),
				'unit': item.uom, 
				'rate': item.rate,
				'tax': round(item_taxes[item.item_code][1], 2),
				'gst_rate': round(item_taxes[item.item_code][0]/100,2),
				'amount': item.amount,
				'order_number': i,
				'hsn_code_description': frappe.get_doc("GST HSN Code", item.gst_hsn_code).commodity_name
			})
			frappe.log_error(title="Einvoice Item before tax set", message=einvoice_item)
   
			# self.set_item_tax_details(einvoice_item)

			# einvoice_item.total_item_value = abs(
			# 	einvoice_item.taxable_value + einvoice_item.igst_amount +
			# 	einvoice_item.sgst_amount + einvoice_item.cgst_amount + 
			# 	einvoice_item.cess_amount + einvoice_item.cess_nadv_amount +
			# 	einvoice_item.other_charges
			# )
			self.append('items', einvoice_item)
   
			frappe.log_error(title="Einvoice Item before tax set", message=einvoice_item)

		#self.set_calculated_item_totals()

	def update_items_from_invoice(self):
		efris_log_info("update_items_from_invoice, clear existing")
		if self.items:
			self.get("items").clear()
		self.fetch_items_from_invoice()
		# item_taxes = loads(self.sales_invoice.taxes[0].item_wise_tax_detail)
		# for i, einvoice_item in enumerate(self.items):
		# 	item = self.sales_invoice.items[i]

		# 	if not item.gst_hsn_code:
		# 		frappe.throw(_('Row #{}: Item {} must have HSN code set to be able to generate e-invoice.')
		# 			.format(item.idx, item.item_code))

		# 	is_service_item = item.gst_hsn_code[:2] == "99" #TODO: Change to EFRIS logic

		# 	einvoice_item.update({
		# 		'item_code': item.item_code,
		# 		'item_name': item.item_name,
		# 		'is_service_item': is_service_item,
		# 		'gst_hsn_code': item.gst_hsn_code,
		# 		'quantity': abs(item.qty),
		# 		'unit': item.uom,
		# 		'rate': item.rate,
		# 		'gst_rate': round(item_taxes[item.item_code][0]/100,2),
		# 		'amount': item.amount,
		# 		'tax': round(item_taxes[item.item_code][1], 2),
    	# 		'order_number': i,
		# 		'hsn_code_description': frappe.get_doc("GST HSN Code", item.gst_hsn_code).commodity_name
		# 	})

			#self.set_item_tax_details(einvoice_item)

			# einvoice_item.total_item_value = abs(
			# 	einvoice_item.taxable_value + einvoice_item.igst_amount +
			# 	einvoice_item.sgst_amount + einvoice_item.cgst_amount + 
			# 	einvoice_item.cess_amount + einvoice_item.cess_nadv_amount +
			# 	einvoice_item.other_charges
			# )

		#self.set_calculated_item_totals()

	
	
	def update_other_charges(self, tax_row, gst_accounts_list, considered_rows):
		taxes = self.sales_invoice.get('taxes')
		prev_row_id = cint(tax_row.row_id) - 1

		if tax_row.account_head in gst_accounts_list and prev_row_id not in considered_rows:
			if tax_row.charge_type == 'On Previous Row Amount':
				amount = taxes[prev_row_id].tax_amount_after_discount_amount
				self.other_charges -= abs(amount)
				considered_rows.append(prev_row_id)
			if tax_row.charge_type == 'On Previous Row Total':
				amount = taxes[prev_row_id].base_total - self.sales_invoice.base_net_total
				self.other_charges -= abs(amount)
				considered_rows.append(prev_row_id)

	def set_payment_details(self):
		if self.sales_invoice.is_pos and self.sales_invoice.base_paid_amount:
			self.payee_name = self.company
			self.mode = ', '.join([d.mode_of_payment for d in self.sales_invoice.payments if d.amount > 0])
			self.paid_amount = self.sales_invoice.base_paid_amount
			self.outstanding_amount = self.sales_invoice.outstanding_amount

	def set_return_doc_reference(self):
		if self.sales_invoice.is_return:
			if not self.sales_invoice.return_against:
				frappe.throw(_('For generating EFRIS, reference to the original invoice is mandatory for a credit note. Please set {} field to generate e-invoice.')
					.format(frappe.bold('Return Against')), title=_('Missing Field'))

			self.previous_document_no = self.sales_invoice.return_against
			original_invoice_date = frappe.db.get_value('Sales Invoice', self.sales_invoice.return_against, 'posting_date')
			self.previous_document_date = format_date(original_invoice_date, 'dd/mm/yyyy')

	def get_einvoice_json(self):
		# Update to have URA fields
		einvoice_json = {
			"extend": {
			},
			"importServicesSeller": {
			},
			"airlineGoodsDetails": [
				{
				}
			],
			"edcDetails": {
			},
			"agentEntity": {
			}
		}


		einvoice_json.update(self.get_seller_details_json())
		einvoice_json.update(self.get_basic_information_json())
		einvoice_json.update(self.get_buyer_details_json())
		einvoice_json.update(self.get_buyer_extend())
		einvoice_json.update(self.get_good_details())
		einvoice_json.update(self.get_tax_details())
		einvoice_json.update(self.get_summary())
  
		frappe.log_error(title="Einvoice JSON", message=einvoice_json)

		return einvoice_json

	def get_seller_details_json(self):
		return {
			"sellerDetails": {
				"tin": self.seller_gstin,
				"ninBrn": "",
				"legalName": self.seller_legal_name,
				"businessName": self.seller_trade_name,
				"mobilePhone": self.seller_phone,
				"linePhone": "",
				"emailAddress": self.seller_email,
				"referenceNo": self.seller_reference_no,
				"branchId": "",
				"isCheckReferenceNo": "0",
				"branchName": "Test",
				"branchCode": ""
			}
		}

	def get_basic_information_json(self):
		return {
			"basicInformation": {
				"invoiceNo": "",
				"antifakeCode": "",
				"deviceNo": self.device_no,
				"issuedDate": str(self.issuedDate),
				"operator": self.operator,
				"currency": self.currency,
				"oriInvoiceId": "",
				"invoiceType": str(self.invoiceType),
				"invoiceKind": str(self.invoiceKind),
				"dataSource": str(self.dataSource),
				"invoiceIndustryCode": str(self.invoiceIndustryCode),
				"isBatch": str(self.isBatch)
			}
		}
	
	def get_buyer_details_json(self):
		return {
			"buyerDetails": {
				"buyerTin": self.buyer_gstin,
				"buyerNinBrn": self.buyer_nin_or_brn,
				"buyerPassportNum": "",
				"buyerLegalName": self.buyer_legal_name,
				"buyerBusinessName": self.buyer_legal_name,
				"buyerType": self.supply_type,
				"buyerCitizenship": self.buyer_citizenship,
				"buyerSector": self.buyer_sector,
				"buyerReferenceNo": self.buyer_reference_no,
				"nonResidentFlag": self.non_resident_flag
			}
		}

	def get_buyer_extend(self):
		return {
			"buyerExtend": {
				"propertyType": "",
				"district": "",
				"municipalityCounty": "",
				"divisionSubcounty": "",
				"town": "",
				"cellVillage": "",
				"effectiveRegistrationDate": "",
				"meterStatus": ""
			}
		}

	def get_good_details(self):
		item_list = []
		for row in self.items:
			#frappe.log_error(title="Item details", message=row.as_dict())
			
			inv_uom = frappe.get_doc("UOM",row.unit)
			efris_uom_code = inv_uom.efris_uom_code


			item = {
				"item": row.item_name,
				"itemCode": row.item_code,
				"qty": str(row.quantity),
				"unitOfMeasure": efris_uom_code,
				"unitPrice": str(row.rate),
				"total": str(row.amount),
				"taxRate": str(row.gst_rate), # Get from Uganda tax template
				"tax": str(row.tax),
				"discountTotal": "",
				"discountTaxRate": "0.00",
				"orderNumber": str(row.order_number),
				"discountFlag": "2",
				"deemedFlag": "2",
				"exciseFlag": "2",
				"categoryId": "",
				"categoryName": "",
				"goodsCategoryId": row.gst_hsn_code,
				"goodsCategoryName": row.hsn_code_description,
				"exciseRate": "",
				"exciseRule": "",
				"exciseTax": "",
				"pack": "",
				"stick": "",
				"exciseUnit": "101",
				"exciseCurrency": "UGX",
				"exciseRateName": "",
				"vatApplicableFlag": "1",
				"deemedExemptCode": "",
				"vatProjectId": "",
				"vatProjectName": ""
			}
			item_list.append(item)
		return {
			"goodsDetails": item_list
		}
		
	def get_tax_details(self):
		#TODO Support multiple tax categories
		return {
			"taxDetails": [{
				"taxCategoryCode": "01",
				"netAmount": str(self.net_amount),
				"taxRate": str(self.sales_invoice.taxes[0].rate/100),
				"taxAmount": str(self.tax_amount),
				"grossAmount": str(self.gross_amount),
				"exciseUnit": "",
				"exciseCurrency": "",
				"taxRateName": ""
			}]
		}

	def get_summary(self):
		return {
			"summary": {
				"netAmount": str(self.net_amount),
				"taxAmount": str(self.tax_amount),
				"grossAmount": str(self.gross_amount),
				"itemCount": str(self.item_count),
				"modeCode": str(self.mode_code),
				"remarks": "",
				"qrCode": ""
			}
       }


	def sync_with_sales_invoice(self):
		# to fetch details from 'fetch_from' fields
		self._action = 'save'
		self._validate_links()
		self.fetch_invoice_details()

	def validate_items(self):
		error_list = []
		return #MOKI, temp deactivate validations
		for item in self.items:
			if (item.cgst_amount or item.sgst_amount) and item.igst_amount:
				error_list.append(_('Row #{}: Invalid value of Tax Amount, provide either IGST or both SGST and CGST.')
					.format(item.idx))
			
			if item.gst_rate not in [0.000, 0.100, 0.250, 0.500, 1.000, 1.500, 3.000, 5.000, 7.500, 12.000, 18.000, 28.000]:
				error_list.append(_('Row #{}: Invalid GST Tax rate. Please correct the Tax Rate Values and try again.')
					.format(item.idx))

			total_gst_amount = item.cgst_amount + item.sgst_amount + item.igst_amount
			if abs((item.taxable_value * item.gst_rate / 100) - total_gst_amount) > 1:
				error_list.append(_('Row #{}: Invalid GST Tax rate. Please correct the Tax Rate Values and try again.')
					.format(item.idx))

			if not item.gst_hsn_code:
				error_list.append(_('Row #{}: HSN Code is mandatory for e-invoice generation.')
					.format(item.idx))

		if abs(self.base_invoice_value - (self.items_total_value - self.invoice_discount + self.other_charges + self.round_off_amount)) > 1:
			msg = _('Invalid Total Invoice Value.') + ' '
			msg += _('The Total Invoice Value should be equal to the Sum of Total Value of All Items - Invoice Discount + Invoice Other charges + Round-off amount.') + ' '
			msg += _('Please correct the Invoice Value and try again.')
			error_list.append(msg)
		
		if error_list:
			frappe.throw(error_list, title=_('E Invoice Validation Failed'), as_list=1)

	def validate_uom(self):
		for item in self.items:			
			
			inv_uom = frappe.get_doc("UOM",item.unit)
			efris_log_info("item.unit:" + str(item.unit))
			if not inv_uom:
				frappe.throw("Cannot find in UOM List. Unit:" + item.unit)
			efris_uom_code = inv_uom.efris_uom_code			
			efris_log_info("efris_uom_code:" + str(efris_uom_code))

			if not efris_uom_code:
				msg = _('Row #{}: {} has invalid UOM set.').format(item.idx, item.item_name) + ' '
				msg += _('Please set EFRIS UOM Code on UOM.')
				msg += '<br><br>'
				frappe.throw(msg, title=_('Invalid Item UOM'))


	def set_eway_bill_details(self, details):
		self.sales_invoice = frappe._dict()
		self.sales_invoice.transporter = details.transporter
		self.transporter_gstin = details.transporter_gstin
		self.transporter_name = details.transporter_name
		self.distance = details.distance
		self.transport_document_no = details.transport_document_no
		self.transport_document_date = details.transport_document_date
		self.vehicle_no = details.vehicle_no
		self.vehicle_type = details.vehicle_type or ''
		self.mode_of_transport = details.mode_of_transport

	def get_eway_bill_json(self):
		eway_bill_details = self.get_ewaybill_details_json().get('EwbDtls')
		eway_bill_details.update({ 'Irn': self.irn })

		return eway_bill_details

def create_einvoice(sales_invoice):
	if frappe.db.exists('E Invoice', sales_invoice):
		einvoice = frappe.get_doc('E Invoice', sales_invoice)
	else:
		einvoice = frappe.new_doc('E Invoice')
		einvoice.invoice = sales_invoice

	einvoice.sync_with_sales_invoice()
	einvoice.flags.ignore_permissions = 1
	einvoice.save()
	frappe.db.commit()

	efris_log_info("create_einvoice returning")
	return einvoice

def get_einvoice(sales_invoice):
	return frappe.get_doc('E Invoice', sales_invoice)

def validate_sales_invoice_change(doc, method=""):
	efris_log_info("validate_sales_invoice_change, doc.docstatus/_action:" +  str(doc.docstatus) + "/" + str(doc._action))
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if doc.einvoice_status in ['EFRIS Cancelled']:
		return

	if doc.docstatus == 0 and doc._action == 'save':
		efris_log_info("saving..")
		if frappe.db.exists('E Invoice', doc.name):
			einvoice = get_einvoice(doc.e_invoice)

			einvoice_copy = get_einvoice(doc.e_invoice)
			einvoice_copy.sync_with_sales_invoice()
			
			# to ignore changes in default fields
			#einvoice = remove_default_fields(einvoice)
			einvoice_copy = remove_default_fields(einvoice_copy)
			diff = get_diff(einvoice, einvoice_copy)
	
			if diff and einvoice.status in ['EFRIS Generated','EFRIS Credit Note Pending']:
				frappe.log_error(
					message=dumps(diff, indent=2),
					title=_('E-Invoice: Edit Not Allowed')
				)
				frappe.throw(_('You cannot edit the invoice after generating EFRIS'), title=_('Edit Not Allowed'))

def remove_default_fields(doc):
	clone = frappe.copy_doc(doc)
	for fieldname in clone.as_dict():
		value = doc.get(fieldname)
		if isinstance(value, list):
			trimmed_child_docs = []
			for d in value:
				trimmed_child_docs.append(remove_default_fields(d))
			doc.set(fieldname, trimmed_child_docs)

		if fieldname == 'name':
			# do not reset name, since it is used to check child table row changes
			continue

		if fieldname in default_fields or fieldname == '__islocal':
			doc.set(fieldname, None)

	return doc

@frappe.whitelist()
def validate_einvoice_eligibility(doc):
	if isinstance(doc, six.string_types):
		doc = loads(doc)

	#frappe.log_error("** validate_einvoice_eligibility +1 **")
	service_provider = frappe.db.get_single_value('E Invoicing Settings', 'service_provider')
	if not service_provider:
		return False

	#frappe.log_error("** validate_einvoice_eligibility +2 **")

	# if service_provider ==  "ERP Champions Settings":
	# 	einvoicing_enabled = frappe.get_cached_doc(service_provider)
	# else:
	# 	einvoicing_enabled = frappe.get_cached_doc("GST Settings", "GST Settings")
	
	einvoicing_enabled = cint(frappe.db.get_single_value(service_provider, 'enabled'))
 
	if not einvoicing_enabled:
		return False

	#frappe.log_error("** validate_einvoice_eligibility +3 **")

	einvoicing_eligible_from = '2021-04-01'
	if getdate(doc.get('posting_date')) < getdate(einvoicing_eligible_from):
		return False

	#frappe.log_error("** validate_einvoice_eligibility +4 **")

	eligible_companies = frappe.db.get_single_value('E Invoicing Settings', 'companies')
	invalid_company = doc.get('company') not in eligible_companies

	frappe.log_error("** validate_einvoice_eligibility invalid_company: **" + str(invalid_company))
	# Modified URA supply types
	invalid_supply_type = False # doc.get('gst_category') not in ["0", "1", "2", "3"] # 0: B2B 1: B2C 2: Foreigner 3: B2G
	inter_company_transaction = False # = doc.get('billing_address_gstin') == doc.get('company_gstin')
	has_non_gst_item = any(d for d in doc.get('items', []) if d.get('is_non_gst'))

	#frappe.log_error("** validate_einvoice_eligibility has_non_gst_item: **" + str(has_non_gst_item))
	# if export invoice, then taxes can be empty
	# invoice can only be ineligible if no taxes applied and is not an export invoice
	no_taxes_applied = not doc.get('taxes') and not doc.get('gst_category') == 'Overseas'
	
	#frappe.log_error("** validate_einvoice_eligibility no_taxes_applied: **" + str(no_taxes_applied))

	if invalid_company or invalid_supply_type or inter_company_transaction or no_taxes_applied or has_non_gst_item:
		frappe.log_error(f'{invalid_company}, {invalid_supply_type}, {inter_company_transaction}, {no_taxes_applied}, {has_non_gst_item}')
		return False

	frappe.log_error("** validate_einvoice_eligibility true **")
	return True

def validate_sales_invoice_submission(doc, method=""):
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if not doc.get('einvoice_status') or doc.get('einvoice_status') == 'EFRIS Pending':
		frappe.throw(_('You must generate EFRIS before submitting the document.'), title=_('Missing EFRIS'))

def validate_sales_invoice_cancellation(doc, method=""):
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if doc.get('einvoice_status') != 'EFRIS Cancelled':
		frappe.throw(_('You must cancel EFRIS before cancelling the document.'), title=_('Cancellation Not Allowed'))

def validate_sales_invoice_deletion(doc, method=""):
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if doc.get('einvoice_status') != 'EFRIS Cancelled':
		frappe.throw(_('You must cancel EFRIS before deleting the document.'), title=_('Deletion Not Allowed'))

def cancel_e_invoice(doc, method=""):
	if doc.get('e_invoice'):
		e_invoice = frappe.get_doc('E Invoice', doc.get('e_invoice'))
		e_invoice.flags.ignore_permissions = True
		e_invoice.cancel()

def delete_e_invoice(doc, method=""):
	if doc.get('e_invoice'):
		frappe.db.set_value('Sales Invoice', doc.get('name'), 'e_invoice', '')
		frappe.delete_doc(
			doctype='E Invoice',
			name=doc.get('e_invoice'),
			ignore_missing=True
		)

def get_gst_accounts(
    company=None,
    account_wise=False,
    only_reverse_charge=0,
    only_non_reverse_charge=0,
):
    filters = {}

    if company:
        filters["company"] = company
    if only_reverse_charge:
        filters["account_type"] = "Reverse Charge"
    elif only_non_reverse_charge:
        filters["account_type"] = ("!=", "Reverse Charge")
        
    service_provider = frappe.db.get_single_value('E Invoicing Settings', 'service_provider')
 
    if not service_provider:
        return False
    if service_provider == "ERP Champions Settings":
        settings = frappe.get_cached_doc(service_provider)
    else:
        settings = frappe.get_cached_doc("GST Settings", "GST Settings")
        
    gst_accounts = settings.get("gst_accounts", filters)
    result = frappe._dict()
	
    settings_form = get_link_to_form('ERP Champions Settings', 'ERP Champions Settings')
    
    if not gst_accounts:
        frappe.throw(_("Cannot find GST Accounts under ERP Champions settings. Please check GST Settings under {}.").format(settings_form))
    	

    for row in gst_accounts:
        for fieldname in GST_ACCOUNT_FIELDS:
            if not (value := row.get(fieldname)):
                continue

            if not account_wise:
                result.setdefault(fieldname, []).append(value)
            else:
                result[value] = fieldname

    return result