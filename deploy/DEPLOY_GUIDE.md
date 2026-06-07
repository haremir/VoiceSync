# VoiceSync Canlı Sunucu (Production) Dağıtım Kılavuzu

Bu kılavuz, VoiceSync ses klonlama mikroservis altyapısının Ubuntu/Debian tabanlı canlı bir Linux sunucusunda Docker ve Nginx reverse proxy ile uçtan uca ayağa kaldırılması adımlarını içerir.

---

### Adım 1: Sunucuya Bağlantı ve Projenin Çekilmesi

Öncelikle terminal üzerinden canlı sunucunuza SSH ile bağlanın ve projeyi `/srv/voicesync` dizinine konumlandırın:

```bash
# 1. Sunucuya bağlanın (kendi sunucu IP veya alan adınızı girin)
ssh root@your_server_ip

# 2. Gerekli sistem paketlerini güncelleyin ve Git/Nginx/Docker kurulu değilse kurun
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y git nginx certbot python3-certbot-nginx

# 3. Proje dizinini oluşturun ve yetkilendirmeyi yapın
sudo mkdir -p /srv/voicesync
sudo chown -R $USER:$USER /srv/voicesync

# 4. Projeyi Git üzerinden dizine klonlayın
git clone -b feat/production-deploy https://github.com/haremir/VoiceSync.git /srv/voicesync
cd /srv/voicesync
```

---

### Adım 2: Ortam Değişkenlerinin Yapılandırılması (.env)

Üretim ortamında uygulamanın güvenliğini sağlamak için benzersiz ve güçlü bir API Key üreteceğiz:

```bash
# 1. Örnek yapılandırma dosyasını kopyalayın
cp .env.example .env

# 2. Python secrets modülü ile 24 baytlık (48 karakterli) güvenli rastgele anahtar oluşturun
python3 -c "import secrets; print(secrets.token_hex(24))"
# ÇIKTI ÖRNEĞİ: 8f31b26ac87f6e3c09da418e24c6d9bf809ef8956ac2f0d9

# 3. .env dosyasını nano editörü ile açın ve API_KEY değerini buraya yazın
nano .env
```

`.env` dosyasının içeriği şu şekilde olmalıdır (ürettiğiniz anahtarı yapıştırın):
```env
API_KEY=8f31b26ac87f6e3c09da418e24c6d9bf809ef8956ac2f0d9
VOICE_DEFAULT=default
```
*(Kaydetmek için: `CTRL + O`, `Enter` ve çıkmak için `CTRL + X` tuşlarına basın)*

---

### Adım 3: Referans Ses Kaydının Sunucuya Aktarılması (Voice Cloning)

Şirket yetkilisinin (Emir veya Uğur) seslendirdiği 10-15 saniyelik temiz bir ses kaydını (WAV veya MP3 formatında) kendi yerel bilgisayarınızdan sunucuya transfer edin:

```bash
# Kendi bilgisayarınızın terminalinden çalıştırın (sunucuya transfer)
scp /path/to/local/recording.wav root@your_server_ip:/srv/voicesync/voices/default.wav
```

---

### Adım 4: Docker Container'ın Derlenmesi ve Ayağa Kaldırılması

Docker katman önbelleğinden yararlanarak sunucuda derleme işlemini başlatıp konteyneri arka planda çalıştıracağız:

```bash
# Docker ve Docker Compose kurulu olduğundan emin olun
# Değilse resmi docker kurulumunu yapın: sudo apt-get install -y docker-compose-plugin docker.io

# Konteynerleri arka planda derleyerek ayağa kaldırın
docker compose up -d --build

# Konteyner durumlarını doğrulayın
docker compose ps
# Beklenen durum: voicesync-voicesync-1 container'ı "Up" (Çalışıyor) olmalıdır.

# Logları kontrol edin (model indirme ve ffmpeg yükleme adımlarını izleyebilirsiniz)
docker compose logs -f
```

---

### Adım 5: Nginx Reverse Proxy Yapılandırması

Trafik akışını yönetmek ve `/audio/` altındaki ses dosyalarını FastAPI AI motorunu yormadan doğrudan diskten yüksek hızla sunmak için Nginx konfigürasyonunu aktif edeceğiz:

```bash
# 1. Projedeki nginx.conf dosyasını Nginx sites-available dizinine kopyalayın
sudo cp deploy/nginx.conf /etc/nginx/sites-available/voicesync.conf

# 2. Sitenin aktif edilmesi için sembolik bağ (symlink) oluşturun
sudo ln -s /etc/nginx/sites-available/voicesync.conf /etc/nginx/sites-enabled/

# 3. Nginx yapılandırma dosyasının sözdizimini (syntax) doğrulayın
sudo nginx -t
# Beklenen çıktı: nginx: configuration file /etc/nginx/nginx.conf test is successful

# 4. Nginx servisini yeni ayarlarla yeniden yükleyin
sudo systemctl reload nginx
```

---

### Adım 6: Certbot ile Ücretsiz SSL (HTTPS) Sertifikası Kurulumu

Güvenli iletişim (HTTPS) ve API Key şifrelemesi için Let's Encrypt SSL sertifikasını Certbot aracılığıyla otomatik oluşturup Nginx'e entegre edin:

```bash
# Certbot'u çalıştırıp alan adınız için sertifika talebi oluşturun
sudo certbot --nginx -d voicesync.domain.com

# Cron üzerinde çalışan otomatik SSL yenileme zamanlayıcısını test edin
sudo certbot renew --dry-run
```

---

### Adım 7: WordPress ve Umbraco Panellerinde Test & Entegrasyon

Ağ ve güvenlik katmanları hazır olduğuna göre entegrasyonu tamamlayabilirsiniz:

1. **WordPress Ayarları:**
   - WordPress admin paneline girin -> **Ayarlar** -> **VoiceSync** yolunu izleyin.
   - **API URL:** `https://voicesync.domain.com` değerini girin.
   - **API Key:** Adım 2'de ürettiğiniz 48 karakterli güvenli anahtarı girin.
   - **Ses ID:** `default` (veya sunucuya yüklediğiniz WAV dosyasının adı).
   - Ayarları kaydedip yeni bir blog yazısı yayınlayarak asenkron ses üretimini test edin.

2. **Umbraco Ayarları:**
   - Projenizin `appsettings.json` dosyasını açıp aşağıdaki değerleri güncelleyin:
     ```json
     {
       "VoiceSync": {
         "ApiUrl": "https://voicesync.domain.com",
         "ApiKey": "8f31b26ac87f6e3c09da418e24c6d9bf809ef8956ac2f0d9",
         "VoiceId": "default"
       }
     }
     ```
   - Projeyi yeniden derleyip canlıya alın ve arka planda çalışan `VoiceSyncPoller` Background Service'in yayındaki içerikler için asenkron durumu başarıyla poll ettiğini doğrulayın.
