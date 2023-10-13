import re
import os
import io
import base64
import frappe

from frappe import _
from json import dumps
from pyqrcode import create as qrcreate
from frappe.utils.data import get_link_to_form
from erpnext_gst_compliance.utils import log_exception
from erpnext_gst_compliance.efris_utils import efris_log_info, get_ug_time_str, to_ug_datetime
from frappe.integrations.utils import make_post_request, make_get_request
from frappe.utils.data import add_to_date, time_diff_in_seconds, now_datetime
import erpnext_gst_compliance.efris_utils
import json
from datetime import datetime

class ErpChampionsConnector:
	def __init__(self, gstin):

		self.gstin = gstin
		self.settings = frappe.get_cached_doc("ERP Champions Settings")
		self.credentials = self.get_user_credentials()
		# self.host = self.get_host_url()
		# self.endpoints = self.get_endpoints()

		self.validate()

	def get_user_credentials(self):
		return next(filter(lambda row: row.gstin == self.gstin, self.settings.credentials), frappe._dict())

	def get_host_url(self):
		if self.settings.sandbox_mode:
			# Modify to have real URA endpoints
			return "https://efristest.ura.go.ug/efrisws/ws/taapp/getInformation"
		else:
			return "https://efris.ura.go.ug/efrisws/ws/taapp/getInformation"

	def get_endpoints(self):
		return frappe._dict({
			"authenticate": 'https://gsp.adaequare.com/gsp/authenticate?grant_type=token',
			"generate_irn": self.host + '/enriched/ei/api/invoice',
			"cancel_irn": self.host + '/enriched/ei/api/invoice/cancel',
			"irn_details": self.host + '/enriched/ei/api/invoice/irn',
			"gstin_details": self.host + '/enriched/ei/api/master/gstin',
			"cancel_ewaybill": self.host + '/enriched/ei/api/ewayapi',
			"generate_ewaybill": self.host + '/enriched/ei/api/ewaybill',
		})

	def validate(self):
		if not self.settings.enabled:
			frappe.throw(_("EFRIS is not enabled. Please configure ERP Champions Settings and try again."))
		
		if not self.credentials:
			settings_form = get_link_to_form('ERP Champions Settings', 'ERP Champions Settings')
			frappe.throw(_("Cannot find EFRIS Credentials for selected Company GSTIN {}. Please check {}.").format(self.gstin, settings_form))

	@log_exception
	def make_request(self, req_type, url, headers, payload):
		if req_type == 'post':
			response = make_post_request(url, headers=headers, data=payload)
		else:
			response = make_get_request(url, headers=headers, data=payload)
			
		self.log_einvoice_request(url, headers, payload, response)
		
		return response

	def log_einvoice_request(self, url, headers, payload, response):
		headers.update({ 'password': self.credentials.password })
		request_log = frappe.get_doc({
			"doctype": "E Invoice Request Log",
			"user": frappe.session.user,
			"reference_invoice": self.einvoice.name,
			"url": url,
			"headers": dumps(headers, indent=4) if headers else None,
			"data": dumps(payload, indent=4) if isinstance(payload, dict) else payload,
			"response": dumps(response, indent=4) if response else None
		})
		request_log.save(ignore_permissions=True)
		frappe.db.commit()

	@log_exception
	def fetch_auth_token(self):
		client_id = self.settings.client_id or frappe.conf.einvoice_client_id
		client_secret = self.settings.get_password('client_secret') or frappe.conf.einvoice_client_secret
		headers = {
			'gspappid': client_id,
			'gspappsecret': client_secret
		}
		url = self.endpoints.authenticate
		res = self.make_request('post', url, headers, None)
		self.handle_successful_token_generation(res)

	@log_exception
	def handle_successful_token_generation(self, res):
		self.settings.auth_token = "{} {}".format(res.get('token_type'), res.get('access_token'))
		self.settings.token_expiry = add_to_date(None, seconds=res.get('expires_in'))
		self.settings.save(ignore_permissions=True)
		self.settings.reload()
		frappe.db.commit()

	@log_exception
	def get_auth_token(self):
		if time_diff_in_seconds(self.settings.token_expiry, now_datetime()) < 150.0:
			self.fetch_auth_token()

		return self.settings.auth_token

	@log_exception
	def get_headers(self):
		return {
			'content-type': 'application/json',
			'user_name': self.credentials.username,
			'password': self.credentials.get_password(),
			'gstin': self.credentials.gstin,
			'authorization': self.get_auth_token(),
			'requestid': str(base64.b64encode(os.urandom(18))),
		}

	@log_exception
	def make_irn_request(self):
		efris_log_info("make_irn_request()..")
		# headers = self.get_headers()
		# url = self.endpoints.generate_irn

		einvoice_json = self.einvoice.get_einvoice_json()
		#frappe.log_error(title="ErpChampionsConnector Einvoice", message=einvoice_json)
		efris_log_info("einvoice_json" + str(einvoice_json))

		# response = self.make_request('post', url, headers, payload)
		status, response = erpnext_gst_compliance.efris_utils.make_post("T109", einvoice_json)
		#frappe.log_error(str(response[1]))
		erpnext_gst_compliance.efris_utils.efris_log_info("response:")
		erpnext_gst_compliance.efris_utils.efris_log_info(response)
  
		sucess, errors = self.handle_irn_generation_response(status, response)
		return sucess, errors

	@staticmethod
	@log_exception
	def generate_irn(einvoice):
		efris_log_info("(generate_irn)()")
		gstin = einvoice.seller_gstin
		efris_log_info("(gstin:" + str(gstin))
		connector = ErpChampionsConnector(gstin)
		connector.einvoice = einvoice
		success, errors = connector.make_irn_request()

		return success, errors

	@log_exception
	# TODO: Change the handling to reflect what URA has
	def handle_irn_generation_response(self, status, response):

		if status == True:

			# Fix to remove characters that fail at 2174
			# response_letter_array = list(response)
			# del response_letter_array[2174]
			# del response_letter_array[2174]
			# response_letter_array = "".join(response_letter_array)
			# response = json.loads(response_letter_array)

			self.handle_successful_irn_generation(response)
		
		# if response.get('success'):
		# 	govt_response = response.get('result')
		# 	self.handle_successful_irn_generation(govt_response)
		# elif '2150' in response.get('message'):
		# 	govt_response = response.get('result')
		# 	self.handle_irn_already_generated(govt_response)
		# else:
		# 	errors = response.get('message')
		# 	errors = self.sanitize_error_message(errors)
		# 	return False, errors

			return True, []
		else:
			# throw back error to controller (will show error message)
			return False, response

	def handle_successful_irn_generation(self, response):
		status = 'EFRIS Generated'
		# Default values
		irn = invoice_id = antifake_code = qrcode = invoice_date = None
		seller_address = seller_trade_name = seller_legal_name = nin_brn = seller_email = seller_phone = None
		buyer_trade_name = buyer_legal_name = buyer_gstin = None

		try:
			# URA returned fields
			irn = response["basicInformation"]["invoiceNo"]
			invoice_id = response["basicInformation"]["invoiceId"]
			antifake_code = response["basicInformation"]["antifakeCode"]
			qrcode = self.generate_qrcode(response["summary"]["qrCode"])
			invoice_datetime = response["basicInformation"]["issuedDate"]
			efris_log_info("invoice_date:" + str(invoice_date))
			invoice_datetime = datetime.strptime(invoice_date, '%d/%m/%Y %H:%M:%S')
			invoice_date = invoice_datetime.date()
			invoice_time = invoice_datetime.time()


			# seller details
			seller_address = response["sellerDetails"]["address"]
			seller_trade_name = response["sellerDetails"]["businessName"]
			seller_legal_name = response["sellerDetails"]["legalName"]
			nin_brn = response["sellerDetails"]["ninBrn"]
			seller_email = response["sellerDetails"]["emailAddress"]
			seller_phone = response["sellerDetails"]["mobilePhone"]

			# buyer details
			buyer_trade_name = response["buyerDetails"]["buyerBusinessName"]
			buyer_legal_name = response["buyerDetails"]["buyerLegalName"]
			buyer_gstin = response["buyerDetails"]["buyerTin"]

		except KeyError as e:
			print(f"Error fetching data from response JSON: Missing key {e}")
		except Exception as e:
			print(f"Unexpected error occurred: {e}")

		finally:		
						
			self.einvoice.update({
				'irn': irn,
				'invoice_id': invoice_id,
				'antifake_code': antifake_code,
				'status': status,
				'qrcode_path': qrcode,
				'invoice_date': invoice_date,
				'issued_time': invoice_time,
				'seller_trade_name': seller_trade_name,
				'seller_legal_name': seller_legal_name,
				'seller_nin_or_brn': nin_brn,
				'seller_address': seller_address,
				'seller_email': seller_email,
				'seller_phone': seller_phone,
				'buyer_trade_name': buyer_trade_name,
				'buyer_legal_name': buyer_legal_name,
				'buyer_gstin': buyer_gstin,
			})
			self.einvoice.flags.ignore_permissions = 1
			self.einvoice.submit()

	def generate_qrcode(self, signed_qrcode):
		doctype = self.einvoice.doctype
		docname = self.einvoice.name
		filename = '{} - QRCode.png'.format(docname).replace(os.path.sep, "__")
		qr_image = io.BytesIO()
		url = qrcreate(signed_qrcode, error='L')
		url.png(qr_image, scale=2, quiet_zone=1)
		_file = frappe.get_doc({
		'doctype': 'File',
		'file_name': filename,
		'attached_to_doctype': doctype,
		'attached_to_name': docname,
		'attached_to_field': 'qrcode_path',
		'is_private': 0,
		'content': qr_image.getvalue()
		})
		_file.save()
		return _file.file_url

	def handle_irn_already_generated(self, response):
		# IRN already generated but not updated in invoice
		# Extract the IRN from the response description and fetch irn details
		irn = response[0].get('Desc').get('Irn')
		success, irn_details = self.make_get_irn_details_request(irn)
		if success:
			self.handle_successful_irn_generation(irn_details)
	
	def sanitize_error_message(self, message):
		'''
			On validation errors, response message looks something like this:
			message = '2174 : For inter-state transaction, CGST and SGST amounts are not applicable; only IGST amount is applicable,
						3095 : Supplier GSTIN is inactive'
			we search for string between ':' to extract the error messages
			errors = [
				': For inter-state transaction, CGST and SGST amounts are not applicable; only IGST amount is applicable, 3095 ',
				': Test'
			]
			then we trim down the message by looping over errors
		'''
		if not message:
			return []

		if not ' : ' in message:
			return [message]

		errors = re.findall(' : [^:]+', message)
		for idx, e in enumerate(errors):
			# remove colons
			errors[idx] = errors[idx].replace(':', '').strip()
			# if not last
			if idx != len(errors) - 1:
				# remove last 7 chars eg: ', 3095 '
				errors[idx] = errors[idx][:-6]

		return errors

	@log_exception
	def make_get_irn_details_request(self, irn):
		headers = self.get_headers()
		url = self.endpoints.irn_details

		params = '?irn={irn}'.format(irn=irn)
		response = self.make_request('get', url + params, headers, None)

		if response.get('success'):
			return True, response.get('result')
		else:
			errors = response.get('message')
			errors = self.sanitize_error_message(errors)
			return False, errors

	@log_exception
	def make_cancel_irn_request(self, reason, remark):
		efris_log_info ("make_cancel_irn_request. reason/remark" + str(reason) + "/" + str(remark) )
		
		einvoice_credit_copy = self.einvoice
		for index, item in enumerate(einvoice_credit_copy.items):
			einvoice_credit_copy.items[index].quantity = - abs(item.quantity)
			einvoice_credit_copy.items[index].tax = - abs(item.tax)
			einvoice_credit_copy.items[index].amount = - abs(item.amount)

		for index, tax_item in enumerate(einvoice_credit_copy.taxes):
			einvoice_credit_copy.taxes[index].net_amount = -abs(tax_item.net_amount)
			einvoice_credit_copy.taxes[index].tax_amount = -abs(tax_item.tax_amount)
			einvoice_credit_copy.taxes[index].gross_amount = -abs(tax_item.gross_amount)

		einvoice_credit_copy.net_amount = -abs(einvoice_credit_copy.net_amount)
		einvoice_credit_copy.tax_amount = -abs(einvoice_credit_copy.tax_amount)
		einvoice_credit_copy.gross_amount = -abs(einvoice_credit_copy.gross_amount)
		#einvoice_credit_copy.name = einvoice_credit_copy.name + "-CAN"
		einvoice_credit_copy.status = "EFRIS Credit Note Pending"
		


		efris_log_info("creating copy of credit note done...:" + str(self.einvoice.currency_code))

		credit_note = {
			"oriInvoiceId": self.einvoice.invoice_id,
			"oriInvoiceNo": self.einvoice.irn,
			"reasonCode": reason,
			"reason": "",
			"applicationTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
			"invoiceApplyCategoryCode": "101",
			"currency": 'UGX', #TODO remove hardcode
			"contactName": "",
			"contactMobileNum": "",
			"contactEmail": "",
			"source": "103",
			"remarks": remark,
			"sellersReferenceNo": self.einvoice.seller_reference_no
		}
		item_list = []
		for item in self.einvoice.items:
			item_list.append({
				"item": item.item_name,
				"itemCode": item.item_name,
				"qty": item.quantity,
				"unitOfMeasure": frappe.get_doc("UOM",item.unit).efris_uom_code,
				"unitPrice": item.rate,
				"total": item.amount,
				"taxRate": str(item.gst_rate),
				"tax": item.tax,
				"orderNumber": str(item.order_number),
				"deemedFlag": "2",
				"exciseFlag": "2",
				"categoryId": "",
				"categoryName": "",
				"goodsCategoryId": item.gst_hsn_code,
				"goodsCategoryName": "",
				"exciseRate": "",
				"exciseRule": "",
				"exciseTax": "",
				"pack": "",
				"stick": "",
				"exciseUnit": "",
				"exciseCurrency": "",
				"exciseRateName": "",
				"vatApplicableFlag": "1"
			})
   
		credit_note.update({"goodsDetails": item_list})
  
		tax_list = []
		for tax in self.einvoice.taxes:
			tax_list.append({
				"taxCategoryCode": tax.tax_category_code,
				"netAmount": tax.net_amount,
				"taxRate": str(tax.tax_rate),
				"taxAmount": tax.tax_amount,
				"grossAmount": tax.gross_amount,
				"exciseUnit": tax.excise_unit,
				"exciseCurrency": tax.excise_currency,
				"taxRateName": tax.tax_rate_name
			})
   
		credit_note.update({"taxDetails": tax_list})
		credit_note.update({"summary": {
			"netAmount": self.einvoice.net_amount,
			"taxAmount": self.einvoice.tax_amount,
			"grossAmount": self.einvoice.gross_amount,
			"itemCount": str(self.einvoice.item_count),
			"modeCode": "0",
			"qrCode": self.einvoice.qrcode_path
		}})
		credit_note.update({"buyerDetails": {
			"buyerTin": self.einvoice.buyer_gstin,
			"buyerNinBrn": "",
			"buyerPassportNum": "",
			"buyerLegalName": "",
			"buyerBusinessName": "",
			"buyerAddress": "",
			"buyerEmail": "",
			"buyerMobilePhone": "",
			"buyerLinePhone": "",
			"buyerPlaceOfBusi": "",
			"buyerType": "1",
			"buyerCitizenship": "1",
			"buyerSector": "1",
			"buyerReferenceNo": ""
		}})
		credit_note.update({"payWay": [
			{
				"paymentMode": "101",
				"paymentAmount": self.einvoice.gross_amount,
				"orderNumber": "a"
			}
		]})
		credit_note.update({"importServicesSeller": {
			"importBusinessName": "",
			"importEmailAddress": "",
			"importContactNumber": "",
			"importAddress": "",
			"importInvoiceDate": "",
			"importAttachmentName": "",
			"importAttachmentContent": ""
		}})
		credit_note.update({"basicInformation": {
			"operator": self.einvoice.operator,
			"invoiceKind": "1",
			"invoiceIndustryCode": "102",
			"branchId": ""
		}})
  
		#frappe.log_error("Credit Note JSON BEFORE: ", credit_note)
		# Add needed fields
	

		# Make fields negative

		# GoodsDetails
		for index, item in enumerate(credit_note["goodsDetails"]):
			credit_note["goodsDetails"][index]["qty"] = str(-abs(int(credit_note["goodsDetails"][index]["qty"])))
			credit_note["goodsDetails"][index]["total"] = str(-abs(float(credit_note["goodsDetails"][index]["total"])))
			credit_note["goodsDetails"][index]["tax"] = str(-abs(float(credit_note["goodsDetails"][index]["tax"])))
			
		# TaxDetails
		for index, tax in enumerate(credit_note["taxDetails"]):
			credit_note["taxDetails"][index]["netAmount"] = str(-abs(float(credit_note["taxDetails"][index]["netAmount"])))
			credit_note["taxDetails"][index]["taxAmount"] = str(-abs(float(credit_note["taxDetails"][index]["taxAmount"])))
			credit_note["taxDetails"][index]["grossAmount"] = str(-abs(float(credit_note["taxDetails"][index]["grossAmount"])))
   
		# Summary
		credit_note['summary']['netAmount'] = str(-abs(float(credit_note['summary']['netAmount'])))
		credit_note['summary']['taxAmount'] = str(-abs(float(credit_note['summary']['taxAmount'])))
		credit_note['summary']["grossAmount"] = str(-abs(float(credit_note['summary']["grossAmount"])))
  
		# Payway
		credit_note["payWay"][0]["paymentAmount"] = str(-abs(float(credit_note["payWay"][0]["paymentAmount"])))
  
		frappe.log_error("Credit Note JSON AFTER: ", credit_note)

		status, response = erpnext_gst_compliance.efris_utils.make_post("T110", credit_note)
  
		
		sucess, errors = self.handle_irn_cancellation_response(status, response)

		try:
		
			einv = frappe.new_doc('E Invoice')
			einv = einvoice_credit_copy

			#einv.flags.ignore_validate_update_after_submit = 1
			einv.flags.ignore_permissions = 1
			efris_log_info("BEFORE Save creditnote einvoice")
			#einv.save()
			#frappe.db.commit()
			efris_log_info("AFTER Save creditnote einvoice")
		except Exception as e:
			frappe.log_error("E Invoice Credit Note SAVE Error: ", e)
		return sucess, errors

	@log_exception
	def handle_irn_cancellation_response(self, status, response):
		if status:
			try: 
				self.handle_successful_irn_cancellation(response)
			except Exception as e:
				frappe.log_error("E Invoice Cancellation Error: ", e)
			return True, []
		else:
			return False, "Something went wrong"

	def handle_successful_irn_cancellation(self, response):
		
		credit_note_appl_ref = response["referenceNo"]
		efris_log_info("credit_note_appl_ref:" + str(credit_note_appl_ref))
		self.einvoice.credit_note_application_ref_no =credit_note_appl_ref
		#self.einvoice.irn_cancelled = 1
		#self.einvoice.irn_cancel_date = datetime.now()
		#self.einvoice.status = 'IRN Cancelled'
		self.einvoice.credit_note_approval_status = "102:Submitted"
		formatted_date = get_ug_time_str()
		efris_log_info("formatted_date:" + str(formatted_date))
		self.einvoice.credit_note_application_date =  formatted_date
		self.einvoice.status = "EFRIS Credit Note Pending"
		self.einvoice.flags.ignore_validate_update_after_submit = 1
		self.einvoice.flags.ignore_permissions = 1
		self.einvoice.save()

	@staticmethod
	@log_exception
	def cancel_irn(einvoice, reason, remark):
		gstin = einvoice.seller_gstin
		connector = ErpChampionsConnector(gstin)
		connector.einvoice = einvoice
		success, errors = connector.make_cancel_irn_request(reason, remark)

		return success, errors
	
	
	@log_exception
	def make_confirm_irn_cancellation_request(self):
		efris_log_info ("make_confirm_irn_cancellation_request")
		credit_note_application_query ={
								"referenceNo": self.einvoice.credit_note_application_ref_no,
								"oriInvoiceNo": "",
								"invoiceNo": "",
								"combineKeywords": "",
								"approveStatus": "",
								"queryType": "1",
								"invoiceApplyCategoryCode": "",
								"startDate": "",
								"endDate": "",
								"pageNo": "1",
								"pageSize": "10" ,
								"creditNoteType": "",
								"branchName": "",
								"sellerTinOrNin": "",
								"sellerLegalOrBusinessName": ""
							}
		frappe.log_error("Confirm Request: ", credit_note_application_query)

		status, response = erpnext_gst_compliance.efris_utils.make_post("T111", credit_note_application_query)
  		
		sucess, errors = self.handle_confirm_irn_cancellation_response(status, response)
		return sucess, errors

	@log_exception
	def handle_confirm_irn_cancellation_response(self, status, response):
		if status:
			try: 
				sucess, errors = self.handle_successful_confirm_irn_cancellation(response)
			except Exception as e:
				frappe.log_error("E Invoice Confirm Cancellation Error: ", e)
			return True, errors
		else:
			return False, "Something went wrong"

	def handle_successful_confirm_irn_cancellation(self, response):
		
		page_count = response["page"]["pageCount"]
		efris_log_info("page_count:" + str(page_count))

		if not page_count:
			return False, "Credit Note Application Reference not found!"
		approve_status = response["records"][0]["approveStatus"]
		efris_log_info("approve_status:" + str(approve_status))

		if approve_status == '102': #no change
			return True, "Pending URA Approval"
		
		if approve_status == '101': #approved
			credit_invoice_no = response["records"][0]["invoiceNo"]
			efris_log_info("credit_invoice_no:" + str(credit_invoice_no))	
			self.einvoice.credit_note_invoice_no =credit_invoice_no
			self.einvoice.irn_cancelled = 1
			self.einvoice.irn_cancel_date = datetime.now() # TODO Credit Note Invoice Issue Date
			self.einvoice.credit_note_approval_status = "101:Approved"
			#self.einvoice.status = "EFRIS Cancelled"

			#get invoice details
			invoice_details_content = {"invoiceNo":self.einvoice.credit_note_invoice_no}
			status, response = erpnext_gst_compliance.efris_utils.make_post("T108", invoice_details_content)
			if status:
				try: 
					
					# URA returned fields for the credit note
					invoice_id = response["basicInformation"]["invoiceId"]
					antifake_code = response["basicInformation"]["antifakeCode"]
					qrcode = self.generate_qrcode(response["summary"]["qrCode"])
					efris_log_info("invoice_id/antifake_code: " + str(invoice_id) + "/" + str(antifake_code) )
				except Exception as e:
					frappe.log_error("E Invoice Confirm Cancellation Error: ", e)
				return True, ""
			else:
				return False, "Something went wrong"
		
			self.einvoice.flags.ignore_validate_update_after_submit = 1
			self.einvoice.flags.ignore_permissions = 1
			self.einvoice.save()

			return True, "Credit Note Approved! New Credit Note Invoice No: " + str(self.einvoice.credit_note_invoice_no) 

	@staticmethod
	@log_exception
	def confirm_irn_cancellation(einvoice):
		gstin = einvoice.seller_gstin
		connector = ErpChampionsConnector(gstin)
		connector.einvoice = einvoice
		success, errors = connector.make_confirm_irn_cancellation_request()

		return success, errors		

	@log_exception
	def make_eway_bill_request(self):
		headers = self.get_headers()
		url = self.endpoints.generate_ewaybill

		eway_bill_json = self.einvoice.get_eway_bill_json()
		payload = dumps(eway_bill_json, indent=4)

		response = self.make_request('post', url, headers, payload)

		if response.get('success'):
			govt_response = response.get('result')
			self.handle_successful_ewaybill_generation(govt_response)
		else:
			errors = response.get('message')
			errors = self.sanitize_error_message(errors)
			return False, errors

		return True, []

	def handle_successful_ewaybill_generation(self, response):
		self.einvoice.ewaybill = response.get('EwbNo')
		self.einvoice.ewaybill_validity = response.get('EwbValidTill')
		self.einvoice.status = 'E-Way Bill Generated'
		self.einvoice.flags.ignore_validate_update_after_submit = 1
		self.einvoice.flags.ignore_permissions = 1
		self.einvoice.save()

	@staticmethod
	@log_exception
	def generate_eway_bill(einvoice):
		gstin = einvoice.seller_gstin
		connector = ErpChampionsConnector(gstin)
		connector.einvoice = einvoice
		success, errors = connector.make_eway_bill_request()

		return success, errors

	@log_exception
	def make_cancel_ewaybill_request(self, reason, remark):
		headers = self.get_headers()
		url = self.endpoints.cancel_ewaybill

		ewaybill = self.einvoice.ewaybill

		payload = {'ewbNo': ewaybill, 'cancelRsnCode': reason, 'cancelRmrk': remark}
		payload = dumps(payload, indent=4)

		response = self.make_request('post', url, headers, payload)

		if response.get('success'):
			self.handle_successful_ewaybill_cancellation()
		else:
			errors = response.get('message')
			errors = self.sanitize_error_message(errors)
			return False, errors

		return True, []

	def handle_successful_ewaybill_cancellation(self):
		self.einvoice.ewaybill = ''
		self.einvoice.ewaybill_cancelled = 1
		self.einvoice.status = 'E-Way Bill Cancelled'
		self.einvoice.flags.ignore_validate_update_after_submit = 1
		self.einvoice.flags.ignore_permissions = 1
		self.einvoice.save()

	@staticmethod
	@log_exception
	def cancel_ewaybill(einvoice, reason, remark):
		gstin = einvoice.seller_gstin
		connector = ErpChampionsConnector(gstin)
		connector.einvoice = einvoice
		success, errors = connector.make_cancel_ewaybill_request(reason, remark)

		return success, errors