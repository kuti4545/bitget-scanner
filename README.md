# Bitget kaldıraç tarayıcı

Bitget USDT-M vadeli paritelerini ~5 dakikada bir tarar.

Baktığı şeyler: **RSI, MACD, hacim, Bollinger, VuManChu Cipher B (WaveTrend + MFI), PVG**.
6.5+ puanı **Telegram**’a atar: LONG / SHORT.

Telefonun tarayıcıyı açık tutmasına gerek yok. Tarama GitHub sunucusunda çalışır.

## Telefondan kurulum

### 1) Telegram bot
1. Telegram’da [@BotFather](https://t.me/BotFather) → `/newbot`
2. Bot token’ı kopyala
3. Botuna `/start` yaz
4. Tarayıcıda aç: `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. `chat.id` numarasını kopyala (kendi sohbetin veya grup)

### 2) GitHub repo
1. Telefonda github.com → yeni **public** repo aç (ör. `bitget-scanner`)
2. Bu klasördeki dosyaları yükle (Add file → Upload, veya GitHub mobil)
3. Repo → **Settings → Secrets and variables → Actions**
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. **Actions** sekmesi → “I understand…” → workflow’u **Enable** et
5. **Bitget Tarama** → **Run workflow** (ilk deneme)

Public repo = ücretsiz sınırsız Actions dakikası.  
Kod herkese açık olur; Telegram mesajların özel kalır.

Private repo ücretsiz kotayı ~2 günde bitirir. O yüzden public tut veya taramayı 15-30 dk yap.

### 3) İsteğe bağlı site
Settings → Pages → Source: GitHub Actions değil, **Deploy from a branch**  
Branch: `main` / folder: `/docs`  
Adres: `https://KULLANICI.github.io/REPO/`

## Önemli sınırlar
- GitHub cron en sık **5 dakika** (eski 3-4 dk birebir olmaz)
- Yoğun saatte 5-15 dk gecikebilir
- Public repoda 60 gün commit olmazsa cron durur; ayda bir dosya güncelle
- Bu bir sinyal tarayıcıdır, yatırım tavsiyesi değildir. Kaldıraç likidasyon riski taşır.

## Eşikleri değiştirme
`.github/workflows/scan.yml` içindeki env:
- `ALERT_SCORE` varsayılan `6.5`
- `MAX_SYMBOLS` varsayılan `80` (24s hacme göre en likitler)
- `TIMEFRAME` varsayılan `15m` (`5m`, `1H` da olur)
- `MIN_USDT_VOLUME_24H` varsayılan `2000000`

## Local deneme
```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python scanner.py
```
