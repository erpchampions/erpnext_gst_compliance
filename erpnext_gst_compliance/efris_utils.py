#import frappe
#from frappe import _
import random
import hashlib
import uuid
import json
import base64
import requests
from datetime import datetime
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
from Crypto.Cipher import AES
from Crypto.Signature import PKCS1_v1_5 as PKCS1_v1_5_Signature
from Crypto.Util.Padding import pad, unpad
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from Crypto.Hash import SHA1
from cryptography.hazmat.primitives import padding
import OpenSSL
import os
#from frappe.utils import get_site_path
import logging
logging.basicConfig(filename='/home/frappe/frappe-bench/logs/efris_logfile3.log', level=logging.DEBUG)
from datetime import datetime
import pytz
from collections import defaultdict


#logging.info("This is an info message")
#logging.warning("This is a warning message")
#logging.error("This is an error message")

def efris_log_info(message):
    logging.info(message)

def efris_log_warning(message):
    logging.warning(message)

def efris_log_error(message):
    logging.error(message)

def encrypt_aes_ecb(content, key):
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(json.dumps(content).encode()) + padder.finalize()
    encrypted_content = encryptor.update(padded_data) + encryptor.finalize()
    return encrypted_content

def make_post(interface_code, content):
    data = fetch_data()
    print("Data done:", data)
    aes_key, errorMsg = get_aes_key()
    print("aes_key done:", aes_key)
    efris_log_info("aes_key done")

    if errorMsg != "":
        return False, errorMsg
    
    # Encrypt the content using AES-128-ECB
    encrypted_content = encrypt_aes_ecb(content, aes_key)
    b64_encrypted_content = base64.b64encode(encrypted_content).decode()

    print("Content to encrypt:", json.dumps(content))
    print("Encrypted content:", b64_encrypted_content)

    data["globalInfo"]["interfaceCode"] = interface_code
    data["data"]["content"] = b64_encrypted_content
    data["data"]["dataDescription"]["codeType"] = "1"
    data["data"]["dataDescription"]["encryptCode"] = "2"

    private_key = get_private_key()
    # Sign the encrypted content
    # sign the data
    signature = OpenSSL.crypto.sign(private_key, b64_encrypted_content, "sha1")

    if signature:
        # print the base64-encoded signature
        b4signature = base64.b64encode(signature).decode()

        # add signature to data
        data["data"]["signature"] = b4signature

    print(data)
    efris_log_info(data)
    data = json.dumps(data).replace("'", '"').replace("\n", "").replace("\r", "")
    efris_log_info("Make Post - post_req() with:" + data)

    json_resp = post_req(data)
    try:
        resp = json.loads(json_resp)
        errorMsg = resp["returnStateInfo"]["returnMessage"]
        efris_log_info("returnStateInfoMsg:" + errorMsg)
        if errorMsg != "SUCCESS":
            return False, errorMsg
        
        respcontent = resp["data"]["content"]
        efris_response=decrypt_aes_ecb(aes_key,respcontent)
        print("Decrypted EFRIS response:",efris_response)
        efris_log_info("Decrypted EFRIS response: "+ efris_response)
        return True, efris_response
    except json.decoder.JSONDecodeError:
        print("Error: Could not decode JSON data")
        efris_log_info("Error: Could not decode JSON data")
        exit(1)
    except:
        respcontentfailed = resp["returnStateInfo"]
        print(respcontentfailed)
        exit(1)



def decrypt_aes_ecb(ciphertext,aeskey):
    print("Encrypted data:", ciphertext)
    print("Decryption key:", aeskey)
    # Decode the ciphertext from base64
    ciphertext = base64.b64decode(ciphertext)

    # Create an AES cipher object with the given key and mode
    cipher = AES.new(aeskey, AES.MODE_ECB)

    # Decrypt the ciphertext
    plaintext = cipher.decrypt(ciphertext).decode()
    
    print("Decrypted data:", plaintext)
    
    return plaintext        


