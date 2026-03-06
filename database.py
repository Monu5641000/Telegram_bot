import json
import os
from datetime import datetime, timedelta
import pymongo
import config

client = pymongo.MongoClient(config.MONGO_URI)
db = client[config.DB_NAME]

users_col = db["users"]
videos_col = db["videos"]
orders_col = db["orders"]
payouts_col = db["payouts"]
settings_col = db["settings"]

def migrate_from_json():
    db_file = "db.json"
    if not os.path.exists(db_file): return
    try:
        with open(db_file, "r") as f:
            data = json.load(f)
            
        if "users" in data and users_col.count_documents({}) == 0:
            users_list = list(data["users"].values())
            if users_list: users_col.insert_many(users_list)
            
        if "videos" in data and videos_col.count_documents({}) == 0:
            if data["videos"]: videos_col.insert_many(data["videos"])
            
        if "orders" in data and orders_col.count_documents({}) == 0:
            orders_list = list(data["orders"].values())
            if orders_list: orders_col.insert_many(orders_list)
            
        if "payouts" in data and payouts_col.count_documents({}) == 0:
            if data["payouts"]: payouts_col.insert_many(data["payouts"])
            
        os.rename(db_file, "db_migrated.json")
    except Exception as e:
        print(f"Migration error: {e}")

migrate_from_json()

# --- Settings Operations ---
def get_main_menu_text():
    setting = settings_col.find_one({"_id": "main_menu"})
    if setting and "text" in setting:
        return setting["text"]
    return None

def update_main_menu_text(text):
    settings_col.update_one({"_id": "main_menu"}, {"$set": {"text": text}}, upsert=True)

def get_pricing_plans():
    setting = settings_col.find_one({"_id": "pricing_plans"})
    if setting and "plans" in setting:
        return setting["plans"]
    
    # Default config plans if not set in DB
    default_plans = {
        "1-Day": {"price": 49, "days": 1, "minutes": 0, "description": "Access for 1 Day"},
        "1-Week": {"price": 99, "days": 7, "minutes": 0, "description": "Access for 7 Days"},
        "1-Month": {"price": 199, "days": 30, "minutes": 0, "description": "Access for 30 Days"},
        "3-Months": {"price": 299, "days": 90, "minutes": 0, "description": "Access for 90 Days"},
        "6-Months": {"price": 399, "days": 180, "minutes": 0, "description": "Access for 180 Days"},
        "Lifetime": {"price": 699, "days": 36500, "minutes": 0, "description": "Lifetime Access"},
        "Demo": {"price": 0, "url": "https://t.me/+r5WU9e69M8xjY2Zl", "description": "Join Free Channel"}
    }
    update_pricing_plans(default_plans)
    return default_plans

def update_pricing_plans(plans_dict):
    settings_col.update_one({"_id": "pricing_plans"}, {"$set": {"plans": plans_dict}}, upsert=True)

# --- User Operations ---
def get_user(user_id):
    user_id_str = str(user_id)
    user = users_col.find_one({"user_id": int(user_id_str)}) or users_col.find_one({"user_id": user_id_str})
    
    if not user:
        user = {
            "user_id": int(user_id_str),
            "is_subscribed": False,
            "subscription_expiry": None,
            "current_video_index": 0,
            "last_message_id": None,
            "demo_used": False,
            "joined_at": datetime.now().isoformat()
        }
        users_col.insert_one(user)
    else:
        # Check expiry
        if user.get("is_subscribed") and user.get("subscription_expiry"):
            expiry = datetime.fromisoformat(user["subscription_expiry"]) if isinstance(user["subscription_expiry"], str) else user["subscription_expiry"]
            if expiry < datetime.now():
                users_col.update_one({"_id": user["_id"]}, {"$set": {"is_subscribed": False}})
                user["is_subscribed"] = False
    return user

def mark_demo_used(user_id):
    users_col.update_one({"user_id": int(user_id)}, {"$set": {"demo_used": True}})

def update_last_message_id(user_id, message_id):
    users_col.update_one({"user_id": int(user_id)}, {"$set": {"last_message_id": message_id}})

def update_user_subscription(user_id, days=0, minutes=0):
    expiry = datetime.now() + timedelta(days=days, minutes=minutes)
    users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {
            "is_subscribed": True,
            "subscription_expiry": expiry.isoformat()
        }}
    )

