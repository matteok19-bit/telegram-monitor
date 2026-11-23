"""Monitora canali Telegram pubblici e ti avvisa (via bot) quando compare "SSD 1TB"."""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CHANNELS = ["prodigeekOfferte", "offertepuntotech"]

# ============================================================
# PAROLE DA CERCARE: aggiungi qui le tue, tra virgolette, separate da virgola.
# Un post viene segnalato se contiene TUTTE le parole di almeno una voce
# (in qualsiasi ordine, maiuscole/minuscole e "1 TB"/"1TB" non contano).
# Esempio: "SSD 1TB" trova "Crucial SSD 1TB" e anche "1TB SSD NVMe".
# ============================================================
KEYWORDS = [
    "SSD 1TB",
    "prezzo",  # parola di prova: toglila quando le notifiche funzionano
    # "RTX 4070",
    # "monitor 27",
]


def normalize(text):
    # "1 TB" -> "1TB", "512 GB" -> "512GB"
    return re.sub(r"(\d)\s+(tb|gb|mb)\b", r"\1\2", text, flags=re.IGNORECASE)


def find_keyword(text):
    """Restituisce la prima voce di KEYWORDS trovata nel testo, altrimenti None."""
    text = normalize(text)
    for keyword in KEYWORDS:
        words = normalize(keyword).split()
        if all(re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE) for w in words):
            return keyword
    return None

STATE_FILE = Path("state.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; channel-monitor/1.0)"}

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]


def fetch_posts(channel):
    """Restituisce [(id, testo), ...] degli ultimi post visibili sul web."""
    r = requests.get(f"https://t.me/s/{channel}", headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        post_id = int(msg["data-post"].split("/")[-1])
        text_div = msg.select_one(".tgme_widget_message_text")
        text = text_div.get_text("\n", strip=True) if text_div else ""
        posts.append((post_id, text))
    return sorted(posts)


def notify(channel, keyword, post_id, text):
    link = f"https://t.me/{channel}/{post_id}"
    preview = text if len(text) <= 600 else text[:600] + "…"
    message = f"🔔 {keyword} su @{channel}\n\n{preview}\n\n{link}"
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message},
        timeout=20,
    )
    r.raise_for_status()


def main():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    errors = 0

    for channel in CHANNELS:
        try:
            posts = fetch_posts(channel)
        except Exception as e:
            print(f"[{channel}] errore: {e}", file=sys.stderr)
            errors += 1
            continue
        if not posts:
            print(f"[{channel}] nessun post trovato")
            continue

        last_seen = state.get(channel)
        newest = posts[-1][0]
        new_posts = [p for p in posts if last_seen is not None and p[0] > last_seen]

        print(
            f"[{channel}] letti {len(posts)} post, ultimo id {newest}, "
            f"ultimo visto {last_seen}, nuovi {len(new_posts)}"
        )
        print(f"[{channel}] ultimo post: {posts[-1][1][:80]!r}")
        print(f"[{channel}] parole cercate: {KEYWORDS}")

        if last_seen is None:
            # Prima esecuzione: memorizzo il punto di partenza senza notificare
            print(f"[{channel}] prima esecuzione, parto dal post {newest}")
        else:
            for post_id, text in new_posts:
                keyword = find_keyword(text)
                print(f"[{channel}] nuovo post {post_id}: parola trovata = {keyword}")
                if keyword:
                    notify(channel, keyword, post_id, text)

        state[channel] = max(newest, last_seen or 0)

    STATE_FILE.write_text(json.dumps(state, indent=2))
    sys.exit(1 if errors == len(CHANNELS) else 0)


if __name__ == "__main__":
    main()
