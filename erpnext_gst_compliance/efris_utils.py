import frappe
from frappe import _
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


def make_post(interfaceCode, content):
    try:
        # Fetch data and log the result
        data = fetch_data()
        efris_log_info("Data fetched successfully")

        # Get AES key and log the result
        aes_key = get_AES_key()
        efris_log_info("AES key fetched successfully")

        deviceNo = "1002170340_01"
        tin = "1002170340"
        brn = ""

        # Convert content to JSON and log the result
        json_content = json.dumps(content)
        efris_log_info("Content converted to JSON successfully: "+ json_content)

        # Encrypt content with AES and log the result
        isAESEncrypted = encrypt_aes_ecb(json_content, aes_key)
        efris_log_info("Content encrypted with AES successfully")

        # Decode and encode the encrypted data
        isAESEncrypted = base64.b64decode(isAESEncrypted)
        newEncrypteddata = base64.b64encode(isAESEncrypted).decode("utf-8")

        if isAESEncrypted:
            efris_log_info("AES encryption successful")
            # Define data dictionary
            data["globalInfo"]["deviceNo"] = deviceNo
            data["globalInfo"]["tin"] = tin
            data["globalInfo"]["brn"] = brn
            data["globalInfo"]["interfaceCode"] = interfaceCode
            data["data"]["content"] = base64.b64encode(isAESEncrypted).decode("utf-8")
            data["data"]["dataDescription"] = {"codeType": "1", "encryptCode": "2"}

            # Get private key and log the result
            private_key = get_private_key()
            efris_log_info("Private key fetched successfully")

            # Sign the data and log the result
            signature = OpenSSL.crypto.sign(private_key, newEncrypteddata, "sha1")

            if signature:
                # Print the base64-encoded signature
                b4signature = base64.b64encode(signature).decode()

                # Add signature to data
                data["data"]["signature"] = b4signature

        # Convert data to JSON and log the result
        data_json = json.dumps(data).replace("'", '"').replace("\n", "").replace("\r", "")
        efris_log_info("Request data converted to JSON successfully")
        efris_log_info("Request data:\n")
        efris_log_info(data_json)

        # Make the POST request and log the result
        json_resp = post_req(data_json)

        # Parse the JSON response
        resp = json.loads(json_resp)
        efris_log_info("Server response successfully parsed")

        # Check for error message in the response
        errorMsg = resp["returnStateInfo"]["returnMessage"]
        efris_log_info("returnStateInfoMsg: " + errorMsg)
        if errorMsg != "SUCCESS":
            return False, errorMsg

        # Decrypt and parse the response content
        respcontent = resp["data"]["content"]
        efris_response = decrypt_aes_ecb(aes_key, respcontent)
        efris_log_info("Response content decrypted successfully")
        resp_json = json.loads(efris_response)
        efris_log_info("Decrypted JSON Data:")
        efris_log_info(resp_json)
        return True, resp_json

    except Exception as e:
        # Handle exceptions and log the error
        efris_log_error("An error occurred: " + str(e))
        return False, str(e)

def encrypt_aes_ecb(data, key):
    # Calculate the number of padding bytes required
    padding_length = 16 - (len(data) % 16)

    # Pad the data with the required number of bytes
    padding = bytes([padding_length] * padding_length)
    padded_data = data + padding.decode()

    cipher = AES.new(key, AES.MODE_ECB)
    ct_bytes = cipher.encrypt(padded_data.encode("utf-8"))
    ct = base64.b64encode(ct_bytes).decode("utf-8")
    return ct

def decrypt_aes_ecb(aeskey, ciphertext):

    # Decode the ciphertext from base64
    ciphertext = base64.b64decode(ciphertext)

    # Create an AES cipher object with the given key and mode
    cipher = AES.new(aeskey, AES.MODE_ECB)

    # Decrypt the ciphertext
    plaintext_with_padding = cipher.decrypt(ciphertext).decode()

    # Remove the padding
    padding_length = ord(plaintext_with_padding[-1])
    plaintext = plaintext_with_padding[:-padding_length]

    return plaintext

def to_ug_datetime(date_time):
    ug_time_zone = "Africa/Kampala"
    # Convert the current time to the Uganda time zone
    uganda_time = date_time.astimezone(pytz.timezone(ug_time_zone))
    uganda_time_str = uganda_time.strftime("%Y-%m-%d %H:%M:%S")   

    return  uganda_time_str
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

def get_AES_key():
    try:
        # Fetch data and log the result
        data = fetch_data()
        efris_log_info("Data fetched successfully")

        deviceNo = "1002170340_01"
        tin = "1002170340"
        brn = ""
        dataExchangeId = guidv4()

        # Update globalInfo dictionary
        data["globalInfo"]["interfaceCode"] = "T104"
        data["globalInfo"]["dataExchangeId"] = dataExchangeId
        data["globalInfo"]["deviceNo"] = deviceNo
        data["globalInfo"]["tin"] = tin
        data["globalInfo"]["brn"] = brn

        # Convert data to JSON and log the result
        data_json = json.dumps(data).replace("'", '"').replace("\n", "").replace("\r", "")
        efris_log_info("Request data converted to JSON successfully")

        # Make the POST request and log the result
        resp = post_req(data_json)
        efris_log_info("POST request to fetch AES key successful")

        # Parse the JSON response
        jsonresp = json.loads(resp)
        efris_log_info("Response JSON parsed successfully")

        # Extract content from the response
        b64content = jsonresp["data"]["content"]
        content = json.loads(base64.b64decode(b64content).decode("utf-8"))
        efris_log_info("Content extracted from response")

        # Decode passwordDes and decrypt AES key
        b64passwordDes = content["passowrdDes"]
        passwordDes = base64.b64decode(b64passwordDes)
        efris_log_info("PasswordDes decoded successfully")

        # Read private key and log the result
        privKey = get_private_key()
        efris_log_info("Private key fetched successfully")

        # Convert the private key object to a byte string
        pkey_str = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, privKey)

        # Decrypt AES key using RSA private key
        cipher = PKCS1_v1_5.new(RSA.import_key(pkey_str))
        aesKey = cipher.decrypt(passwordDes, None)
        
        efris_log_info("AES key decrypted successfully")
        return base64.b64decode(aesKey)

    except Exception as e:
        # Handle exceptions and log the error
        efris_log_error("An error occurred in get_AES_key(): " + str(e))
        return None  # You may want to return an appropriate value or raise an exception here

def guidv4():
    # generate a random UUID
    my_uuid = uuid.uuid4()

    # get the UUID as a string in standard format (32 hex characters separated by hyphens)
    my_uuid_str = str(my_uuid)

    # remove the hyphens to get a 32-character UUID string
    my_uuid_str_32 = my_uuid_str.replace("-", "")

    return my_uuid_str_32

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

def get_private_key():
    try:
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
    except:
        frappe.throw(_('Could not find private key inside Files. Please make sure it is uploaded.'))

def safe_load_json(message):
	try:
		json_message = json.loads(message)
	except Exception:
		json_message = message

	return json_message

def format_amount(amount):
    amt_float = float(amount)    
    amt_string = "{:.2f}"
    return amt_string.format(amt_float)

