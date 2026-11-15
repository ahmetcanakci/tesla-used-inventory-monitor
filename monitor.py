import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

import requests

# Public Tesla inventory search endpoint used by several community clients.
INVENTORY_URL = "https://www.tesla.com/inventory/api/v4/inventory-results"
STATE_FILE = Path("data/seen_vins.json")
ZIP_CODE = os.getenv("TESLA_ZIP", "34080")


def fetch_inventory():
    query = {
        "query": {
            "model": "my",
            "condition": "used",
            "options": {},
            "arrangeby": "Price",
            "order": "asc",
            "market": "TR",
            "language": "tr",
            "super_region": "europe",
            "zip": ZIP_CODE,
            "range": 0,
            "region": "TR",
        },
        "offset": 0,
        "count": 50,
        "outsideOffset": 0,
        "outsideSearch": False,
        "isFalconDeliverySelectionEnabled": False,
        "version": None,
    }

    response = requests.get(
        INVENTORY_URL,
        params={"query": json.dumps(query, separators=(",", ":"))},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Referer": (
                "https://www.tesla.com/tr_TR/inventory/used/my"
                "?arrangeby=plh&zip=34080&HasVehiclePhotos=true"
            ),
            "Origin": "https://www.tesla.com",
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise RuntimeError("Tesla API beklenmeyen yanıt döndürdü; envanter güvenilir şekilde okunamadı.")
    return extract_vehicles(data)


def extract_vehicles(data):
    vehicles = []
    for obj in data.get("results", []):
        vin = obj.get("VIN") or obj.get("vin")
        if not vin:
            continue
        vehicles.append({
            "vin": vin,
            "model": obj.get("TrimName") or obj.get("Model") or "Model Y",
            "price": obj.get("InventoryPrice") or obj.get("Price") or obj.get("TotalPrice"),
            "year": obj.get("Year"),
            "url": f"https://www.tesla.com/tr_TR/my/order/{vin}",
        })
    unique = {vehicle["vin"]: vehicle for vehicle in vehicles}
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
        lines.append(vehicle["url"])
        lines.append("")
    lines += [
        "Envanter sayfası:",
        "https://www.tesla.com/tr_TR/inventory/used/my?arrangeby=plh&zip=34080&HasVehiclePhotos=true",
    ]

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

    current = {vehicle["vin"] for vehicle in vehicles}
    new_vins = current - seen

    # First successful run establishes a baseline; it does not email existing listings.
    if not STATE_FILE.exists():
        print("İlk başarılı çalışma: mevcut ilanlar başlangıç listesine kaydedilecek; e-posta gönderilmeyecek.")
    elif new_vins:
        new_vehicles = [vehicle for vehicle in vehicles if vehicle["vin"] in new_vins]
        send_email(new_vehicles)
        print(f"{len(new_vehicles)} yeni ilan için e-posta gönderildi.")
    else:
        print("Yeni ilan yok.")

    STATE_FILE.write_text(
        json.dumps(sorted(seen | current), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"HATA: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