def get_ug_time_str():
    ug_time_zone = "Africa/Kampala"
    now = datetime.now()#.strftime("%Y-%m-%d %H:%M:%S")
    
    # Convert the current time to the Uganda time zone
    uganda_time = now.astimezone(pytz.timezone(ug_time_zone))
    uganda_time_str = uganda_time.strftime("%Y-%m-%d %H:%M:%S")   

    return  uganda_time_str

def fetch_data():
    now = get_ug_time_str() #datetime.now().strftime("%Y-%m-%d %H:%M:%S")     
    return {
        "data": {
            "content": "",
            "signature": "",
            "dataDescription": {
                "codeType": "0",
                "encryptCode": "1",
                "zipCode": "0"
            }
        },
        "globalInfo": {
            "appId": "AP04",
            "version": "1.1.20191201",
            "dataExchangeId": "9230489223014123",
            "interfaceCode": "T101",
            "requestTime": now,
            "requestCode": "TP",
            "responseCode": "TA",
            "userName": "admin",
            "deviceMAC": "FFFFFFFFFFFF",
            "deviceNo": "1002170340_01",
            "tin": "1002170340",
            "brn": "",
            "taxpayerID": "1",
            "longitude": "116.397128",
            "latitude": "39.916527",
            "extendField": {
                "responseDateFormat": "dd/MM/yyyy",
                "responseTimeFormat": "dd/MM/yyyy HH:mm:ss"
            }
        },
        "returnStateInfo": {
            "returnCode": "",
            "returnMessage": ""
        }
    }

def get_aes_key():
    errorMsg = ""
    # GET AES KEY
    data = fetch_data()
    deviceNo = "1002170340_01"
    tin = "1002170340"
    brn = ""
    #dataExchangeId = guidv4()
    dataExchangeId = hashlib.sha256(str(uuid.uuid4()).encode('utf-8')).hexdigest()[:32]
    
    data["globalInfo"]["interfaceCode"] = "T104"
    data["globalInfo"]["dataExchangeId"] = dataExchangeId
    data["globalInfo"]["deviceNo"] = deviceNo
    data["globalInfo"]["tin"] = tin
    data["globalInfo"]["brn"] = brn

    data = json.dumps(data).replace("'", '"').replace("\n", "").replace("\r", "")
    resp = post_req(data)
    try:
        jsonresp = json.loads(resp)
        efris_log_info("aes OK:" + resp)
        errorMsg = jsonresp["returnStateInfo"]["returnMessage"]
        efris_log_info("aes returnStateInfoMsg:" + errorMsg)
        if errorMsg != "SUCCESS":
            return "", errorMsg


    except json.decoder.JSONDecodeError:
        print("Error: Could not decode JSON data")
        efris_log_info("aes error ")
        return "", "json.decoder.JSONDecodeError"

    b64content = jsonresp["data"]["content"]
    content = json.loads(base64.b64decode(b64content).decode("utf-8"))

    b64passowrdDes = content["passowrdDes"]
    passowrdDes = base64.b64decode(b64passowrdDes)

    # read private key
    privKey = get_private_key()
   
    # convert the pkey object to a byte string
    pkey_str = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, privKey)

    cipher = PKCS1_v1_5.new(RSA.import_key(pkey_str))
    aesKey = cipher.decrypt(passowrdDes, None)

    return base64.b64decode(aesKey), ""

def post_req(data):
    efris_log_info("post_req()...starting")
    url = "https://efristest.ura.go.ug/efrisws/ws/taapp/getInformation"
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, data=data, headers=headers)
    print(response.text)
    efris_log_info("post_req()...done, response:" + response.text)
    return response.text

def post_reqs(data, url, headers):
    efris_log_info("post_req()...")
    response = requests.post(url, data=data, headers=headers)
    print(response.text)
    return response.text

def get_private_keys():
    # Get the private files directory for the current site
    private_files_path = frappe.get_site_path('private', 'files')

    # Construct the path to the key file in the ERPNext file system
    key_file_path = os.path.join(private_files_path, 'erpnext.pfx')

    # Load the PKCS#12 file
    with open(key_file_path, "rb") as f:
        pfx_data = f.read()

    # Extract the private key and certificate from the PKCS#12 file
    pfx = OpenSSL.crypto.load_pkcs12(pfx_data, b"123456")
    pkey = pfx.get_privatekey()

    efris_log_info("get_private_key()...done")
    return pkey

