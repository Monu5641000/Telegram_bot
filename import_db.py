import json
import pymongo
import config
import os

print("Connecting to MongoDB...")
client = pymongo.MongoClient(config.MONGO_URI)
db = client[config.DB_NAME]

print("Loading data from db_migrated.json...")
with open('db_migrated.json', 'r') as f:
    data = json.load(f)

print("Dropping existing collections...")
db.users.drop()
db.videos.drop()
db.orders.drop()
db.payouts.drop()

print("Inserting data...")
if "users" in data:
    users_list = list(data["users"].values())
    if users_list: 
        db.users.insert_many(users_list)
        print(f"Inserted {len(users_list)} users.")
        
if "videos" in data:
    if data["videos"]: 
        db.videos.insert_many(data["videos"])
        print(f"Inserted {len(data['videos'])} videos.")
        
if "orders" in data:
    orders_list = list(data["orders"].values())
    if orders_list: 
        db.orders.insert_many(orders_list)
        print(f"Inserted {len(orders_list)} orders.")
        
if "payouts" in data:
    if data["payouts"]: 
        db.payouts.insert_many(data["payouts"])
        print(f"Inserted {len(data['payouts'])} payouts.")

print("Successfully imported db_migrated.json to MongoDB!")
