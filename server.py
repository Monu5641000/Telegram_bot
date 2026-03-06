from flask import Flask, render_template, jsonify, request
import database as db
import os
import threading
import logging
from flask_cors import CORS
import requests
import json
import config
import time

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
            elif data:
                 # Standard form-data/x-www-form-urlencoded
                 response = session.post(url, data=data, timeout=10)
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
    analytics = db.get_daily_user_analytics()
    main_menu_text = db.get_main_menu_text() or ""
    pricing_plans = db.get_pricing_plans()
    
    # Financials (40% Yash, 60% Abhishek)
    total_earnings = stats['total']
    yash_share = total_earnings * 0.40
    abhishek_share = total_earnings * 0.60
    
    total_paid_yash = db.get_total_paid()
    pending_yash = yash_share - total_paid_yash
    
    payouts = db.get_payouts()
    # Sort payouts new to old
    payouts.sort(key=lambda x: x['date'], reverse=True)

    financials = {
        "yash_share": yash_share,
        "abhishek_share": abhishek_share,
        "total_paid": total_paid_yash,
        "pending": pending_yash,
        "payouts": payouts
    }

    return render_template('index.html', users=users, orders=orders, stats=stats, financials=financials, analytics=analytics, main_menu_text=main_menu_text, pricing_plans=pricing_plans)

@app.route('/api/update_main_menu', methods=['POST'])
def update_main_menu():
    text = request.json.get("text")
    if text is not None:
        db.update_main_menu_text(text)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

@app.route('/api/update_pricing', methods=['POST'])
def update_pricing():
    plans = request.json.get("plans")
    if plans:
        db.update_pricing_plans(plans)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

@app.route('/api/mark_paid', methods=['POST'])
def mark_paid():
    data = request.json
    amount = data.get("amount")
    note = data.get("note", "")
    
    if not amount:
        return jsonify({"status": "error", "message": "Amount is required"}), 400
        
    try:
        db.add_payout(amount, note)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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

    return jsonify({"status": "error", "message": "User not found"}), 404

@app.route('/api/upload_image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    
    if file:
        photos_dir = "photos"
        try:
            if not os.path.exists(photos_dir):
                os.makedirs(photos_dir)
            for filename in os.listdir(photos_dir):
                file_path = os.path.join(photos_dir, filename)
                try:
                    if os.path.isfile(file_path): os.unlink(file_path)
                except: pass
            
            file.save(os.path.join(photos_dir, file.filename))
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/upload_qr', methods=['POST'])
def upload_qr():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    
    if file:
        try:
            file.save(config.QR_CODE_PATH)
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/broadcast', methods=['POST'])
def broadcast():
    # Handle Multipart Form Data
    message = request.form.get("message")
    target = request.form.get("target", "all")
    btn_text = request.form.get("btn_text")
    btn_url = request.form.get("btn_url")
    
    file = request.files.get("file")
    
    if not message and not file:
        return jsonify({"status": "error", "message": "Message or File is required"}), 400
        
    users = db.get_all_users()
    
    reply_markup = None
    if btn_text and btn_url:
        reply_markup = {"inline_keyboard": [[{"text": btn_text, "url": btn_url}]]}
    
    # Save file temporarily if exists
    temp_file_path = None
    media_type = None
    if file:
        filename = file.filename.lower()
        if filename.endswith(('.jpg', '.jpeg', '.png', '.webp')):
            media_type = "photo"
        elif filename.endswith(('.mp4', '.mov', '.avi')):
            media_type = "video"
        
        if not os.path.exists("static/temp"):
            os.makedirs("static/temp")
        temp_file_path = os.path.join("static/temp", file.filename)
        file.save(temp_file_path)

    def send_broadcast_thread(temp_path, m_type):
        sent_count = 0
        file_id = None # Store file_id after first upload to reuse
        
        for user in users:
            try:
                # Filter Logic
                if target == "active" and not user.get("is_subscribed"): continue
                if target == "expired" and user.get("is_subscribed"): continue
                
                chat_id = user['user_id']
                payload = {
                    "chat_id": chat_id,
                    "parse_mode": "Markdown",
                    "reply_markup": json.dumps(reply_markup) if reply_markup else None
                }
                if message: payload["caption" if m_type else "text"] = message

                # CASE 1: Text Only
                if not m_type:
                    safe_send_telegram("sendMessage", data=payload)
                
                # CASE 2: Media (First Time Upload)
                elif file_id is None:
                    with open(temp_path, 'rb') as f:
                        method = "sendPhoto" if m_type == "photo" else "sendVideo"
                        files = {m_type: f}
                        resp = safe_send_telegram(method, data=payload, files=files)
                        
                        # Try to extract file_id for optimization
                        if resp and resp.status_code == 200:
                            res_json = resp.json()
                            if m_type == "photo":
                                file_id = res_json['result']['photo'][-1]['file_id']
                            elif m_type == "video":
                                file_id = res_json['result']['video']['file_id']
                                
                # CASE 3: Media (Reuse File ID)
                else:
                    method = "sendPhoto" if m_type == "photo" else "sendVideo"
                    payload[m_type] = file_id
                    safe_send_telegram(method, data=payload)

                sent_count += 1
                time.sleep(0.05)
            except Exception as e:
                print(f"Broadcast error for {user.get('user_id')}: {e}")
        
        print(f"Broadcast completed. Sent to {sent_count} users.")
        
        # Cleanup
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    threading.Thread(target=send_broadcast_thread, args=(temp_file_path, media_type)).start()
    
    return jsonify({"status": "success", "message": "Broadcast started"})

def run_server():
    app.run(host='0.0.0.0', port=5050)

if __name__ == '__main__':
    run_server()
