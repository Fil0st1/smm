import discord
from discord.ext import commands
import requests
import sqlite3
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import aiohttp

# === CONFIG ===
load_dotenv() 
TOKEN = os.getenv("TOKEN")

API_KEY = os.getenv("API_KEY")
API_URL = "https://justanotherpanel.com/api/v2"
PREFIX = "!"
DB_NAME = "wallet.db"

# === BOT SETUP ===
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# === DATABASE SETUP ===
conn = sqlite3.connect(DB_NAME)
c = conn.cursor()
c.execute("CREATE TABLE IF NOT EXISTS wallet (user_id INTEGER PRIMARY KEY, balance REAL)")
conn.commit()

def get_balance(user_id):
    c.execute("SELECT balance FROM wallet WHERE user_id=?", (user_id,))
    result = c.fetchone()
    return result[0] if result else 0.0

def add_balance(user_id, amount):
    balance = get_balance(user_id)
    new_balance = balance + amount
    c.execute("INSERT OR REPLACE INTO wallet (user_id, balance) VALUES (?, ?)", (user_id, new_balance))
    conn.commit()
    return new_balance

def deduct_balance(user_id, amount):
    balance = get_balance(user_id)
    if balance >= amount:
        new_balance = balance - amount
        c.execute("UPDATE wallet SET balance=? WHERE user_id=?", (new_balance, user_id))
        conn.commit()
        return True
    return False

# === BOT EVENTS ===
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# === COMMAND: Check Balance ===
@bot.command()
async def balance(ctx):
    bal = get_balance(ctx.author.id)
    await ctx.send(f"💳 {ctx.author.mention}, your wallet balance is €{bal:.2f}")

