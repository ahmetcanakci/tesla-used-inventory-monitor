import json
import os
import smtplib
import sys
from email.message import EmailMessage
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

INVENTORY_PAGE_URL = "https://www.tesla.com/tr_TR/inventory/used/my?arrangeby=plh&zip=34080&range=0"
STATE_FILE = Path("data/seen_vins.json")


def fetch_inventory():
    # Önce kullanıcının verdiği resmi envanter sayfasını aç.
    # Sayfa başarılı yüklenirse, sayfanın kendi oturumunda yüklediği envanter
    # JSON kaynağını bulup aynı tarayıcı bağlamında okur.
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1200")
    options.add_argument("--lang=tr-TR")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60)
        driver.get(INVENTORY_PAGE_URL)
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        # Sayfanın ağ kayıtlarında envanter API isteğini ara.
        resources = driver.execute_script("""
            return performance.getEntriesByType('resource')
                .map(e => e.name)
                .filter(u => u.includes('/inventory/api/') && u.includes('inventory-results'));
        """)
        api_url = resources[-1] if resources else None

        if not api_url:
            # Bazı tarayıcı/yanıt durumlarında performans kaydı bulunmayabilir.
            body = driver.find_element(By.TAG_NAME, "body").text.strip()
            excerpt = body[:400].replace("\\n", " ")
            raise RuntimeError(
                "Envanter sayfası açıldı ancak sayfanın yüklediği inventory-results "
                f"JSON isteği bulunamadı. Sayfa metni: {excerpt}"
            )

        result = driver.execute_async_script("""
            const url = arguments[0];
            const done = arguments[arguments.length - 1];
            fetch(url, { credentials: 'include' })
                .then(r => {
                    if (!r.ok) throw new Error('HTTP ' + r.status);
                    return r.json();
                })
                .then(data => done({ok: true, data}))
                .catch(err => done({ok: false, error: String(err)}));
        """, api_url)

        if not result or not result.get("ok"):
            raise RuntimeError(
                "Tesla envanter JSON'u sayfa oturumundan okunamadı: "
                + str((result or {}).get("error", "bilinmeyen hata"))
            )
        data = result["data"]
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise RuntimeError("Tesla yanıtında beklenen results listesi yok.")
        print(f"Envanter sayfasından JSON alındı; toplam eşleşme: {data.get('total_matches_found', 'bilinmiyor')}")
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
    lines.extend(["Envanter sayfası:", INVENTORY_PAGE_URL])
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
