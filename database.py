import json
import os
from datetime import datetime, timedelta

DB_FILE = "db.json"

def _load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "videos": [], "orders": {}}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading db.json: {e}")
        return {"users": {}, "videos": [], "orders": {}}

def _save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4, default=str)

# --- User Operations ---
def get_user(user_id):
    db = _load_db()
    user_id = str(user_id)
    user = db["users"].get(user_id)
    
    if not user:
        user = {
            "user_id": int(user_id),
            "is_subscribed": False,
            "subscription_expiry": None,
            "current_video_index": 0,
            "last_message_id": None,
            "demo_used": False
        }
        db["users"][user_id] = user
        _save_db(db)
    else:
        # Check expiry
        if user.get("is_subscribed") and user.get("subscription_expiry"):
            expiry = datetime.fromisoformat(user["subscription_expiry"]) if isinstance(user["subscription_expiry"], str) else user["subscription_expiry"]
            if expiry < datetime.now():
                user["is_subscribed"] = False
                db["users"][user_id] = user
                _save_db(db)
    return user

def mark_demo_used(user_id):
    db = _load_db()
    user_id = str(user_id)
    if user_id in db["users"]:
        db["users"][user_id]["demo_used"] = True
        _save_db(db)

def update_last_message_id(user_id, message_id):
    db = _load_db()
    user_id = str(user_id)
    if user_id in db["users"]:
        db["users"][user_id]["last_message_id"] = message_id
        _save_db(db)

def update_user_subscription(user_id, days=0, minutes=0):
    db = _load_db()
    user_id = str(user_id)
    if user_id in db["users"]:
        expiry = datetime.now() + timedelta(days=days, minutes=minutes)
        db["users"][user_id]["is_subscribed"] = True
        db["users"][user_id]["subscription_expiry"] = expiry.isoformat()
        _save_db(db)

def update_video_index(user_id, index):
    db = _load_db()
    user_id = str(user_id)
    if user_id in db["users"]:
        db["users"][user_id]["current_video_index"] = index
        _save_db(db)

# --- Video Operations ---
def add_video(file_id, description, message_id=None):
    db = _load_db()
    video = {
        "file_id": file_id,
        "description": description,
        "message_id": message_id,
        "sequence_id": len(db["videos"])
    }
    db["videos"].append(video)
    _save_db(db)
    return video

def get_video_by_index(index):
    db = _load_db()
    videos = db["videos"]
    for v in videos:
        if v["sequence_id"] == index:
            return v
    return None

def get_total_videos():
    db = _load_db()
    return len(db["videos"])

# --- Order Operations ---
def create_order(order_id, user_id, amount, screenshot_path=None, days=30):
    db = _load_db()
    order = {
        "order_id": order_id,
        "user_id": user_id,
        "amount": amount,
        "days": days,
        "screenshot_path": screenshot_path,
        "status": "PENDING_APPROVAL",
        "created_at": datetime.now().isoformat()
    }
    db["orders"][order_id] = order
    _save_db(db)
    return order

def update_order_status(order_id, status):
    db = _load_db()
    if order_id in db["orders"]:
        db["orders"][order_id]["status"] = status
        _save_db(db)

def get_order(order_id):
    db = _load_db()
    return db["orders"].get(order_id)

# --- Admin Operations ---
def get_all_users():
    db = _load_db()
    # Convert dict to list
    return list(db["users"].values())

def get_pending_orders():
    db = _load_db()
    pending = []
    for order in db["orders"].values():
        if order.get("status") == "PENDING_APPROVAL":
            pending.append(order)
    return pending

def approve_order(order_id):
    db = _load_db()
    if order_id in db["orders"]:
        order = db["orders"][order_id]
        if order["status"] == "SUCCESS":
            return False # Already approved
            
        # Update Order
        db["orders"][order_id]["status"] = "SUCCESS"
        
        # Update User Subscription
        user_id = str(order["user_id"])
        
        # Fallback: Default to 30 days if 'days' not in order
        days = order.get("days", 30) 
        
        # Create user if not exists (edge case)
        if user_id not in db["users"]:
             db["users"][user_id] = {
                "user_id": int(user_id),
                "is_subscribed": False,
                "subscription_expiry": None,
                "current_video_index": 0
            }
            
        expiry = datetime.now() + timedelta(days=days)
        db["users"][user_id]["is_subscribed"] = True
        db["users"][user_id]["subscription_expiry"] = expiry.isoformat()
        
        _save_db(db)
        return True
    return False

def reject_order(order_id):
    db = _load_db()
    if order_id in db["orders"]:
        db["orders"][order_id]["status"] = "REJECTED"
        _save_db(db)
        return True
    return False

def expire_user(user_id):
    db = _load_db()
    user_id = str(user_id)
    if user_id in db["users"]:
        db["users"][user_id]["is_subscribed"] = False
        db["users"][user_id]["subscription_expiry"] = None # Or keep date for record
        _save_db(db)
        return True
    return False

def get_earnings_stats():
    db = _load_db()
    orders = db["orders"].values()
    
    total_earnings = 0
    daily_earnings = 0
    today_str = datetime.now().date().isoformat()
    
    for order in orders:
        if order.get("status") == "SUCCESS":
            try:
                amount = float(order["amount"])
                total_earnings += amount
                
                # Check date
                created_at = order.get("created_at")
                if created_at and created_at.startswith(today_str):
                    daily_earnings += amount
            except (ValueError, TypeError):
                pass
                
    return {
        "total": total_earnings,
        "daily": daily_earnings
    }