# === COMMAND: Add Funds (manual approval) ===
@bot.command()
async def addfunds(ctx, amount: float):
    embed = discord.Embed(
        title="💸 Add Funds Request",
        description="Follow the instructions below to add balance:",
        color=discord.Color.green()
    )
    embed.add_field(name="PayPal", value="`whymebtw123@hotmail.com`", inline=False)
    embed.add_field(name="Amount", value=f"**{amount:.2f} EUR**", inline=False)
    embed.add_field(
        name="Instructions",
        value="✅ Send as **Friends & Family**\n✨Send screenshot of sending\n⏳ Wait for an admin to confirm your payment.",
        inline=False
    )
    embed.set_footer(text=f"Requested by {ctx.author}", 
                     icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

    await ctx.send(embed=embed)


# === COMMAND: Admin Approve Funds ===
@bot.command()
@commands.has_permissions(administrator=True)
async def approve(ctx, member: discord.Member, amount: float):
    new_balance = add_balance(member.id, amount)
    await ctx.send(f"✅ Approved €{amount} for {member.mention}. New balance: €{new_balance:.2f}")

# === COMMAND: Admin Deduct Funds ===
@bot.command()
@commands.has_permissions(administrator=True)
async def deduct(ctx, member: discord.Member, amount: float):
    balance = get_balance(member.id)
    if balance >= amount:
        success = deduct_balance(member.id, amount)
        if success:
            new_balance = get_balance(member.id)
            await ctx.send(f"✅ Deducted {amount:.2f} from {member.mention}. New balance: {new_balance:.2f}")
        else:
            await ctx.send("⚠️ Deduction failed (DB error).")
    else:
        await ctx.send(f"❌ {member.mention} doesn’t have enough balance. Current: {balance:.2f}")


# === COMMAND: List Services ===
# MARKUP_PERCENT = 30  # increase panel rate by 30%

# @bot.command()
# async def services(ctx, *, query: str = None):
#     payload = {"key": API_KEY, "action": "services"}
#     try:
#         r = requests.post(API_URL, data=payload)
#         result = r.json()

#         if query:
#             query = query.lower()
#             filtered = [s for s in result if query in s["name"].lower()]
#         else:
#             filtered = result[:10]

#         if not filtered:
#             await ctx.send(f"❌ No services found for: `{query}`")
#             return

#         msg = f"📋 Services matching **{query if query else 'All'}**:\n"
#         for s in filtered[:10]:
#             base_rate = float(s["rate"])  # panel rate per 1000
#             sell_rate = base_rate * (1 + MARKUP_PERCENT/100)  # add profit
#             msg += f"ID: {s['service']} | {s['name']} | Rate: {sell_rate:.2f}/1000\n"

#         await ctx.send(msg)

#     except Exception as e:
#         await ctx.send(f"❌ Error fetching services: {str(e)}")

#==== Command: list services =====
import os

@bot.command()
async def services(ctx, category: str = None):
    if not category:
        await ctx.send("⚠️ Please specify a category. Example: `!services IG_followers`")
        return

    filename = f"{category}.txt"

    if not os.path.exists(filename):
        await ctx.send(f"❌ No services found for `{category}` (file `{filename}` missing).")
        return

    try:
        with open(filename, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            await ctx.send(f"⚠️ The file `{filename}` is empty.")
            return

        msg = f"📋 Services for **{category}**:\n\n"
        for line in lines:
            msg += line.strip() + "\n"

        await ctx.send(msg)

    except Exception as e:
        await ctx.send(f"❌ Error reading services: {str(e)}")




# === COMMAND: Place Order ===
@bot.command()
async def order(ctx, service_id: str, link: str, qty: int):
    async with aiohttp.ClientSession() as session:
        # get services
        payload = {"key": API_KEY, "action": "services"}
        async with session.post(API_URL, data=payload) as resp:
            services = await resp.json()

        cost = None
        for s in services:
            if str(s["service"]) == service_id:
                rate = float(s["rate"])
                base_cost = (rate / 1000) * qty
                cost = base_cost * 1.3
                break

        if cost is None:
            return await ctx.send("⚠️ Invalid service ID.")

        if not deduct_balance(ctx.author.id, cost):
            return await ctx.send("❌ Insufficient balance.")

        # place order
        payload = {
            "key": API_KEY,
            "action": "add",
            "service": service_id,
            "link": link,
            "quantity": qty
        }
        async with session.post(API_URL, data=payload) as resp:
            result = await resp.json()

        if "order" in result:
            await ctx.send(f"✅ Order placed! ID: {result['order']}")
        else:
            await ctx.send(f"⚠️ Failed to place order: {result}")




USD_TO_EUR = 0.92  # fixed conversion rate

@bot.command()
async def status(ctx, order_id: str):
    payload = {"key": API_KEY, "action": "status", "order": order_id}
    try:
        result = requests.post(API_URL, data=payload).json()

        if "error" in result:
            await ctx.send(f"❌ Error: {result['error']}")
            return

        # Extract values safely
        # charge_usd = float(result.get("charge", 0))
        # charge_eur = charge_usd * USD_TO_EUR
        start_count = result.get("start_count", "N/A")
        remains = result.get("remains", "N/A")
        status_val = result.get("status", "N/A")

        now = datetime.now(timezone.utc)

        embed = discord.Embed(
            title="📊 Order Status",
            color=discord.Color.blue(),
            timestamp=now
        )

        embed.add_field(name="🆔 ID", value=order_id, inline=True)
        # embed.add_field(name="💰 Charge", value=f"{charge_usd:.5f} USD ≈ {charge_eur:.5f} EUR", inline=False)
        embed.add_field(name="📈 Start Count", value=start_count, inline=True)
        embed.add_field(name="⏳ Remains", value=remains, inline=True)
        embed.add_field(name="📌 Status", value=status_val, inline=True)

        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error fetching status: {str(e)}")

# === COMMAND: Create Refill ===
@bot.command()
async def refill(ctx, order_id: str):
    payload = {"key": API_KEY, "action": "refill", "order": order_id}
    try:
        r = requests.post(API_URL, data=payload).json()
        refill_id = r.get("refill")

        if refill_id:
            embed = discord.Embed(
                title="♻️ Refill Created",
                description=f"✅ Refill request created successfully.",
                color=discord.Color.green()
            )
            embed.add_field(name="Order ID", value=order_id, inline=True)
            embed.add_field(name="Refill ID", value=refill_id, inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Failed to create refill: {r}")

    except Exception as e:
        await ctx.send(f"⚠️ Error: {str(e)}")


# === COMMAND: Refill Status ===
@bot.command()
async def refillstatus(ctx, refill_id: str):
    payload = {"key": API_KEY, "action": "refill_status", "refill": refill_id}
    try:
        r = requests.post(API_URL, data=payload).json()
        status = r.get("status", "Unknown")

        embed = discord.Embed(
            title="📊 Refill Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="Refill ID", value=refill_id, inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"⚠️ Error: {str(e)}")

ADMIN_IDS = [962895767486464131, 576830885664522281]  # replace with real Discord IDs

@bot.command()
async def breal(ctx):
    if ctx.author.id not in ADMIN_IDS:
        return await ctx.send("⛔ You are not authorized to use this command.")

    payload = {"key": API_KEY, "action": "balance"}
    r = requests.post(API_URL, data=payload).json()
    bal = r.get("balance", "0")
    currency = r.get("currency", "USD")

    embed = discord.Embed(
        title="💰 Account Balance",
        color=discord.Color.gold()
    )
    embed.add_field(name="Balance", value=f"{bal} {currency}", inline=True)
    await ctx.send(embed=embed)

# === COMMAND: Show All Commands ===
@bot.command(name="helpme")
async def helpme(ctx):
    embed = discord.Embed(
        title="📖 Available Commands",
        description="Here are all the commands you can use:",
        color=discord.Color.purple()
    )

    # User Commands
    embed.add_field(
        name="👤 User Commands",
        value=(
            "`!balance` → Check your wallet balance\n"
            "`!addfunds <amount>` → Request to add funds\n"
            "`!services <category>` → Show available services (ex: IG_followers)\n"
            "`!order <service_id> <link> <qty>` → Place an order\n"
            "`!status <order_id>` → Check status of your order\n"
            "`!refill <order_id>` → Create a refill request\n"
            "`!refillstatus <refill_id>` → Check status of a refill\n"
        ),
        inline=False
    )

    # Admin Commands
    embed.add_field(
        name="🛠️ Admin Commands",
        value=(
            "`!approve <@user> <amount>` → Approve funds for a user\n"
            "`!deduct <@user> <amount>` → Deduct funds from a user\n"
            "`!breal` → Check API account balance\n"
        ),
        inline=False
    )

    embed.set_footer(
        text=f"Requested by {ctx.author}", 
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
    )

    await ctx.send(embed=embed)

from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run).start()


bot.run(TOKEN)
