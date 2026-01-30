import os
from dotenv import load_dotenv

load_dotenv()

# Bot Credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
# Channel Configuration
PRIVATE_CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID")
CHANNEL_START_ID = int(os.getenv("CHANNEL_START_ID", 1)) # Message ID of the first video

# Config
QR_CODE_PATH = "qr.jpeg" # Place a file named qr.jpeg in the bot folder
UPLOAD_FOLDER = "static/screenshots"

# MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "tele_corn_bot"

# Paytm Credentials
PAYTM_MID = os.getenv("PAYTM_MID")
PAYTM_MERCHANT_KEY = os.getenv("PAYTM_MERCHANT_KEY")
PAYTM_WEBSITE = os.getenv("PAYTM_WEBSITE", "DEFAULT")
PAYTM_CALLBACK_URL = os.getenv("PAYTM_CALLBACK_URL", "https://securegw.paytm.in/theia/paytmCallback") # Not used for bot usually, but required params
PAYTM_INDUSTRY_TYPE_ID = os.getenv("PAYTM_INDUSTRY_TYPE_ID", "Retail")
PAYTM_CHANNEL_ID = os.getenv("PAYTM_CHANNEL_ID", "WAP")
PAYTM_TRANSACTION_URL = "https://securegw.paytm.in/theia/processTransaction"
PAYTM_STATUS_URL = "https://securegw.paytm.in/merchant-status/getTxnStatus"


# Subscription Plans
PLANS = {
    "1-Day": {"price": 49, "days": 1, "minutes": 0, "description": "Access for 1 Day"},
    "1-Month": {"price": 100, "days": 30, "minutes": 0, "description": "Access for 30 Days"},
    "3-Months": {"price": 150, "days": 90, "minutes": 0, "description": "Access for 90 Days"},
    "Demo": {"price": 0, "days": 0, "minutes": 1, "description": "Free Testing Access (1 Minute)"}
}
