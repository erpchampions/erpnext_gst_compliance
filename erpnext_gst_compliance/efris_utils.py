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
from Crypto.Util.Padding import pad, unpad
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives import hashes
from Crypto.Hash import SHA1

import os
#from frappe.utils import get_site_path
import logging

from datetime import datetime
import pytz
from collections import defaultdict

#logging.info("This is an info message")
#logging.warning("This is a warning message")
#logging.error("This is an error message")

# Determine the base directory of frappe-bench
base_dir = os.path.dirname(os.path.abspath(__file__))

# Traverse up to the frappe-bench directory
frappe_bench_dir = os.path.abspath(os.path.join(base_dir, '..', '..'))

# Define the logs directory relative to frappe-bench
log_dir = os.path.join(frappe_bench_dir, 'logs')

# Ensure the logs directory exists
os.makedirs(log_dir, exist_ok=True)

# Define the log file path
log_file_path = os.path.join(log_dir, 'efris_logfile.log')
#logging.basicConfig(filename='/workspace/development/frappe-bench/logs/efris_logfile.log', level=logging.DEBUG)
logging.basicConfig(filename=log_file_path, level=logging.DEBUG)

def efris_log_info(message):
    logging.info(message)


def make_post(interfaceCode, content):
    try:
        data = fetch_data()
        efris_log_info("Data fetched successfully")

        aes_key = get_AES_key()
        efris_log_info("AES key fetched successfully")

        deviceNo = "1017460267_01"
        tin = "1017460267"
        brn = ""

        json_content = json.dumps(content)
        efris_log_info("Content converted to JSON successfully: " + json_content)

        isAESEncrypted = encrypt_aes_ecb(json_content, aes_key)
        efris_log_info("Content encrypted with AES successfully")

        isAESEncrypted = base64.b64decode(isAESEncrypted)
        newEncrypteddata = base64.b64encode(isAESEncrypted).decode("utf-8")

        if isAESEncrypted:
            efris_log_info("AES encryption successful")
            data["globalInfo"]["deviceNo"] = deviceNo
            data["globalInfo"]["tin"] = tin
            data["globalInfo"]["brn"] = brn
            data["globalInfo"]["interfaceCode"] = interfaceCode
            data["data"]["content"] = base64.b64encode(isAESEncrypted).decode("utf-8")
            data["data"]["dataDescription"] = {"codeType": "1", "encryptCode": "2"}

            private_key = get_private_key()
            efris_log_info("Private key fetched successfully in make_post()")

            signature = sign_data(private_key, newEncrypteddata.encode())
            efris_log_info("signature done...")

            if signature:
                b4signature = base64.b64encode(signature).decode()
                data["data"]["signature"] = b4signature

        data_json = json.dumps(data).replace("'", '"').replace("\n", "").replace("\r", "")
        efris_log_info("Request data converted to JSON successfully")
        efris_log_info("Request data:\n")
        efris_log_info(data_json)

        json_resp = post_req(data_json)

        resp = json.loads(json_resp)
        efris_log_info("Server response successfully parsed")

        errorMsg = resp["returnStateInfo"]["returnMessage"]
        efris_log_info("returnStateInfoMsg: " + errorMsg)
        if errorMsg != "SUCCESS":
            return False, errorMsg

        respcontent = resp["data"]["content"]
        efris_response = decrypt_aes_ecb(aes_key, respcontent)
        efris_log_info("Response content decrypted successfully")
        resp_json = json.loads(efris_response)
        efris_log_info("Decrypted JSON Data:")
        efris_log_info(resp_json)
        return True, resp_json

    except Exception as e:
        efris_log_info("An error occurred: " + str(e))
        return False, str(e)

def encrypt_aes_ecb(data, key):
    padding_length = 16 - (len(data) % 16)
    padding = bytes([padding_length] * padding_length)
    padded_data = data + padding.decode()

    cipher = AES.new(key, AES.MODE_ECB)
    ct_bytes = cipher.encrypt(padded_data.encode("utf-8"))
    ct = base64.b64encode(ct_bytes).decode("utf-8")
    return ct

def decrypt_aes_ecb(aeskey, ciphertext):
    ciphertext = base64.b64decode(ciphertext)
    cipher = AES.new(aeskey, AES.MODE_ECB)
    plaintext_with_padding = cipher.decrypt(ciphertext).decode()
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

def fetch_data():
    now = get_ug_time_str()
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
            "deviceNo": "1017460267_01",
            "tin": "1017460267",
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
        data = fetch_data()
        efris_log_info("Data fetched successfully - inside get_AES_key")

        deviceNo = "1017460267_01"
        tin = "1017460267"
        brn = ""
        dataExchangeId = guidv4()

        data["globalInfo"]["interfaceCode"] = "T104"
        data["globalInfo"]["dataExchangeId"] = dataExchangeId
        data["globalInfo"]["deviceNo"] = deviceNo
        data["globalInfo"]["tin"] = tin
        data["globalInfo"]["brn"] = brn

        data_json = json.dumps(data).replace("'", '"').replace("\n", "").replace("\r", "")
        efris_log_info("Request data converted to JSON successfully")

        resp = post_req(data_json)
        efris_log_info("POST request to fetch AES key successful")

        jsonresp = json.loads(resp)
        efris_log_info("Response JSON parsed successfully")

        b64content = jsonresp["data"]["content"]
        content = json.loads(base64.b64decode(b64content).decode("utf-8"))
        efris_log_info("Content extracted from response")

        b64passwordDes = content["passowrdDes"]
        passwordDes = base64.b64decode(b64passwordDes)
        efris_log_info("PasswordDes decoded successfully")

        privKey = get_private_key()
        efris_log_info("Private key fetched successfully")

        # Convert the private key to a PEM format byte string for RSA import
        pkey_str = privKey.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        efris_log_info("pkey_str converted...")

        # Decrypt AES key using the private key
        cipher = PKCS1_v1_5.new(RSA.import_key(pkey_str))
        aesKey = cipher.decrypt(passwordDes, None)

        efris_log_info("AES key decrypted successfully")
        return base64.b64decode(aesKey)

    except Exception as e:
        efris_log_info("An error occurred in get_AES_key(): " + str(e))
        return None


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
        key_file_path = os.path.join(private_files_path, 'online_mode_pk.p12')

        efris_log_info("key_file_path:" + str(key_file_path))

        with open(key_file_path, "rb") as f:
            pfx_data = f.read()
            efris_log_info("read the key...")

        pfx = pkcs12.load_key_and_certificates(pfx_data, b"efris", default_backend())
        efris_log_info("pfx done...")

        private_key = pfx[0]  # The private key is the first element

        if private_key is None:
            efris_log_info('Private key extraction failed: private_key is None')
            return None
        
        efris_log_info("get_private_key()...done")
        return private_key
    except Exception as e:
        efris_log_info(f'Error extracting private key: {e}')
        return None

def sign_data(private_key, data):
    try:
        # Use the private key to sign the data
        signature = private_key.sign(
            data,
            asym_padding.PKCS1v15(),
            hashes.SHA1()
        )

        efris_log_info("Data signed successfully")
        return signature
    except Exception as e:
        efris_log_info(f'Error signing data: {e}')
        return None


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

