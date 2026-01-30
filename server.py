from flask import Flask, render_template, jsonify, request
import database as db
import threading
import logging
from flask_cors import CORS
import requests
import json
import config

# Configure logging to be less verbose for Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Robust Session for Telegram API
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

def safe_send_telegram(endpoint, json_data=None, data=None, files=None):
    """Helper to send requests with explicit retry for RemoteDisconnected"""
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/{endpoint}"
    for i in range(3):
        try:
            if files:
                # requests/session with files usually requires data, not json
                response = session.post(url, data=data, files=files, timeout=10)
            else:
                response = session.post(url, json=json_data, timeout=10)
            return response
        except Exception as e:
            print(f"⚠️ Network error (attempt {i+1}/3): {e}")
            time.sleep(1)
    return None

app = Flask(__name__)
CORS(app)

# Helper to pass bot reference if needed (complex in threads, so we use DB only)
# Bot notifications on approval will be handled by Main Bot polling DB? 
# Or server updates DB, and Main Bot logic handles user entry?
# Actually, Main Bot doesn't need to do anything. User just gets access.
# If we want to NOTIFY user "You are approved", we need Bot Instance.
# We will solve "Notification" by updating DB and user checks status.
# Or, simpler: We won't notify instantly, user will just click "Check" or try again.
# BUT User asked: "after approve send message from bot approved"
# To do this cleanly: Server updates DB. We can add a "notifications" queue in DB?
# Or we can share the 'application.bot' object if we run in same process.
# We will stick to simple DB update first.

@app.route('/')
def index():
    users = db.get_all_users()
    orders = db.get_pending_orders()
    stats = db.get_earnings_stats()
    return render_template('index.html', users=users, orders=orders, stats=stats)

@app.route('/api/approve/<order_id>', methods=['POST'])
def approve(order_id):
    success = db.approve_order(order_id)
    if success:
        # Notify User
        order = db.get_order(order_id)
        if order:
            try:
                user_id = order['user_id']
                safe_send_telegram(
                    "sendMessage",
                    json_data={
                        "chat_id": user_id,
                        "text": "✅ **Your subscription has been APPROVED!**\n\nYou can now access the premium content. Use /start if needed.",
                        "parse_mode": "Markdown"
                    }
                )
                
                # Check if we should auto-trigger video interface? 
                # We can't easily trigger the python function from here, but the user is subscribed now.
                # A simple message is enough.
            except Exception as e:
                print(f"Failed to notify user: {e}")

        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Order not found or already processed"}), 400

@app.route('/api/reject/<order_id>', methods=['POST'])
def reject(order_id):
    success = db.reject_order(order_id)
    if success:
         # Notify User
        order = db.get_order(order_id)
        if order:
            try:
                user_id = order['user_id']
                # Send Rejection Text
                safe_send_telegram(
                    "sendMessage",
                    json_data={
                        "chat_id": user_id,
                        "text": "❌ **Your payment was REJECTED.**\n\nPlease ensure you pay the correct amount and upload a valid screenshot.\n\n👇 **Scan QR to Pay Again:**",
                        "parse_mode": "Markdown"
                    }
                )
                
                # Send QR Code again
                with open(config.QR_CODE_PATH, 'rb') as f:
                    safe_send_telegram(
                        "sendPhoto",
                        data={"chat_id": user_id},
                        files={"photo": f}
                    )
            except Exception as e:
                print(f"Failed to notify user: {e}")

        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

@app.route('/api/expire/<user_id>', methods=['POST'])
def expire(user_id):
    success = db.expire_user(user_id)
    if success:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "User not found"}), 404

def run_server():
    app.run(host='0.0.0.0', port=5000)

if __name__ == '__main__':
    run_server()
