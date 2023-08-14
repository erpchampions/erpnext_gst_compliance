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
from frappe.utils.data import cint, format_date, getdate, flt
from frappe.core.doctype.version.version import get_diff
import random

#from erpnext.regional.india.utils import get_gst_accounts
GST_ACCOUNT_FIELDS = (
    "cgst_account",
    "sgst_account",
    "igst_account",
    "cess_account",
    "cess_non_advol_account",
)

class EInvoice(Document):
	def validate(self):
		self.validate_uom()
		self.validate_items()
	
	def before_submit(self):
		if not self.irn:
			msg = _("Cannot submit e-invoice without IRN.") + ' '
			msg += _("You must generate IRN for the sales invoice to submit this e-invoice.")
			frappe.throw(msg, title=_("Missing IRN"))

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
     
		# ERP Champions: Mimic the doctype structure as customized for EFRIS
		# set_basic_information()
		# set_seller_details()
		# set_buyer_details()
		# set_buyer_extend() #skip for phase 1
		# set_item_details()
		# set_tax_details()
		# set_summary_details()
  
		self.set_sales_invoice()
		self.set_invoice_type()
		self.set_supply_type()
  
		self.set_seller_details()
		self.set_buyer_details()
		self.set_item_details()
		self.set_value_details()
  
		# Additional methods
		self.set_basic_information()
		self.set_buyer_extend()
		self.set_summary_details()
		self.set_tax_details()
  
	def set_basic_information(self):
     
		service_provider = frappe.db.get_single_value('E Invoicing Settings', 'service_provider')
		if not service_provider:
			return False

		# URA set fields
		self.invoiceNo = ""
		self.antifakeCode = ""
  
		self.deviceNo = frappe.db.get_single_value(service_provider, 'device_no')
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
		self.netAmount = self.sales_invoice.net_total
		if len(self.sales_invoice.taxes) > 0:
			self.taxAmount = self.sales_invoice.taxes[0].tax_amount
		else:
			self.taxAmount = 0
		
		self.grossAmount = self.sales_invoice.grand_total
		self.itemCount = len(self.sales_invoice.items)
		self.modeCode = 1 # Hardcode for now
		self.remarks = "Test Askcc invoice"
		self.qrCode = ""

		"""
		ERP Champions: Mimic the doctype structure as customized for EFRIS
		set_basic_information()
		set_seller_details()
		set_buyer_details()
		set_buyer_extend() #skip for phase 1
		set_item_details()
		set_tax_details()
		set_summary_details()

		"""


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
     
		if len(self.sales_invoice.taxes) > 0 and len(self.taxes) < 1:
			taxes = frappe._dict({
				"tax_category_code" : "01",
				"net_amount" : abs(self.sales_invoice.taxes[0].total - self.sales_invoice.taxes[0].tax_amount),
				"tax_rate" : self.sales_invoice.taxes[0].rate/100,
				"tax_amount" : self.sales_invoice.taxes[0].tax_amount,
				"gross_amount" : self.sales_invoice.taxes[0].total,
				"excise_unit" : "101",
				"excise_currency" : "UGX",
				"tax_rate_name" : "123"
			})
			self.append("taxes", taxes)
		else:
			return
		
		

	def set_seller_details(self):
		company_address = self.sales_invoice.company_address
		if not company_address:
			frappe.throw(_('Company address must be set to be able to generate e-invoice.'))

		seller_address = frappe.get_all('Address', {'name': company_address}, ['*'])[0]
		mandatory_field_label_map = {
			'gstin': 'GSTIN',
			'address_line1': 'Address Lines',
			'city': 'City',
			'pincode': 'Pincode',
			'gst_state_number': 'State Code',
			'email_id': 'Email Address'
		}
		for field, field_label in mandatory_field_label_map.items():
			if not seller_address[field]:
				frappe.throw(_('Company address {} must have {} set to be able to generate e-invoice.')
					.format(company_address, field_label))
    
		# if not self.sales_invoice.seller_reference_no:
		# 	frappe.throw(_('Reference No must be set'))

		self.seller_legal_name = self.company
		self.seller_gstin = seller_address.gstin
		self.seller_location = seller_address.city
		self.seller_pincode = seller_address.pincode
		self.seller_address_line_1 = seller_address.address_line1
		self.seller_address_line_2 = seller_address.address_line2
		self.seller_state_code = seller_address.gst_state_number
		# Added fields
		self.seller_email = seller_address.email_id
		# Use invoice name instead
		self.seller_reference_no = self.sales_invoice.name
		self.seller_trade_name = self.company

	def set_buyer_details(self):
		customer_address = self.sales_invoice.customer_address
		if not customer_address:
			frappe.throw(_('Customer address must be set to be able to generate e-invoice.'))

		is_export = self.supply_type == 'EXPWOP'
		buyer_address = frappe.get_all('Address', {'name': customer_address}, ['*'])[0]
		mandatory_field_label_map = {
			'gstin': 'GSTIN',
			'address_line1': 'Address Lines',
			'city': 'City',
			'pincode': 'Pincode',
			'gst_state_number': 'State Code',
			'email_id': 'Email Address',
		}
		for field, field_label in mandatory_field_label_map.items():
			if field == 'gstin':
				if not buyer_address.gstin and not is_export:
					frappe.throw(_('Customer address {} must have {} set to be able to generate e-invoice.')
						.format(customer_address, field_label))
				continue

			if not buyer_address[field]:
				frappe.throw(_('Customer address {} must have {} set to be able to generate e-invoice.')
					.format(customer_address, field_label))

		self.buyer_legal_name = self.sales_invoice.customer
		self.buyer_gstin = buyer_address.gstin
		self.buyer_location = buyer_address.city
		self.buyer_pincode = buyer_address.pincode
		self.buyer_address_line_1 = buyer_address.address_line1
		self.buyer_address_line_2 = buyer_address.address_line2
		self.buyer_state_code = buyer_address.gst_state_number
		self.buyer_place_of_supply = buyer_address.gst_state_number
		#Added fields
		self.buyer_email = buyer_address.email_id
  
		# self.buyerTin = buyer_address.gstin
		buyer_nin = frappe.get_list("Customer", fields="*", filters={'name':self.sales_invoice.customer})[0].nin
		self.buyerNinBrn = "" if buyer_nin is None else  buyer_nin
		pass_num = frappe.get_list("Customer", fields="*", filters={'name':self.sales_invoice.customer})[0].buyer_pass_num
		self.buyerPassportNum = "" if pass_num is None else  pass_num
		# self.buyerLegalName = ""
		# self.buyerBusinessName = ""
		# self.buyerAddress = ""
		# self.buyerEmail = buyer_address.email_id
		# self.buyerMobilePhone = ""
		self.buyerLinePhone = buyer_address.phone # Picked from customer phone field
		# self.buyerPlaceOfBusi = buyer_address.address_line1
		# self.buyerType = 0 # Same as supply type
		self.buyerCitizenship = "" # Hardcode for now
		self.buyerSector = "" # Hardcode for now
		self.buyerReferenceNo = "" # Hardcode for now
		self.nonResidentFlag = 0 # Hardcode for now

		if is_export:
			self.buyer_gstin = 'URP'
			self.buyer_state_code = 96
			self.buyer_pincode = 999999
			self.buyer_place_of_supply = 96
	
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

		if self.items and not item_added_or_removed:
			self.update_items_from_invoice()
		else:
			self.fetch_items_from_invoice()

	def fetch_items_from_invoice(self):
		item_taxes = loads(self.sales_invoice.taxes[0].item_wise_tax_detail)
		for item in self.sales_invoice.items:
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
				'discount': 0,
				'unit': item.uom, # Hardcode value for now
				'rate': item.rate,
				'tax': item_taxes[item.item_code][1],
				'gst_rate': round(item_taxes[item.item_code][0]/100,2),
				'amount': item.amount,
				'taxable_value': abs(item.amount)
			})
			frappe.log_error(title="Einvoice Item before tax set", message=einvoice_item)
   
			self.set_item_tax_details(einvoice_item)

			einvoice_item.total_item_value = abs(
				einvoice_item.taxable_value + einvoice_item.igst_amount +
				einvoice_item.sgst_amount + einvoice_item.cgst_amount + 
				einvoice_item.cess_amount + einvoice_item.cess_nadv_amount +
				einvoice_item.other_charges
			)
			self.append('items', einvoice_item)
   
			frappe.log_error(title="Einvoice Item before tax set", message=einvoice_item)

		self.set_calculated_item_totals()

	def update_items_from_invoice(self):
		item_taxes = loads(self.sales_invoice.taxes[0].item_wise_tax_detail)
		for i, einvoice_item in enumerate(self.items):
			item = self.sales_invoice.items[i]

			if not item.gst_hsn_code:
				frappe.throw(_('Row #{}: Item {} must have HSN code set to be able to generate e-invoice.')
					.format(item.idx, item.item_code))

			is_service_item = item.gst_hsn_code[:2] == "99"

			einvoice_item.update({
				'item_code': item.item_code,
				'item_name': item.item_name,
				'is_service_item': is_service_item,
				'gst_hsn_code': item.gst_hsn_code,
				'quantity': abs(item.qty),
				'discount': 0,
				'unit': item.uom,
				'rate': item.rate,
				'gst_rate': round(item_taxes[item.item_code][0]/100,2),
				'amount': item.amount,
				'taxable_value': abs(item.amount),
			})

			self.set_item_tax_details(einvoice_item)

			einvoice_item.total_item_value = abs(
				einvoice_item.taxable_value + einvoice_item.igst_amount +
				einvoice_item.sgst_amount + einvoice_item.cgst_amount + 
				einvoice_item.cess_amount + einvoice_item.cess_nadv_amount +
				einvoice_item.other_charges
			)

		self.set_calculated_item_totals()

	def set_calculated_item_totals(self):
		item_total_fields = ['items_ass_value', 'items_igst', 'items_sgst', 'items_cgst',
			'items_cess', 'items_cess_nadv', 'items_other_charges', 'items_total_value']

		for field in item_total_fields:
			self.set(field, 0)

		for item in self.items:
			self.items_ass_value += item.taxable_value
			self.items_igst += item.igst_amount
			self.items_sgst += item.sgst_amount
			self.items_cess += item.cess_amount
			self.items_cess_nadv += item.cess_nadv_amount
			self.items_other_charges += item.other_charges
			self.items_total_value += item.total_item_value

	def set_item_tax_details(self, item):
		gst_accounts = get_gst_accounts(self.company)
		gst_accounts_list = [d for accounts in gst_accounts.values() for d in accounts if d]

		for attr in ['gst_rate', 'cgst_amount',  'sgst_amount', 'igst_amount',
			'cess_rate', 'cess_amount', 'cess_nadv_amount', 'other_charges']:
			item.update({ attr: 0 })

		for t in self.sales_invoice.taxes:
			is_applicable = t.tax_amount and t.account_head in gst_accounts_list
			if is_applicable:
				# this contains item wise tax rate & tax amount (incl. discount)
				item_tax_detail = loads(t.item_wise_tax_detail).get(item.item_code or item.item_name)

				item_tax_rate = item_tax_detail[0]
				# item tax amount excluding discount amount
				item_tax_amount = (item_tax_rate / 100) * item.taxable_value

				if t.account_head in gst_accounts.cess_account:
					item_tax_amount_after_discount = item_tax_detail[1]
					if t.charge_type == 'On Item Quantity':
						item.cess_nadv_amount += abs(item_tax_amount_after_discount)
					else:
						item.cess_rate += item_tax_rate
						item.cess_amount += abs(item_tax_amount_after_discount)

				for tax_type in ['igst', 'cgst', 'sgst']:
					if t.account_head in gst_accounts[f'{tax_type}_account']:
						item.gst_rate += item_tax_rate
						amt_fieldname = f'{tax_type}_amount'
						item.update({
							amt_fieldname: item.get(amt_fieldname, 0) + abs(item_tax_amount)
						})
			else:
				# TODO: other charges per item
				pass

	def set_value_details(self):
		self.ass_value = abs(sum([i.taxable_value for i in self.get('items')]))
		self.invoice_discount = 0
		self.round_off_amount = self.sales_invoice.base_rounding_adjustment
		self.base_invoice_value = abs(self.sales_invoice.base_rounded_total) or abs(self.sales_invoice.base_grand_total)
		self.invoice_value = abs(self.sales_invoice.rounded_total) or abs(self.sales_invoice.grand_total)

		self.set_invoice_tax_details()

	def set_invoice_tax_details(self):
		gst_accounts = get_gst_accounts(self.company)
		gst_accounts_list = [d for accounts in gst_accounts.values() for d in accounts if d]

		self.cgst_value = 0
		self.sgst_value = 0
		self.igst_value = 0
		self.cess_value = 0
		self.other_charges = 0
		considered_rows = []

		for t in self.sales_invoice.taxes:
			tax_amount = t.base_tax_amount_after_discount_amount

			if t.account_head in gst_accounts_list:
				if t.account_head in gst_accounts.cess_account:
					# using after discount amt since item also uses after discount amt for cess calc
					self.cess_value += abs(t.base_tax_amount_after_discount_amount)

				for tax in ['igst', 'cgst', 'sgst']:
					if t.account_head in gst_accounts[f'{tax}_account']:
						new_value = self.get(f'{tax}_value') + abs(tax_amount)
						self.set(f'{tax}_value', new_value)

					self.update_other_charges(t, gst_accounts_list, considered_rows)
			else:
				self.other_charges += abs(tax_amount)
	
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
				frappe.throw(_('For generating IRN, reference to the original invoice is mandatory for a credit note. Please set {} field to generate e-invoice.')
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
				"address": self.seller_location,
				"mobilePhone": "15501234567",
				"linePhone": "",
				"emailAddress": self.seller_email,
				"placeOfBusiness": self.seller_address_line_1,
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
				"buyerNinBrn": self.buyerNinBrn,
				"buyerPassportNum": self.buyerPassportNum,
				"buyerLegalName": self.buyer_legal_name,
				"buyerBusinessName": self.buyer_legal_name,
				"buyerAddress": self.buyer_location,
				"buyerEmail": self.buyer_email,
				"buyerMobilePhone": self.buyerLinePhone,
				"buyerLinePhone": "",
				"buyerPlaceOfBusi": self.buyer_address_line_1,
				"buyerType": "0",
				"buyerCitizenship": self.buyerCitizenship,
				"buyerSector": self.buyerSector,
				"buyerReferenceNo": self.buyerReferenceNo,
				"nonResidentFlag": self.nonResidentFlag
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
		item_taxes = loads(self.sales_invoice.taxes[0].item_wise_tax_detail)
		for row in self.sales_invoice.items:
			frappe.log_error(title="Item details", message=row.as_dict())
   
			item = {
				"item": row.item_name,
				"itemCode": row.item_code,
				"qty": str(row.qty),
				"unitOfMeasure": "101",
				"unitPrice": str(row.rate),
				"total": str(row.amount),
				"taxRate": str(item_taxes[row.item_code][0]/100), # Get from Uganda tax template
				"tax": str(round(item_taxes[row.item_code][1], 2)),
				"discountTotal": "",
				"discountTaxRate": "0.00",
				"orderNumber": 0,
				"discountFlag": "2",
				"deemedFlag": "2",
				"exciseFlag": "2",
				"categoryId": "",
				"categoryName": "",
				"goodsCategoryId": "50151513",
				"goodsCategoryName": "Services",
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
     
		return {
			"taxDetails": [{
				"taxCategoryCode": "01",
				"netAmount": str(self.netAmount),
				"taxRate": str(self.sales_invoice.taxes[0].rate/100),
				"taxAmount": str(self.taxAmount),
				"grossAmount": str(self.grossAmount),
				"exciseUnit": "101",
				"exciseCurrency": "UGX",
				"taxRateName": "123"
			}]
		}

	def get_summary(self):
		return {
			"summary": {
				"netAmount": str(self.netAmount),
				"taxAmount": str(self.taxAmount),
				"grossAmount": str(self.grossAmount),
				"itemCount": str(self.itemCount),
				"modeCode": str(self.modeCode),
				"remarks": "Test Askcc invoice.",
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
		return # MOKI, temp deactivate validations
		valid_uoms = ['BAG', 'BAL', 'BDL', 'BKL', 'BOU', 'BOX', 'BTL', 'BUN', 'CAN', 'CCM', 'CMS', 'CBM', 'CTN', 'DOZ', 'DRM', 'GGK', 'GMS', 'GRS', 'GYD', 'KGS', 'KLR', 'KME', 'LTR', 'MLS', 'MLT', 'MTR', 'MTS', 'NOS', 'OTH', 'PAC', 'PCS', 'PRS', 'QTL', 'ROL', 'SET', 'SQF', 'SQM', 'SQY', 'TBS', 'TGM', 'THD', 'TON', 'TUB', 'UGS', 'UNT', 'YD']
		for item in self.items:
			if item.unit and item.unit.upper() not in valid_uoms:
				msg = _('Row #{}: {} has invalid UOM set.').format(item.idx, item.item_name) + ' '
				msg += _('Please set proper UOM as defined by e-invoice portal.')
				msg += '<br><br>'
				uom_list_link = '<a href="https://einvoice1.gst.gov.in/Others/MasterCodes" target="_blank">this</a>'
				msg += _('You can refer {} link to check valid UOMs defined by e-invoice portal.').format(uom_list_link)
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

	return einvoice

def get_einvoice(sales_invoice):
	return frappe.get_doc('E Invoice', sales_invoice)

def validate_sales_invoice_change(doc, method=""):
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if doc.einvoice_status in ['IRN Cancelled', 'IRN Pending']:
		return

	if doc.docstatus == 0 and doc._action == 'save':
		if frappe.db.exists('E Invoice', doc.name):
			einvoice = get_einvoice(doc.e_invoice)
			einvoice_copy = get_einvoice(doc.e_invoice)
			einvoice_copy.sync_with_sales_invoice()
	
			# to ignore changes in default fields
			einvoice = remove_default_fields(einvoice)
			einvoice_copy = remove_default_fields(einvoice_copy)
			diff = get_diff(einvoice, einvoice_copy)
	
			if diff:
				frappe.log_error(
					message=dumps(diff, indent=2),
					title=_('E-Invoice: Edit Not Allowed')
				)
				frappe.throw(_('You cannot edit the invoice after generating IRN'), title=_('Edit Not Allowed'))

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

	service_provider = frappe.db.get_single_value('E Invoicing Settings', 'service_provider')
	if not service_provider:
		return False

	# if service_provider ==  "ERP Champions Settings":
	# 	einvoicing_enabled = frappe.get_cached_doc(service_provider)
	# else:
	# 	einvoicing_enabled = frappe.get_cached_doc("GST Settings", "GST Settings")
	
	einvoicing_enabled = cint(frappe.db.get_single_value(service_provider, 'enabled'))
 
	if not einvoicing_enabled:
		return False

	einvoicing_eligible_from = '2021-04-01'
	if getdate(doc.get('posting_date')) < getdate(einvoicing_eligible_from):
		return False

	eligible_companies = frappe.db.get_single_value('E Invoicing Settings', 'companies')
	invalid_company = doc.get('company') not in eligible_companies
	# Modified URA supply types
	invalid_supply_type = False # doc.get('gst_category') not in ["0", "1", "2", "3"] # 0: B2B 1: B2C 2: Foreigner 3: B2G
	inter_company_transaction = False # = doc.get('billing_address_gstin') == doc.get('company_gstin')
	has_non_gst_item = any(d for d in doc.get('items', []) if d.get('is_non_gst'))
	# if export invoice, then taxes can be empty
	# invoice can only be ineligible if no taxes applied and is not an export invoice
	no_taxes_applied = not doc.get('taxes') and not doc.get('gst_category') == 'Overseas'

	if invalid_company or invalid_supply_type or inter_company_transaction or no_taxes_applied or has_non_gst_item:
		frappe.log_error(f'{invalid_company}, {invalid_supply_type}, {inter_company_transaction}, {no_taxes_applied}, {has_non_gst_item}')
		return False

	frappe.log_error("** validate_einvoice_eligibility true **")
	return True

def validate_sales_invoice_submission(doc, method=""):
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if not doc.get('einvoice_status') or doc.get('einvoice_status') == 'IRN Pending':
		frappe.throw(_('You must generate IRN before submitting the document.'), title=_('Missing IRN'))

def validate_sales_invoice_cancellation(doc, method=""):
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if doc.get('einvoice_status') != 'IRN Cancelled':
		frappe.throw(_('You must cancel IRN before cancelling the document.'), title=_('Cancellation Not Allowed'))

def validate_sales_invoice_deletion(doc, method=""):
	invoice_eligible = validate_einvoice_eligibility(doc)

	if not invoice_eligible:
		return

	if doc.get('einvoice_status') != 'IRN Cancelled':
		frappe.throw(_('You must cancel IRN before deleting the document.'), title=_('Deletion Not Allowed'))

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

    for row in gst_accounts:
        for fieldname in GST_ACCOUNT_FIELDS:
            if not (value := row.get(fieldname)):
                continue

            if not account_wise:
                result.setdefault(fieldname, []).append(value)
            else:
                result[value] = fieldname

    return result