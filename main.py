import os
import time
import random
import logging
import uuid
import config
import database as db
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaVideo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Silence httpx logger
logging.getLogger("httpx").setLevel(logging.WARNING)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    print(f"⚠️ Error handled: {context.error}")


# State for manual payments: {user_id: {"plan_name": str, "price": int}}
PENDING_PAYMENTS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Received /start from {update.effective_user.id}") # DEBUG
    user_id = update.effective_user.id
    
    # Ensure user exists in DB
    try:
        user = db.get_user(user_id)
        print(f"User fetched: {user}") # DEBUG
    except Exception as e:
        print(f"DB Error: {e}")
        await update.message.reply_text("Database error. Is MongoDB running?")
        return
    
    if user.get("is_subscribed"):
        await show_video_interface(update, context)
    else:
        await show_subscription_plans(update, context)

async def show_subscription_plans(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text=None):
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    
    keyboard = []
    for plan_name, details in config.PLANS.items():
        # Hide Demo if already used
        if details['price'] == 0 and user.get("demo_used"):
            continue
            
        keyboard.append([InlineKeyboardButton(f"{plan_name} - ₹{details['price']}", callback_data=f"plan_{plan_name}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if message_text:
        text = message_text
    else:
        text = (
            "18+ ONLY. VIP ACCESS.\n\n"
            "I deliver raw, explicit premium adult videos.\n"
            "This space is private, uncensored.\n\n"
            "What you get 🔥\n"
            "• Nude & lingerie content\n"
            "• Explicit solo sessions\n"
            "• POV fantasies\n"
            "• Desi / Indian vibes\n"
            "• Young-adult energy (18+)\n"
            "• Amateur & home-style clips\n"
            "• Roleplay scenarios (18+)\n"
            "• Tease → full reveal drops\n\n"
            "Unlock exclusive content by subscribing to one of our plans per below.\n\n"
            "👇 Choose a plan to continue:"
        )
    
    # Image Logic
    photos_dir = "photos"
    photo_path = None
    if os.path.exists(photos_dir):
        files = [f for f in os.listdir(photos_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if files:
            photo_path = os.path.join(photos_dir, random.choice(files))

    if update.callback_query:
        # User Interaction: Delete the previous message (Video or Text) to ensure "Vanish" effect
        try:
             await update.callback_query.message.delete()
        except Exception:
             pass # Message might already be deleted or too old

        if photo_path:
            try:
                with open(photo_path, 'rb') as photo:
                    await context.bot.send_photo(chat_id=update.effective_user.id, photo=photo, caption=text, reply_markup=reply_markup)
            except Exception as e:
                print(f"Error sending photo: {e}")
                await context.bot.send_message(chat_id=update.effective_user.id, text=text, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=update.effective_user.id, text=text, reply_markup=reply_markup)
    else:
        if photo_path:
            try:
                with open(photo_path, 'rb') as photo:
                    await update.message.reply_photo(photo=photo, caption=text, reply_markup=reply_markup)
            except Exception as e:
                print(f"Error sending photo: {e}")
                await update.message.reply_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)

async def show_video_interface(update: Update, context: ContextTypes.DEFAULT_TYPE, retry_count=0, is_looping=False):
    user_id = update.effective_user.id
    
    # Check validity
    user = db.get_user(user_id)
    if not user.get("is_subscribed"):
        # User is not subscribed (or expired just now)
        msg = "⚠️ **Your plan has EXPIRED!** ⚠️\n\nPlease renew your subscription to continue watching."
        await show_subscription_plans(update, context, message_text=msg)
        return

    # Loading Feedback (only on first try)
    if update.callback_query and retry_count == 0 and not is_looping:
        try:
            await update.callback_query.answer("⏳ Fetching next video...")
        except:
             pass

    # --- DIRECT CHANNEL MODE (ALWAYS ACTIVE) ---
    # Treat 'current_video_index' as the actual Message ID in the channel
    # Default to config.CHANNEL_START_ID
    current_msg_id = user.get("current_video_index", config.CHANNEL_START_ID)
    
    # Validation: Ensure we don't go below start ID
    if current_msg_id < config.CHANNEL_START_ID:
        current_msg_id = config.CHANNEL_START_ID
        db.update_video_index(user_id, current_msg_id)

    # 2. FETCH & SEND (New Strategy: Copy New -> Delete Old)
    # This avoids "Temp Copy" weirdness and ensures robust handling of all media types.
    
    # Define Buttons
    reply_markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Prev", callback_data="vid_prev_direct"),
            InlineKeyboardButton("Next ➡️", callback_data="vid_next_direct")
        ]
    ])

    try:
        # A. Copy the new message to the user
        # This handles Video, Document, Photo, Text automatically.
        new_msg = await context.bot.copy_message(
            chat_id=user_id,
            from_chat_id=config.PRIVATE_CHANNEL_ID,
            message_id=current_msg_id,
            protect_content=True,
            reply_markup=reply_markup
        )
        
        # B. If successful, Delete the Old Message
        # We try to delete the message that triggered this (from callback) OR the stored last_message_id
        if update.callback_query:
            try:
                await update.callback_query.message.delete()
            except:
                pass
        elif user.get("last_message_id"):
             # For /start or other entries, try cleanup if possible
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=user["last_message_id"])
            except:
                pass
        
        # C. Update State
        db.update_last_message_id(user_id, new_msg.message_id)

    except Exception as e:
        print(f"Fetch Error (ID {current_msg_id}): {e}")
        
        # AUTO-SKIP LOGIC / RECURSION
        if retry_count < 10: # Limit retries
            next_id = current_msg_id + 1
            print(f"⚠️ Skipping ID {current_msg_id} -> Trying {next_id} (Retry {retry_count+1}/10)")
            db.update_video_index(user_id, next_id)
            await show_video_interface(update, context, retry_count=retry_count+1, is_looping=is_looping)
            return

        # If we ran out of retries, maybe we reached the END of the channel?
        # Try LOOPING back to start?
        if not is_looping:
            print(f"⚠️ End of channel reached (or large gap). Looping to start.")
            db.update_video_index(user_id, config.CHANNEL_START_ID)
            if update.callback_query:
                try: await update.callback_query.answer("↺ Playlist ended. Restarting...")
                except: pass
            await show_video_interface(update, context, retry_count=0, is_looping=True)
            return

        # Fallback if too many retries AND we already looped (Infinite loop prevention)
        if update.callback_query:
            try: 
                 await context.bot.send_message(
                    chat_id=user_id, 
                    text=f"⚠️ No playable videos found after {current_msg_id}. Please try again later.",
                 )
            except: pass
        return

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        print(f"⚠️ Network warning (query.answer): {e}")

    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("plan_"):
        plan_name = data.split("_")[1]
        plan = config.PLANS.get(plan_name)
        if not plan:
            return
            
        # Helper: Bypass for Demo
        if plan["price"] == 0:
            # Check if already used
            user = db.get_user(user_id)
            if user.get("demo_used"):
                await query.answer("⚠️ You have already used the Free Demo!", show_alert=True)
                return

            db.update_user_subscription(user_id, days=plan.get("days", 0), minutes=plan.get("minutes", 0))
            db.mark_demo_used(user_id) # Mark as used
            
            await query.message.delete()
            await context.bot.send_message(chat_id=user_id, text="✅ Demo Activated! You have access for 1 minute.")
            await show_video_interface(update, context)
            return

        # MANUAL PAYMENT FLOW
        # 1. Send QR Code
        try:
            with open(config.QR_CODE_PATH, 'rb') as photo:
                caption = (
                    f"📦 **Plan:** {plan_name}\n"
                    f"💰 **Amount:** ₹{plan['price']}\n\n"
                    "📷 **Scan the QR Code to Pay.**\n"
                    "📤 **After paying, send the successful payment SCREENSHOT here.**"
                )
                await query.message.delete()
                await context.bot.send_photo(chat_id=user_id, photo=photo, caption=caption, parse_mode="Markdown")
                
                # Set State
                PENDING_PAYMENTS[user_id] = plan
                
        except FileNotFoundError:
             await context.bot.send_message(chat_id=user_id, text="❌ Error: QR Code not found. Contact Admin.")

    elif data.startswith("check_"):
        # Deprecated logic, but keeping handler to avoid crashes if old buttons exist
        await query.answer("Please send screenshot instead.")
             
    # --- Direct Mode Handlers (ONLY) ---
    elif data == "vid_next_direct":
        user = db.get_user(user_id)
        # Increment Message ID
        current = user.get("current_video_index", config.CHANNEL_START_ID)
        db.update_video_index(user_id, current + 1)
        await show_video_interface(update, context)
        
    elif data == "vid_prev_direct":
        user = db.get_user(user_id)
        current = user.get("current_video_index", config.CHANNEL_START_ID)
        if current > config.CHANNEL_START_ID:
            db.update_video_index(user_id, current - 1)
        await show_video_interface(update, context)

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if user has a pending payment
    plan = PENDING_PAYMENTS.get(user_id)
    if not plan:
        await update.message.reply_text("❓ You haven't selected a plan. Please use /start to select a plan first.")
        return

    # Process Screenshot
    photo = update.message.photo[-1] # Largest size
    file = await context.bot.get_file(photo.file_id)
    
    # Create Order ID
    order_id = str(uuid.uuid4()).replace("-", "")[:10]
    
    # Save Path
    filename = f"{order_id}.jpg"
    file_path = os.path.join(config.UPLOAD_FOLDER, filename)
    await file.download_to_drive(file_path)
    
    # Create Database Entry
    db.create_order(order_id, user_id, plan["price"], screenshot_path=f"screenshots/{filename}", days=plan["days"])
    
    # Clear State
    del PENDING_PAYMENTS[user_id]
    
    await update.message.reply_text("✅ **Screenshot Received!**\n\nWaiting for admin approval, just 2min wait...", parse_mode="Markdown")

