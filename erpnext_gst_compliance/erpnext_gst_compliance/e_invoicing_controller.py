# Copyright (c) 2021, Frappe and contributors
# For license information, please see license.txt

import six
import frappe
from frappe import _
from erpnext_gst_compliance.utils import safe_load_json
from frappe.utils.data import now_datetime, get_link_to_form, time_diff_in_hours
from erpnext_gst_compliance.erpnext_gst_compliance.doctype.e_invoice.e_invoice import create_einvoice, get_einvoice

def parse_sales_invoice(sales_invoice):
	if isinstance(sales_invoice, six.string_types):
		sales_invoice = safe_load_json(sales_invoice)
		if not isinstance(sales_invoice, dict):
			frappe.throw(_('Invalid Argument: Sales Invoice')) # TODO: better message
		sales_invoice = frappe._dict(sales_invoice)

	return sales_invoice

def get_service_provider_connector():
	service_provider = frappe.db.get_single_value('E Invoicing Settings', 'service_provider')
	controller = frappe.get_doc(service_provider)
	connector = controller.get_connector()

	return connector

@frappe.whitelist()
def generate_irn(sales_invoice):
	sales_invoice = parse_sales_invoice(sales_invoice)
	validate_irn_generation(sales_invoice)
	connector = get_service_provider_connector()

	einvoice = create_einvoice(sales_invoice.name)
	success, errors = connector.generate_irn(einvoice)

	if not success:
		frappe.throw(errors, title=_('EFRIS Generation Failed'), as_list=1)
	else:
		frappe.msgprint(_("EFRIS Generated Successfully."), alert=1)

	return success

def validate_irn_generation(sales_invoice):
	if sales_invoice.e_invoice:
		irn = frappe.db.get_value('E Invoice', sales_invoice.e_invoice, 'irn')
		if irn:
			msg = _('EFRIS is already generated for the Sales Invoice.') + ' '
			msg += _('Check E-Invoice {} for more details.').format(get_link_to_form('E Invoice', sales_invoice.e_invoice))
			frappe.throw(msg=msg, title=_('Invalid Request'))

@frappe.whitelist()
def cancel_irn(sales_invoice, reason, remark):
	sales_invoice = parse_sales_invoice(sales_invoice)
	connector = get_service_provider_connector()

	einvoice = get_einvoice(sales_invoice.name)
	validate_irn_cancellation(einvoice)
	success, errors = connector.cancel_irn(einvoice, reason, remark)

	if not success:
		frappe.throw(errors, title=_('EFRIS Cancellation Failed'), as_list=1)
	else:
		msg = "EFRIS Credit Note Application Submitted Successfully." + "\n"
		msg = msg + "EFRIS will only be cancelled after URA Approval." + "\n"

		frappe.msgprint(_(msg), alert=1)

	return success

def validate_irn_cancellation(einvoice):
	#if time_diff_in_hours(now_datetime(), einvoice.ack_date) > 24:
	#	frappe.throw(_('E-Invoice cannot be cancelled after 24 hours of IRN generation.'),
	#		title=_('Invalid Request'))

	if not einvoice.irn:
		frappe.throw(_('EFRIS not found. You must generate EFRIS before cancelling.'),
			title=_('Invalid Request'))
	
	if einvoice.irn_cancelled:
		frappe.throw(_('EFRIS is already cancelled. You cannot cancel e-invoice twice.'),
			title=_('Invalid Request'))

@frappe.whitelist()
def generate_eway_bill(sales_invoice_name, **kwargs):
	connector = get_service_provider_connector()

	eway_bill_details = frappe._dict(kwargs)
	einvoice = get_einvoice(sales_invoice_name)
	einvoice.set_eway_bill_details(eway_bill_details)
	success, errors = connector.generate_eway_bill(einvoice)

	if not success:
		frappe.throw(errors, title=_('E-Way Bill Generation Failed'), as_list=1)
	else:
		frappe.msgprint(_("E-Way Bill Generated Successfully."), alert=1)

	return success

# cancel ewaybill api is currently not supported by E-Invoice Portal

# @frappe.whitelist()
# def cancel_ewaybill(sales_invoice_name, reason, remark):
# 	connector = get_service_provider_connector()

# 	einvoice = get_einvoice(sales_invoice_name)
# 	success, errors = connector.cancel_ewaybill(einvoice, reason, remark)

# 	if not success:
# 		frappe.throw(errors, title=_('E-Way Bill Cancellation Failed'), as_list=1)

# 	return success


@frappe.whitelist()
def cancel_ewaybill(sales_invoice_name):
	einvoice = get_einvoice(sales_invoice_name)

	einvoice.ewaybill = ''
	einvoice.ewaybill_cancelled = 1
	einvoice.status = 'E-Way Bill Cancelled'
	einvoice.flags.ignore_validate_update_after_submit = 1
	einvoice.flags.ignore_permissions = 1
	einvoice.save()