# Tesla Türkiye ikinci el Model Y takip botu

Bu proje, Tesla Türkiye ikinci el Model Y envanterini GitHub Actions üzerinden yaklaşık 5 dakikada bir kontrol eder ve daha önce görülmemiş VIN'ler için Gmail bildirimi gönderir.

> Önemli: Tesla envanter API'si resmi, kararlı bir genel API değildir. Tesla tarafındaki değişiklikler veya erişim engelleri taramayı bozabilir. İlk çalıştırmada GitHub Actions loglarını kontrol edin. GitHub zamanlaması da tam 5 dakika garantisi vermez.

## Kurulum

1. Bu klasörün içeriğini GitHub deposunun kök dizinine yükleyin. `.github/workflows/monitor.yml` dosyasının da yüklendiğinden emin olun.
2. Depoda **Settings → Secrets and variables → Actions → New repository secret** bölümünden şu üç secret'ı ekleyin:
   - `GMAIL_ADDRESS`: bildirim gönderecek Gmail adresi
   - `GMAIL_APP_PASSWORD`: Google Hesapları üzerinden oluşturulan 16 karakterli Uygulama Şifresi (normal Gmail şifrenizi kullanmayın)
   - `MAIL_TO`: bildirimin gideceği adres (`a.burakcanakci@gmail.com`)
3. **Settings → Actions → General → Workflow permissions** altında **Read and write permissions** seçin.
4. **Actions** sekmesinden `Tesla used inventory monitor` iş akışını seçip **Run workflow** ile ilk kez çalıştırın.
5. İlk başarılı çalışma mevcut VIN'leri başlangıç listesi olarak kaydeder; mevcut ilanlar için e-posta göndermez. Sonraki çalışmalarda yeni VIN görülürse e-posta gönderilir.

## Hedef sayfa

https://www.tesla.com/tr_TR/inventory/used/my?arrangeby=plh&zip=34080&HasVehiclePhotos=true
