
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
import threading

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BOT_USERNAME = os.getenv("BOT_USERNAME")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# In-memory database
users = {}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = {
            "balance": 0.0,
            "referrals": [],
            "referred_by": None
        }
    return users[user_id]

def get_ref_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start={user_id}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_member = await context.bot.get_chat_member(CHANNEL_ID, user.id)
    if chat_member.status in ['left', 'kicked']:
        join_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔐 Join Channel", url=f"https://t.me/{CHANNEL_ID[1:]}")],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]
        ])
        await update.message.reply_text("🔒 Please join our official channel to use the bot:", reply_markup=join_button)
        return

    if context.args:
        ref_by = context.args[0]
        if ref_by != str(user.id):
            u = get_user(user.id)
            if not u["referred_by"]:
                u["referred_by"] = int(ref_by)
                ref_user = get_user(int(ref_by))
                ref_user["referrals"].append(user.id)
                ref_user["balance"] += 0.05

    await send_home(update, context)

async def send_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    text = (
        f"👋 Welcome, {user.first_name}!

"
        f"👤 Username: @{user.username or 'N/A'}
"
        f"🆔 ID: {user.id}
"
        f"💰 Balance: ${u['balance']:.2f}
"
        f"👥 Total Referrals: {len(u['referrals'])}
"
        f"🔗 Referral Link:
{get_ref_link(user.id)}"
    )
    buttons = [[InlineKeyboardButton("💵 Withdraw", callback_data="withdraw")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    chat_member = await context.bot.get_chat_member(CHANNEL_ID, user.id)
    if chat_member.status in ['left', 'kicked']:
        await query.edit_message_text("❌ You haven't joined the channel yet.")
    else:
        await query.delete_message()
        await send_home(update, context)

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    u = get_user(user.id)
    if u["balance"] < 1:
        await query.edit_message_text("⚠️ You need at least $1 to withdraw.")
        return

    active_refs = [r for r in u["referrals"] if await context.bot.get_chat_member(CHANNEL_ID, r)]
    if len(active_refs) < len(u["referrals"]):
        await query.edit_message_text("❌ Some of your referred users are not active in the channel.")
        return

    buttons = [
        [InlineKeyboardButton("📲 bKash", callback_data="bkash")],
        [InlineKeyboardButton("💳 Nagad", callback_data="nagad")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ]
    await query.edit_message_text("🔔 Choose a withdrawal method:", reply_markup=InlineKeyboardMarkup(buttons))

async def method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data
    context.user_data['method'] = method
    await query.edit_message_text("💸 Enter the amount to withdraw:")
    context.user_data['next_step'] = 'ask_amount'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    user_id = update.effective_user.id
    u = get_user(user_id)
    if user_data.get("next_step") == "ask_amount":
        try:
            amount = float(update.message.text)
        except:
            await update.message.reply_text("❌ Invalid amount. Enter a number.")
            return
        if amount > u["balance"]:
            await update.message.reply_text("❌ You don't have enough balance.")
            return
        user_data['amount'] = amount
        user_data['next_step'] = 'ask_number'
        await update.message.reply_text("📱 Enter your number:")
        return

    if user_data.get("next_step") == "ask_number":
        number = update.message.text
        method = user_data['method']
        amount = user_data['amount']
        u["balance"] -= amount
        user_data.clear()
        await update.message.reply_text(
            f"✅ Withdrawal request received.

Method: {method.upper()}
Amount: ${amount}
Number: {number}

💠 It will be processed soon."
        )

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_home(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ You are not authorized.")
        return
    text = "📊 All User Stats:

"
    for uid, data in users.items():
        text += (
            f"🆔 ID: {uid}
"
            f"💰 Balance: ${data['balance']:.2f}
"
            f"👥 Referrals: {len(data['referrals'])}
"
            f"Referred By: {data['referred_by']}

"
        )
    if not users:
        text = "❗ No users found yet."
    await update.message.reply_text(text)

# Flask admin API server
app = Flask(__name__)
CORS(app)

@app.route("/admin/users")
def get_users():
    return jsonify(users)

def run_admin_server():
    app.run(port=8000)

def main():
    threading.Thread(target=run_admin_server).start()
    app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))
    app_telegram.add_handler(CallbackQueryHandler(withdraw, pattern="withdraw"))
    app_telegram.add_handler(CallbackQueryHandler(method_selected, pattern="bkash|nagad"))
    app_telegram.add_handler(CallbackQueryHandler(go_back, pattern="back_home"))
    app_telegram.add_handler(CommandHandler("admin", admin_panel))
    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot is running...")
    app_telegram.run_polling()

if __name__ == "__main__":
    main()
