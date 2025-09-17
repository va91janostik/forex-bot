import os
import asyncio
from datetime import datetime, date, time, timedelta

import pytz
import requests
from bs4 import BeautifulSoup

# === místo importu discord/py-cord hlasu ===
# import discord s deaktivací voice části
import py_cord as discord  # pokud jsi py-cord nainstaloval jako py-cord
# pokud by se jmenovalo jinak, může být: from discord import Client, Intents, etc. podle py-cord

# TRY disable parts, co by mohly importovat audioop
try:
    discord.opus = None
    discord.voice_client = None
    discord.player = None
    discord.sinks = None
except Exception:
    pass

# ==== Nastavení ====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TZ = pytz.timezone("Europe/Prague")

SEND_TIMES = [(7, 30), (19, 0)]
ONLY_HIGH_IMPACT = True
INCLUDE_MEDIUM = True

intents = discord.Intents.default()
# pokud chceš číst více, můžeš případně zapnout message_content, ale nepotřebujeme hlas:
# intents.message_content = True

client = discord.Client(intents=intents)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EconomicCalendarBot/1.0)"
}

def prague_now():
    return datetime.now(TZ)

def next_fire_delay():
    now = prague_now()
    today = now.date()
    candidates = []
    for h, m in SEND_TIMES:
        t = TZ.localize(datetime.combine(today, time(h, m)))
        if t > now:
            candidates.append(t)
    if not candidates:
        h, m = SEND_TIMES[0]
        t = TZ.localize(datetime.combine(today + timedelta(days=1), time(h, m)))
        candidates.append(t)
    target = min(candidates)
    return (target - now).total_seconds()

def parse_impact(cell):
    if cell is None:
        return ""
    for attr in ("title", "aria-label"):
        v = cell.get(attr)
        if v:
            return v.strip()
    img = cell.find("img")
    if img and img.get("alt"):
        return img["alt"].strip()
    text = cell.get_text(" ", strip=True)
    text_lower = text.lower()
    if "high" in text_lower:
        return "High"
    if "medium" in text_lower and INCLUDE_MEDIUM:
        return "Medium"
    return ""

def fetch_today_events():
    url = "https://www.forexfactory.com/calendar"
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.select("tr.calendar__row") or soup.select("tr:has(td.calendar__time), tr:has(td.time)")

    events = []
    for row in rows:
        try:
            time_cell = row.find("td", class_="calendar__time") or row.find("td", class_="time")
            time_txt = (time_cell.get_text(" ", strip=True) if time_cell else "").replace("\xa0", " ")

            curr_cell = row.find("td", class_="calendar__currency") or row.find("td", class_="currency")
            currency = curr_cell.get_text(" ", strip=True) if curr_cell else ""

            impact_cell = row.find("td", class_="calendar__impact") or row.find("td", class_="impact")
            impact = parse_impact(impact_cell)
            if not impact:
                continue

            event_cell = row.find("td", class_="calendar__event") or row.find("td", class_="event")
            event_name = event_cell.get_text(" ", strip=True) if event_cell else ""

            if not event_name:
                continue

            # už nepotřebujeme actual / forecast / previous, můžeme to vynechat

            events.append({
                "time": time_txt or "—",
                "currency": currency or "—",
                "impact": impact,
                "event": event_name
            })
        except Exception:
            continue
    return events

def format_events_discord(events):
    if not events:
        return ["📅 Dnes na ForexFactory (High/Medium impact): nic k zobrazení."]

    header = "📅 **Dnešní ekonomický kalendář – ForexFactory**"
    lines = ["```", f"{'Time':<6} | {'Cur':<5} | {'Imp':<6} | Event", "-" * 70]
    for e in events:
        t = (e["time"] or "—")[:6]
        c = (e["currency"] or "—")[:5]
        i = (e["impact"] or "—")[:6]
        evt = e["event"][:60]
        lines.append(f"{t:<6} | {c:<5} | {i:<6} | {evt}")
    lines.append("```")
    return [header] + lines

async def send_calendar(channel):
    try:
        evs = fetch_today_events()
    except Exception as e:
        await channel.send(f"❗ Chyba při získávání událostí: {e}")
        return
    formatted = format_events_discord(evs)
    # pokud je hodně událostí, můžeme rozdělit zprávy, ale tady stačí jedna
    await channel.send("\n".join(formatted))

async def scheduler_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("‼️ CHANNEL_ID špatně nebo bot nemá přístup.")
        return

    # oznam po startu
    await channel.send("✅ Bot je online. Pošlu ekonomický kalendář dvakrát denně.")

    while True:
        delay = next_fire_delay()
        await asyncio.sleep(delay)
        await send_calendar(channel)

@client.event
async def on_ready():
    print(f"✅ Přihlášen jako {client.user}")

client.loop.create_task(scheduler_loop())
client.run(DISCORD_TOKEN)
