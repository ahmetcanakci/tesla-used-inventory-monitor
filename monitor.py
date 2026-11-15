import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import requests

INVENTORY_URL = "https://www.tesla.com/coinorder/api/v4/inventory-results"
STATE_FILE = Path("data/seen_vins.json")
ZIP_CODE = os.getenv("TESLA_ZIP", "34080")

def fetch_inventory():
    payload = {
        "query": {
            "model": "my",
            "condition": "used",
            "options": {},
            " arrangeby": "plh",
            "market": "TR",
            "language": "tr",
            "super_region": "europe",
            "zip": ZIP_CODE,
            "range": 0
        },
        "queryでは": None
    }
    # Tesla's inventory endpoint is undocumented and may change.
    # Keep request headers browser-like; inspect Actions logs if Tesla changes it.
    response = requests.post(
        INVENTORY_URL,
        params={"query": json.dumps(payload["query"], separators=(",", ":"))},
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.tesla.com",
            "Referer": "https://www.tesla.com/tr_TR/inventory/used/my"
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return extract_vehicles(data)

def extract_vehicles(data):
    vehicles = []
    def walk(obj):
        if isinstance(obj, dict):
            if obj.get("VIN") or obj.get("vin"):
                vin = obj.get("VIN") or obj.get("vin")
                vehicles.append({
                    "vin": vin,
                    "model": obj.get("TrimName") or obj.get("Model") or "Model Y",
                    "price": obj.get("Price") or obj.get("TotalPrice"),
                    "year": obj.get("Year"),
                    "url": obj.get("ModelCode") or ""
                })
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)
    walk(data)
    unique = {v["vin"]: v for v in vehicles}
    return list(unique.values())

def send_email(new_vehicles):
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.getenv("MAIL_TO", sender)

    lines = ["Tesla Türkiye ikinci el Model Y envanterinde yeni araç bulundu:", ""]
    for vehicle in new_vehicles:
        lines.append(
            f"VIN: {vehicle['vin']} | Model: {vehicle['model']} | "
            f"Yıl: {vehicle['year'] or '-'} | Fiyat: {vehicle['price'] or '-'}"
        )
    lines += ["", "Envanter sayfası:", "https://www.tesla.com/tr_TR/inventory/used/my?arrangeby=plh&zip=34080&HasVehiclePhotos=true"]

    message = EmailMessage()
    message["Subject"] = f"Tesla ikinci el Model Y: {len(new_vehicles)} yeni ilan"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("\n".join(lines))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)

def main():
    vehicles = fetch_inventory()
    print(f"API'den bulunan VIN sayısı: {len(vehicles)}")

    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        seen = set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    else:
        seen = set()

    current = {v["vin"] for v in vehicles}
    new_vins = current - seen

    # First run establishes a baseline; it does not email all existing listings.
    if not STATE_FILE.exists():
        print("İlk çalışma: mevcut ilanlar başlangıç listesi olarak kaydedildi; e-posta gönderilmedi.")
    elif new_vins:
        new_vehicles = [v for v in vehicles if v["vin"] in new_vins]
        send_email(new_vehicles)
        print(f"{len(new_vehicles)} yeni ilan için e-posta gönderildi.")
    else:
        print("Yeni ilan yok.")

    STATE_FILE.write_text(json.dumps(sorted(seen | current), ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"HATA: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