async def check_expiry_job(context: ContextTypes.DEFAULT_TYPE):
    """Background job to check for expired users and vanish their content."""
    users = db.get_all_users()
    for user in users:
        user_id = user['user_id']
        
        # Check if expired
        is_expired = False
        if not user.get("is_subscribed"):
            is_expired = True
            
        # Check date (double check, as db.get_all_users doesn't auto-expire without get_user call)
        # We should probably run db.get_user(user_id) to trigger the expiry logic inside it,
        # OR just duplicate the logic here for efficiency.
        # Let's rely on db.get_user to update state if needed.
        user = db.get_user(user_id) # This updates 'is_subscribed' if time passed
        
        if not user.get("is_subscribed") and user.get("last_message_id"):
            # Vanish!
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=user["last_message_id"])
            except Exception as e:
                print(f"Failed to vanish message for {user_id}: {e}")
            
            # Send Expired Message
            try:
                msg = "⚠️ **Your plan has EXPIRED!** ⚠️\n\nThe video has been removed. Please renew to continue."
                
                # We need to send plans. We can't reuse show_subscription_plans easily without 'update' object.
                # So we reproduce a simple version or refactor.
                # Refactoring 'show_subscription_plans' to check for update is best.
                # For now, let's just send text + inline keyboard manually.
                
                keyboard = []
                for plan_name, details in config.PLANS.items():
                    keyboard.append([InlineKeyboardButton(f"{plan_name} - ₹{details['price']}", callback_data=f"plan_{plan_name}")])
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.send_message(chat_id=user_id, text=msg, reply_markup=reply_markup, parse_mode="Markdown")
                
            except Exception as e:
                print(f"Failed to send expiry msg to {user_id}: {e}")
                
            # Clear last_message_id so we don't loop
            db.update_last_message_id(user_id, None)

if __name__ == '__main__':
    # usage of custom request to handle network flakiness
    request = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=60.0,
        pool_timeout=60.0
    )
    application = ApplicationBuilder().token(config.BOT_TOKEN).request(request).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_error_handler(error_handler)
    
    # JOB QUEUE
    job_queue = application.job_queue
    job_queue.run_repeating(check_expiry_job, interval=60, first=10) # Check every 60s
    
    print("Bot is running... Go to Telegram and send /start")
    print(f"ℹ️ DIRECT MODE ACTIVE: Videos fetched from {config.PRIVATE_CHANNEL_ID} starting at msg {config.CHANNEL_START_ID}")

    # Robust Polling Loop
    while True:
        try:
            print("🔄 connection started...")
            # Reduced timeout to 30 for shorter, more reliable cycles
            application.run_polling(timeout=30, bootstrap_retries=-1)
        except Exception as e:
            print(f"⚠️ Connection Lost: {e}")
            print("Restarting in 5 seconds...")
            time.sleep(5)
