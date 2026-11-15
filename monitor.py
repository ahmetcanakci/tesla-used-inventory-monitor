import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import quote

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

INVENTORY_URL = "https://www.tesla.com/inventory/api/v4/inventory-results"
STATE_FILE = Path("data/seen_vins.json")
ZIP_CODE = os.getenv("TESLA_ZIP", "34080")


def build_query_url():
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
    return INVENTORY_URL + "?query=" + quote(json.dumps(query, separators=(",", ":")))


def fetch_inventory():
    # Open the API URL in a normal headless Chrome session rather than requests.
    # This does not bypass Tesla's access controls; if Tesla presents an access
    # denial/challenge page, fail safely and do not update the VIN state.
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1200")
    options.add_argument("--lang=tr-TR")
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(45)
        driver.get(build_query_url())
        body = driver.find_element(By.TAG_NAME, "body").text.strip()
        if not body:
            raise RuntimeError("Chrome boş yanıt aldı; Tesla API yanıtı okunamadı.")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            title = driver.title or "başlıksız sayfa"
            excerpt = body[:250].replace("\\n", " ")
            raise RuntimeError(
                f"Tesla JSON yerine HTML/metin döndürdü (sayfa: {title}). "
                f"Yanıt başlangıcı: {excerpt}"
            )
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise RuntimeError("Tesla API yanıtında beklenen results listesi yok.")
        print(f"Chrome ile Tesla API yanıtı alındı; toplam eşleşme: {data.get('total_matches_found', 'bilinmiyor')}")
        return extract_vehicles(data)
    except WebDriverException as exc:
        raise RuntimeError(f"Chrome/Selenium hatası: {exc}") from exc
    finally:
        if driver:
            driver.quit()


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
    return list({v["vin"]: v for v in vehicles}.values())


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
        lines.extend([vehicle["url"], ""])
    lines.extend([
        "Envanter sayfası:",
        "https://www.tesla.com/tr_TR/inventory/used/my?arrangeby=plh&zip=34080&HasVehiclePhotos=true",
    ])
    message = EmailMessage()
    message["Subject"] = f"Tesla ikinci el Model Y: {len(new_vehicles)} yeni ilan"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("\\n".join(lines))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)


def main():
    vehicles = fetch_inventory()
    print(f"Envanterde bulunan VIN sayısı: {len(vehicles)}")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        seen = set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    else:
        seen = set()
    current = {v["vin"] for v in vehicles}
    new_vins = current - seen
    if not STATE_FILE.exists():
        print("İlk başarılı tarama: mevcut ilanlar başlangıç listesine kaydedilecek; e-posta gönderilmeyecek.")
    elif new_vins:
        send_email([v for v in vehicles if v["vin"] in new_vins])
        print(f"{len(new_vins)} yeni ilan için e-posta gönderildi.")
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
