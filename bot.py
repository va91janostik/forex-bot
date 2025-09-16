import os
import asyncio
from datetime import datetime, date, time, timedelta

import pytz
import requests
from bs4 import BeautifulSoup
import discord

# ==== Nastavení ====
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # nastav v Render env
TZ = pytz.timezone("Europe/Prague")

# kdy posílat (hodiny:minuty v Europe/Prague)
SEND_TIMES = [(7, 30), (19, 0)]  # ráno 07:30, večer 19:00

# filtry
ONLY_HIGH_IMPACT = True     # posílej jen High
INCLUDE_MEDIUM = True      # pokud chceš i Medium, dej True

intents = discord.Intents.default()
client = discord.Client(intents=intents)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0; +https://discord.com)"
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
    if "High" in text:
        return "High"
    if "Medium" in text:
        return "Medium"
    if "Low" in text:
        return "Low"
    bulls = cell.select('[class*="bull"]')
    if bulls:
        n = len(bulls)
        return {3: "High", 2: "Medium", 1: "Low"}.get(n, f"{n} bulls")
    return text

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

            event_cell = row.find("td", class_="calendar__event") or row.find("td", class_="event")
            event_name = event_cell.get_text(" ", strip=True) if event_cell else ""

            actual_cell = row.find("td", class_="calendar__actual") or row.find("td", class_="actual")
            forecast_cell = row.find("td", class_="calendar__forecast") or row.find("td", class_="forecast")
            previous_cell = row.find("td", class_="calendar__previous") or row.find("td", class_="previous")

            actual = actual_cell.get_text(" ", strip=True) if actual_cell else ""
            forecast = forecast_cell.get_text(" ", strip=True) if forecast_cell else ""
            previous = previous_cell.get_text(" ", strip=True) if previous_cell else ""

            if not event_name:
                continue

            imp_norm = impact.lower()
            if ONLY_HIGH_IMPACT and "high" not in imp_norm:
                continue
            if (not ONLY_HIGH_IMPACT) and (not INCLUDE_MEDIUM) and ("low" in imp_norm or "medium" in imp_norm):
                if "high" not in imp_norm:
                    continue

            events.append({
                "time": time_txt or "—",
                "currency": currency or "—",
                "impact": (impact or "—").replace("Impact", "").strip(),
                "event": event_name,
                "actual": actual,
                "forecast": forecast,
                "previous": previous
            })
        except Exception:
            continue
    return events

def format_events_discord(events):
    if not events:
        return ["📅 Dnes na ForexFactory (High impact): nic k zobrazení."]

    header = "📅 **Dnes – ForexFactory Economic Calendar (High impact)**"
    lines = ["```", f"{'Time':<6} | {'Cur':<3} | {'Imp':<5} | Event", "-" * 70]
    for e in events:
        t = (e["time"] or "—")[:6]
        c = (e["currency"] or "—")[:3]
        i = (e["impact"] or "—")[:5]
        evt = e["event"][:60]
        lines.append(f"{t:<6} | {c:<3} | {i:<5} | {evt}")
    lines.append("```")
    text = header + "\n" + "\n".join(lines)
    return [text]

async def send_calendar(channel: discord.TextChannel):
    try:
        events = fetch_today_events()
    except Exception as e:
        await channel.send(f"❗ Nepodařilo se stáhnout kalendář: `{e}`")
        return
    for msg in format_events_discord(events):
        await channel.send(msg)

async def scheduler_loop():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("‼️ CHANNEL_ID je špatně nebo bot nemá přístup.")
        return

    await channel.send("✅ Bot běží. Upozornění přijde 2× denně (07:30 a 19:00, Europe/Prague).")

    while not client.is_closed():
        delay = next_fire_delay()
        await asyncio.sleep(delay)
        await send_calendar(channel)

@client.event
async def on_ready():
    print(f"✅ Přihlášen jako {client.user}")

client.loop.create_task(scheduler_loop())
client.run(DISCORD_TOKEN)