def get_private_key():
    # load the PKCS#12 file
    key_path = "/home/frappe/frappe-bench/sites/efristest.erpchampions.org/private/files/erpnext.pfx"    
    with open(key_path, "rb") as f:
        pfx_data = f.read()

    # extract the private key and certificate from the PKCS#12 file
    pfx = OpenSSL.crypto.load_pkcs12(pfx_data, b"123456")
    pkey = pfx.get_privatekey()

    # do something with the private key and certificate
    return pkey

def safe_load_json(message):
	try:
		json_message = json.loads(message)
	except Exception:
		json_message = message

	return json_message

def send_efris(sales_invoice):
    efris_log_info("send_efris starts..")
    #json_sales_inv = safe_load_json(sales_invoice)
    #frappe.msgprint(json_sales_inv)
    #efris_log_info("sales invoice:" + str(json_sales_inv))
    efris_inv_data = fetch_efris_data(sales_invoice)
    success, resultMsg = False, ""

    json_string = "{}"  # an empty JSON object

    try:
        data = efris_inv_data
        if not data:  # Checks if the parsed JSON data is "empty" like {}, [], "", 0, False, None
            resultMsg = "Oops! The JSON string efris_inv_data is empty or represents a non-value."            
            efris_log_info(resultMsg)
        else:
            #"Great! The JSON string efris_inv_data is not empty."
            print(str(efris_inv_data))
            frappe.msgprint(str(efris_inv_data))
            efris_log_info("efris_inv_data:" + str(efris_inv_data))
            resp_content = make_post("T109", efris_inv_data)
            resultMsg = "EFRIS response: " + str(resp_content)
            efris_log_info(resultMsg)
            success = True            
    except json.JSONDecodeError:
        resultMsg = "Oops! Invalid JSON string."
        print(resultMsg)
        efris_log_info(resultMsg)
    frappe.msgprint(resultMsg)
    return success, resultMsg

def format_amount(amount):
    amt_float = float(amount)    
    amt_string = "{:.2f}"
    return amt_string.format(amt_float)