def update_video_index(user_id, index):
    users_col.update_one({"user_id": int(user_id)}, {"$set": {"current_video_index": index}})

# --- Video Operations ---
def add_video(file_id, description, message_id=None):
    seq_id = videos_col.count_documents({})
    video = {
        "file_id": file_id,
        "description": description,
        "message_id": message_id,
        "sequence_id": seq_id
    }
    videos_col.insert_one(video)
    return video

def get_video_by_index(index):
    return videos_col.find_one({"sequence_id": index})

def get_total_videos():
    return videos_col.count_documents({})

# --- Order Operations ---
def create_order(order_id, user_id, amount, screenshot_path=None, days=30):
    order = {
        "order_id": order_id,
        "user_id": user_id,
        "amount": amount,
        "days": days,
        "screenshot_path": screenshot_path,
        "status": "PENDING_APPROVAL",
        "created_at": datetime.now().isoformat()
    }
    orders_col.insert_one(order)
    return order

def update_order_status(order_id, status):
    orders_col.update_one({"order_id": order_id}, {"$set": {"status": status}})

def get_order(order_id):
    return orders_col.find_one({"order_id": order_id})

# --- Admin Operations ---
def get_all_users():
    return list(users_col.find())

def get_pending_orders():
    return list(orders_col.find({"status": "PENDING_APPROVAL"}))

def approve_order(order_id):
    order = orders_col.find_one({"order_id": order_id})
    if order:
        if order.get("status") == "SUCCESS":
            return False # Already approved
            
        orders_col.update_one({"_id": order["_id"]}, {"$set": {"status": "SUCCESS"}})
        
        user_id = int(order["user_id"])
        days = order.get("days", 30) 
        
        user = users_col.find_one({"user_id": user_id})
        expiry = datetime.now() + timedelta(days=days)
        
        if not user:
             users_col.insert_one({
                "user_id": user_id,
                "is_subscribed": True,
                "subscription_expiry": expiry.isoformat(),
                "current_video_index": 0,
                "joined_at": datetime.now().isoformat()
            })
        else:
            users_col.update_one(
                {"_id": user["_id"]},
                {"$set": {
                    "is_subscribed": True,
                    "subscription_expiry": expiry.isoformat()
                }}
            )
        return True
    return False

def reject_order(order_id):
    result = orders_col.update_one({"order_id": order_id}, {"$set": {"status": "REJECTED"}})
    return result.modified_count > 0

def expire_user(user_id):
    result = users_col.update_one(
        {"user_id": int(user_id)},
        {"$set": {
            "is_subscribed": False,
            "subscription_expiry": None
        }}
    )
    return result.modified_count > 0

def get_earnings_stats():
    orders = list(orders_col.find({"status": "SUCCESS"}))
    
    total_earnings = 0
    daily_earnings = 0
    today_str = datetime.now().date().isoformat()
    
    for order in orders:
        try:
            amount = float(order["amount"])
            total_earnings += amount
            
            created_at = order.get("created_at", "")
            if created_at.startswith(today_str):
                daily_earnings += amount
        except (ValueError, TypeError):
            pass
            
    return {
        "total": total_earnings,
        "daily": daily_earnings
    }

def get_daily_user_analytics():
    # Group users by joined_at date snippet (YYYY-MM-DD)
    users = list(users_col.find({}, {"joined_at": 1}))
    analytics = {}
    
    for u in users:
        # Default to old users if they don't have joined_at (from migration)
        joined_date = u.get("joined_at", "2024-01-01T")[:10]
        if joined_date not in analytics:
            analytics[joined_date] = 0
        analytics[joined_date] += 1
        
    # Sort by date
    sorted_analytics = dict(sorted(analytics.items(), key=lambda x: x[0], reverse=True))
    return sorted_analytics

# --- Payout Operations ---
def add_payout(amount, note=""):
    payout = {
        "id": str(payouts_col.count_documents({}) + 1),
        "amount": float(amount),
        "date": datetime.now().isoformat(),
        "note": note
    }
    payouts_col.insert_one(payout)
    return payout

def get_payouts():
    return list(payouts_col.find())

def get_total_paid():
    total = 0
    for p in payouts_col.find():
        try:
            total += float(p["amount"])
        except:
            pass
    return total
