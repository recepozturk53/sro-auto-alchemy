# Modül: `core/config.py`

**Katman:** L4 Yapılandırma · **Örnek adı:** `config_manager` · **Bağımlılık:** yok

## Ne yapar

Tüm kalıcı ayarları iki sınıfta tutar ve JSON'a yazar:

- `BotConfig` (dataclass) — **şema**. Alan adı = `config.json` anahtarı.
- `ConfigManager` (singleton) — **erişim + kalıcılık**, RLock ile thread-safe.

Konum: `%APPDATA%\SroAutoAlchemy\config.json` (`_get_config_path`, satır ~72).

## `BotConfig` alanları

| Alan | Tip | Varsayılan | Anlamı |
|---|---|---|---|
| `fuse_button_x` / `fuse_button_y` | `int` | `0` | Basma butonu ekran koordinatı |
| `log_roi_x` / `log_roi_y` | `int` | `0` | Log bölgesinin sol-üst köşesi |
| `log_roi_width` / `log_roi_height` | `int` | `300` / `150` | Log bölgesi boyutu |
| `mode` | `str` | `"plus"` | `"plus"` veya `"stat"` |
| `target_plus` | `int` | `10` | Hedef + seviyesi |
| `current_plus` | `int` | `0` | Son okunan + seviyesi |
| `target_stat_threshold` | `float` | `100.0` | Hedef stat eşiği |
| `animation_delay` | `int` | `2500` | Tıklamadan sonra beklenecek süre (ms) |
| `click_delay` | `int` | `500` | İki tıklama arası bekleme (ms) |
| `sound_enabled` | `bool` | `True` | Alarm sesi açık mı |
| `ocr_threshold` | `int` | `150` | OpenCV eşik değeri |
| `tesseract_psm` | `int` | `6` | Tesseract sayfa bölütleme modu |

## API

| Metot | Davranış |
|---|---|
| `config` (property) | Kilitli `BotConfig` referansı döner |
| `update(**kwargs)` | Alanları günceller **ve diske yazar**; bilinmeyen anahtarları sessizce düşürür |
| `save()` / `load()` | `asdict` ↔ JSON (4 boşluk girinti) |
| `reset()` | Varsayılanlara döner ve kaydeder |
| `get_fuse_button()` → `(x, y)` | Kısayol |
| `set_fuse_button(x, y)` | Kısayol |
| `get_log_roi()` → `(x, y, w, h)` | Kısayol |
| `set_log_roi(x, y, w, h)` | Kısayol |
| `is_configured()` | `fuse_x > 0 and fuse_y > 0 and roi_w > 0 and roi_h > 0` |

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Yeni ayar | `BotConfig`'e alan + varsayılan ekle |
| Yeni kısayol erişim | `ConfigManager`'a metot ekle |
| Kalıcılık biçimi | `save()` / `load()` |

## Dikkat

- **`update()` sessizce yutar.** `hasattr` koruması sayesinde yazım hatası olan anahtar
  (`target_pluss`) hata vermez, sadece uygulanmaz. Yeni alan kullanırken adı `BotConfig`
  ile **birebir** karşılaştır.
- **`update()` her seferinde diske yazar.** Döngü içinde çağırmak I/O maliyeti yaratır;
  ayar değişikliklerini toplu yap.
- **Import yan etkisi:** `config_manager` modül yüklenirken `load()` çağrılır, yani
  `config.json` import anında okunur.
- `load()` da `hasattr` koruması kullanır: `config.json`'daki eski/garip anahtarlar
  sessizce yok sayılır, hata fırlatılmaz.
- Kilit `RLock`'tur (yeniden girişli): `update` → `save` → kilit almak güvenlidir.
- Bu modül **`cv2`/`mss`/`pytesseract`/`tkinter` import etmemelidir** (L4 kuralı).
- Alan adını **kaldırma**: `config.json` kullanıcının diskinde durur ve geriye uyumluluk
  beklenir.