def fetch_efris_data(sales_inv):
    if sales_inv is None:
        print("Oops! sales_inv is NONE!")
        efris_log_info("Oops! sales_inv is NONE!")
        frappe.msgprint("Oops! sales_inv is NONE!")
        return ""
    efris_log_info("fetch_efris_data started with:" + str(sales_inv))

    efris_invoice_content = fetch_test_invoice_goods_no_excise()
    efris_invoice_content["basicInformation"]["issuedDate"] = sales_inv["posting_date"]
    efris_invoice_content["basicInformation"]["operator"] = sales_inv["modified_by"]
    
    item_count = 0
    efris_invoice_content["goodsDetails"] = []
    
    #total_amounts_by_item_code = defaultdict(float)
    total_quantities_by_item_code = {}
    efris_log_info("..about to loop items")
    for item in sales_inv["items"]:
        if item['item_code'] in total_quantities_by_item_code:
            total_quantities_by_item_code[item['item_code']] += item['qty']
        else:
            total_quantities_by_item_code[item['item_code']] = item['qty']

    for item in sales_inv["items"]:
        print("Nice! Got an item...")
        efris_log_info("Nice! Got an item...")
        #frappe.msgprint("Nice! Got an item...")
        item_count = item_count + 1
        item_code = item["item_code"]
        item_name = item["item_name"]
        qty = item["qty"]
        rate = format_amount(item["rate"])        

        # Get item-wise tax details
        tax_details_str = sales_inv["taxes"][0]["item_wise_tax_detail"]
        tax_details = json.loads(tax_details_str) if tax_details_str else {}

        tax_rate, tax_amount = tax_details.get(item_code, [0.0, 0.0])
        #total_item_amount = tax_amount + item["net_amount"]
        total_item_amount = item["amount"]
        tax_rate = tax_rate / 100
        item_tax_amount = tax_amount / total_quantities_by_item_code[item["item_code"]] * qty

        #frappe.msgprint("tax_rate,tax_amount,total_item_amount:" + str(tax_rate) + " , " + str(tax_amount) + " , " + str(total_item_amount))
        
        new_item = {
            "item": item_name,
            "itemCode": item_code,
            "qty": qty,
            "unitOfMeasure": "101",
            "unitPrice": rate,
            "total": format_amount(total_item_amount),  # Use item amount as the total
            "taxRate": format_amount(tax_rate),
            "tax": format_amount(item_tax_amount),
            "discountTotal": "",
            "discountTaxRate": "0.00",
            "orderNumber": item_count - 1,
            "discountFlag": "2",
            "deemedFlag": "2",
            "exciseFlag": "2",
            "categoryId": "",
            "categoryName": "",
            "goodsCategoryId": "50151513",
            "goodsCategoryName": "Edible vegetable or plant oils",
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
            "vatProjectName": "testAskcc"
        }


        # Append the new item to the list of items.
        efris_invoice_content["goodsDetails"].append(new_item)
        efris_log_info("Done append new item...")

    
    # Set the tax amount and net amount from the taxes section
    tax_amount = format_amount(sales_inv["taxes"][0]["tax_amount"])
    net_amount = format_amount(sales_inv["net_total"])
    grand_total = format_amount(sales_inv["grand_total"])
    efris_log_info("tax_amount,net_amount,grand_total: " + format_amount(tax_amount) + ", " + format_amount(net_amount)+ ", " + format_amount(grand_total))
    inv_currency = sales_inv["currency"]

    new_tax_details_item = {
        "taxCategoryCode": "01",
        "netAmount": net_amount,
        "taxRate": format_amount(tax_rate),
        "taxAmount": tax_amount,
        "grossAmount": grand_total,
        "exciseUnit": "101",
        "exciseCurrency": inv_currency,
        "taxRateName": "123"
    }
    efris_invoice_content["taxDetails"] = []
    efris_invoice_content["taxDetails"].append(new_tax_details_item)
    
    #frappe.msgprint("tax_amount,net_amount: " + str(tax_amount) + ", " + str(net_amount))
    
    efris_invoice_content["summary"]["taxAmount"] = format_amount(tax_amount)
    efris_invoice_content["summary"]["netAmount"] = format_amount(net_amount)
    efris_invoice_content["summary"]["itemCount"] = item_count
    efris_invoice_content["summary"]["grossAmount"] = format_amount(sales_inv["grand_total"])

    efris_invoice_content["payWay"] = []
    new_payway = {
         "paymentMode": "101",
         "paymentAmount": format_amount(grand_total),
         "orderNumber": "a"
      }
    efris_invoice_content["payWay"].append(new_payway)

    efris_log_info(efris_invoice_content)
    efris_log_info("fetch_efris_data done")
    return efris_invoice_content

