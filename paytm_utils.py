from paytmchecksum import PaytmChecksum
import config
import requests
import json

def generate_checksum(order_id, txn_amount, customer_id):
    """
    Generates Paytm Checksum for transaction.
    """
    paytmParams = dict()

    paytmParams["body"] = {
        "requestType": "Payment",
        "mid": config.PAYTM_MID,
        "websiteName": config.PAYTM_WEBSITE,
        "orderId": order_id,
        "callbackUrl": config.PAYTM_CALLBACK_URL,
        "txnAmount": {
            "value": str(txn_amount),
            "currency": "INR",
        },
        "userInfo": {
            "custId": customer_id,
        },
    }

    # Generate checksum by parameters we have in body
    # Find your Merchant Key in your Paytm Dashboard at https://dashboard.paytm.com/next/apikeys
    checksum = PaytmChecksum.generateSignature(json.dumps(paytmParams["body"]), config.PAYTM_MERCHANT_KEY)

    paytmParams["head"] = {
        "signature": checksum
    }

    return paytmParams

def verify_transaction_status(order_id):
    """
    Checks the status of the transaction via Paytm API.
    """
    paytmParams = dict()

    paytmParams["body"] = {
        "mid": config.PAYTM_MID,
        "orderId": order_id,
    }

    # Generate checksum for status check
    checksum = PaytmChecksum.generateSignature(json.dumps(paytmParams["body"]), config.PAYTM_MERCHANT_KEY)

    paytmParams["head"] = {
        "signature": checksum
    }

    url = config.PAYTM_STATUS_URL

    post_data = json.dumps(paytmParams)
    response = requests.post(url, data=post_data, headers={"Content-type": "application/json"}).json()
    
    return response

def create_payment_link(order_id, txn_amount, customer_id, customer_mobile=None, description="Subscription"):
    """
    Creates a Payment Link via Paytm API.
    """
    paytmParams = dict()
    paytmParams["body"] = {
        "mid": config.PAYTM_MID,
        "linkType": "GENERIC",
        "linkDescription": description,
        "linkName": f"SUB-{order_id}", 
        "orderId": order_id, # Link API often autogenerates if not passed, but for tracking we might need it. Actually Link API uses "linkId" as handle, but let's try standard Create Link parameters.
        # Checking Paytm Link API docs: https://developer.paytm.com/docs/api/create-link/
        # required: mid, linkType, linkName, linkDescription.
        # But we want a Fixed Amount link? Or Generic? 
        # Actually, "Initiate Transaction" is better for one-time orders because Link API creates a re-usable link usually. 
        # But "Invoice Link" is one-time.
        # User said "payment will genrate".
        # Let's stick to Initiate Transaction (Standard) and return the deepLink if available, or just the browser URL.
        # The verify_transaction_status matches Initiate Transaction flow.
        # If we use Initiate Transaction, we need a frontend to handle the JS checkout OR use the native flow.
        # Native flow for "UPI Intent" requires collecting VPA or generating a QR string.
        # Simplest for Bot: Create a Link (Invoice) that holds the specific amount.
    }
    # Wait, Paytm "Create Link" API is distinct.
    # Let's try the logic for "Initiate Transaction" and construct the web url manually for the user to open in browser?
    # URL: https://securegw.paytm.in/theia/api/v1/showPaymentPage?mid=...&orderId=...&txnToken=...
    # Yes, this is the standard "WAP" flow.
    
    # So we keep generate_checksum (which effectively prepares initiate_transaction params if we call the API).
    # We need a function to CALL separate 'initiateTransaction' API to get txnToken.
    pass

def initiate_transaction(order_id, txn_amount, customer_id):
    paytmParams = dict()
    paytmParams["body"] = {
        "requestType": "Payment",
        "mid": config.PAYTM_MID,
        "websiteName": config.PAYTM_WEBSITE,
        "orderId": order_id,
        "callbackUrl": config.PAYTM_CALLBACK_URL,
        "txnAmount": {
            "value": str(txn_amount),
            "currency": "INR",
        },
        "userInfo": {
            "custId": customer_id,
        },
    }
    
    checksum = PaytmChecksum.generateSignature(json.dumps(paytmParams["body"]), config.PAYTM_MERCHANT_KEY)
    paytmParams["head"] = {
        "signature": checksum
    }

    url = f"{config.PAYTM_TRANSACTION_URL}?mid={config.PAYTM_MID}&orderId={order_id}"
    
    response = requests.post(url, data=json.dumps(paytmParams), headers={"Content-type": "application/json"}).json()
    
    if "body" in response and "txnToken" in response["body"]:
        return response["body"]["txnToken"]
    return None

