import discord
from discord.ext import commands, tasks
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import os

# 💡 Získej token z prostředí nebo vlož ručně (NEUKAZUJ VEŘEJNĚ!)
TOKEN = os.getenv("DISCORD_TOKEN") or "TVŮJ_DISCORD_BOT_TOKEN"

# Prefix příkazů, např. !zpravy
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

# 🌍 Časová zóna pro filtrování dnešních událostí
timezone = pytz.timezone("Europe/Prague")


def ziskej_ekonomicke_udalosti():
    url = "https://www.forexfactory.com/calendar"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    udalosti = []

    dnes = datetime.now(timezone).strftime("%b %d")  # např. "Sep 17"

    for row in soup.select("tr.calendar__row"):
        datum = row.select_one(".calendar__cell.date")
        cas = row.select_one(".calendar__cell.time")
        mena = row.select_one(".calendar__cell.currency")
        dopad = row.select_one(".calendar__cell.impact span")
        popis = row.select_one(".calendar__cell.event")

        if not all([datum, cas, mena, dopad, popis]):
            continue

        # Filtruj jen dnešní události
        if dnes.lower() not in datum.text.strip().lower():
            continue

        udalosti.append(
            f"🕒 {cas.text.strip()} | {mena.text.strip()} | {dopad['title']} | {popis.text.strip()}"
        )

    if not udalosti:
        return "🟢 Dnes nejsou žádné plánované události z Forex Factory."
    return "\n".join(udalosti)


@bot.event
async def on_ready():
    print(f"✅ Bot je přihlášen jako {bot.user}")


@bot.command(name="zpravy")
async def posli_zpravy(ctx):
    await ctx.send("📡 Načítám dnešní ekonomické události z ForexFactory...")
    try:
        zpravy = ziskej_ekonomicke_udalosti()
        await ctx.send(f"📰 **Ekonomické události dnes:**\n{zpravy}")
    except Exception as e:
        await ctx.send(f"❌ Chyba při načítání dat: {e}")


bot.run(TOKEN)