def fetch_test_invoice_goods_no_excise():
    random_integer = random.randint(1, 1000000000000)
    invoiceUpload_Goods_NonExcise = {
    "sellerDetails": {
      "tin": "1002170340",
      "ninBrn": "",
      "legalName": "ASK CORPORATE CONSULTS LTD",
      "businessName": "ASK CORPORATE CONSULTS LTD",
      "address": "KAMPALA",
      "mobilePhone": "15501234567",
      "linePhone": "010-6689666",
      "emailAddress": "123456@163.com",
      "placeOfBusiness": "1496 KYEBANDO ROAD BUSINESS GARDEN KAMWOKYA KAMPALA KAWEMPE DIVISION SOUTH KAWEMPE DIVISION MULAGO III",
      "referenceNo": random_integer,
      "branchId": "",
      "isCheckReferenceNo": "0",
      "branchName": "Test",
      "branchCode": ""
    },
    "basicInformation": {
      "invoiceNo": "",
      "antifakeCode": "",
      "deviceNo": "1002170340_01",
      "issuedDate": "2023-05-21 21:40:00",
      "operator": "aisino",
      "currency": "UGX",
      "oriInvoiceId": "1",
      "invoiceType": "1",
      "invoiceKind": "1",
      "dataSource": "101",
      "invoiceIndustryCode": "101",
      "isBatch": "0"
    },
    "buyerDetails": {
      "buyerTin": "1016851411",
      "buyerNinBrn": "/80020002454894",
      "buyerPassportNum": "",
      "buyerLegalName": "TECH THINGS LIMITED",
      "buyerBusinessName": "TECH THINGS LIMITED",
      "buyerAddress": "beijin",
      "buyerEmail": "123456@163.com",
      "buyerMobilePhone": "15501234567",
      "buyerLinePhone": "010-6689666",
      "buyerPlaceOfBusi": "beijin",
      "buyerType": "0",
      "buyerCitizenship": "1",
      "buyerSector": "1",
      "buyerReferenceNo": "00000000001",
      "nonResidentFlag": "0"
    },
    "buyerExtend": {
      "propertyType": "abc",
      "district": "haidian",
      "municipalityCounty": "haidian",
      "divisionSubcounty": "haidian1",
      "town": "haidian1",
      "cellVillage": "haidian1",
      "effectiveRegistrationDate": "2020-10-19",
      "meterStatus": "101"
    },
    "goodsDetails": [
      {
         "item": "pencils-10",
         "itemCode": "0008396770",
         "qty": "20",
         "unitOfMeasure": "101",
         "unitPrice": "12000.00",
         "total": "240000.00",
         "taxRate": "0.18",
         "tax": "36610.17",
         "discountTotal": "",
         "discountTaxRate": "0.00",
         "orderNumber": "0",
         "discountFlag": "2",
         "deemedFlag": "2",
         "exciseFlag": "2",
         "categoryId": "",
         "categoryName": "",
         "goodsCategoryId": "50151513",
         "goodsCategoryName": "Edible vegetable or plant oils",
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
         "vatProjectName": "testAskcc"
      }
    ],
    "taxDetails": [
      {
         "taxCategoryCode": "01",
         "netAmount": "203389.83",
         "taxRate": "0.18",
         "taxAmount": "36610.17",
         "grossAmount": "240000.00",
         "exciseUnit": "101",
         "exciseCurrency": "UGX",
         "taxRateName": "123"
      }
    ],
    "summary": {
      "netAmount": "203389.83",
      "taxAmount": "36610.17",
      "grossAmount": "240000.00",
      "itemCount": "1",
      "modeCode": "0",
      "remarks": "Test Askcc invoice.",
      "qrCode": ""
    },
    "payWay": [
      {
         "paymentMode": "101",
         "paymentAmount": "240000.00",
         "orderNumber": "a"
      }
    ],
    "extend": {
      "reason": "",
      "reasonCode": ""
    },
    "importServicesSeller": {
      "importBusinessName": "",
      "importEmailAddress": "",
      "importContactNumber": "",
      "importAddress": "",
      "importInvoiceDate": "2023-05-21",
      "importAttachmentName": "",
      "importAttachmentContent": ""
    },
    "airlineGoodsDetails": [
      {
         "item": "pencils-10",
         "itemCode": "0008396770",
         "qty": "20",
         "unitOfMeasure": "101",
         "unitPrice": "12000.00",
         "total": "240000.00",
         "taxRate": "0.18",
         "tax": "36610.17",
         "discountTotal": "",
         "discountTaxRate": "0.00",
         "orderNumber": "1",
         "discountFlag": "2",
         "deemedFlag": "1",
         "exciseFlag": "2",
         "categoryId": "",
         "categoryName": "",
         "goodsCategoryId": "50151513",
         "goodsCategoryName": "Edible vegetable or plant oils",
         "exciseRate": "",
         "exciseRule": "",
         "exciseTax": "",
         "pack": "",
         "stick": "",
         "exciseUnit": "101",
         "exciseCurrency": "UGX",
         "exciseRateName": ""
         
      }
    ],
    "edcDetails": {
      "tankNo": "1111",
      "pumpNo": "2222",
      "nozzleNo": "3333",
      "controllerNo": "",
      "acquisitionEquipmentNo": "",
      "levelGaugeNo": "",
      "mvrn": "",
      "updateTimes": ""
    },
    "agentEntity": {
      "tin": "",
      "legalName": "",
      "businessName": "",
      "address": ""
    }
}
    return invoiceUpload_Goods_NonExcise