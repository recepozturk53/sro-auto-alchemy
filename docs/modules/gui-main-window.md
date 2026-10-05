# Modül: `gui/main_window.py`

**Katman:** L1 Arayüz · **Sınıf:** `MainWindow` · **Boyut:** 500x720, yeniden boyutlandırılamaz

## Ne yapar

Uygulamanın tek ekranı. Yedi bölümden oluşur ve bot nesnelerinin sahibidir.

## Bölümler ve widget'lar

| Bölüm | Metot | İçerik |
|---|---|---|
| Mod seçimi | `_create_mode_selector` | `plus` / `stat` radio butonları (`_mode_var`) |
| Ayarlar | `_create_settings_section` | Hedef plus, hedef stat, `animation_delay`, `click_delay` girdileri |
| Stat hedef kaynağı | `_on_stat_target_change` | Log aralığı / eşya tooltip yüzdesi seçimi |
| Koordinat | `_create_coordinate_section` | `Pick Fuse Button`, `Select Log Area`, `Test OCR` butonları + etiketler |
| Yüzde koordinatları | `_pick_item_hover`, `_pick_percent_roi`, `_test_percent_ocr` | Eşya noktası, tek yüzde alanı ve OCR ön testi |
| Kontrol | `_create_control_section` | `▶ Start`, `⏸ Pause`, `⏹ Stop` |
| Durum | `_create_status_section` | Durum metni + `Current` / `Target` / `Iterations` etiketleri |
| Log | `_create_log_section` | Salt-okunur `CTkTextbox` (yükseklik 120) |

## Kurulum sırası

```
__init__ → ctk.set_appearance_mode("dark") + set_default_color_theme("dark-blue")
         → ctk.CTk() kök pencere
         → SelectionHelper()
         → _create_widgets()   ← bölümleri kurar
         → _load_config()      ← config.json'dan koordinat + zamanlama
         → _setup_bots()       ← PlusModeBot/StatModeBot + callback bağlama
```

## Bot yaşam döngüsü

| Metot | Davranış |
|---|---|
| `_start_bot` | `is_configured()` kontrolü → `int()`/`float()` parse → `configure()` + `start()` → buton durumları |
| `_pause_bot` | `_plus_bot.pause()` veya `_stat_bot.pause()` |
| `_stop_bot` | `stop()` + durum "Stopped" |
| `_on_status_change` | `BotStatus` → durum rengi/butonları (`COMPLETED`/`FAILED`/`STOPPED` butonları açar) |
| `_on_log` | `_log_message(message)` → textbox'a ekle |

`self._current_mode` (`"plus"` / `"stat"`) hem `_start_bot` hem `_test_ocr` tarafından
kullanılır; `_on_mode_change` bunu günceller ve hangi ayar çerçevesinin görüneceğini
belirler (`pack_forget()` / `pack()`).

Stat içindeki `Item tooltip %` seçeneği ayrıca `Pick Item Hover`, `Select % Area`
ve `Test % OCR` kontrollerini gösterir. Alan seçimi ve OCR testi pencereyi
simge durumuna indirip kullanıcıya eşyaya **elle** hover yapması için 8 saniye
verir; sonra görüntü dondurulur. Böylece kurulum adımı sentetik fare girdisine
bağlı değildir. Kullanıcı yalnızca hedef yüzdesini çevrelemelidir; örneğin
fiziksel saldırı `(+28%)`, çevresinde birkaç piksel pay bırakarak. Hedef etiketi
yüzde seçildiğinde `Target Percentage (%)`
olur; girilen `57` değeri `57%` hedefidir.

## `_test_ocr` akışı

En değerli hata ayıklama aracı:

1. ROI genişliği/yüksekliği 0 ise uyarı ver, çık.
2. Oyun penceresini öne getir (`_stat_bot._bring_window_to_front()`) + 0.4 sn, `screen_capture.capture_region(*log_roi)`, sonra GUI'yi geri öne al. (Eskiden GUI log alanını örtüyordu ve görüntü bot penceresinin kendisiydi.)
3. `cv2.imwrite("debug_log_region.png", log_image)` — **çalışma dizinine** yazar.
4. `ocr_processor.process_log_region(img, mode=self._current_mode, threshold=..., psm=...)`
5. Log kutusuna `raw_text`, `result_type`, `value`/`error` yazar.

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Yeni widget/bölüm | `_create_widgets` içine yeni `_create_*` + çağrısı |
| Yeni ayar girdisi | `_create_settings_section` + `_start_bot` parse kısmı |
| Yeni buton | `_create_coordinate_section` / `_create_control_section` + handler |
| Durum gösterimi | `_on_status_change` |
| OCR hata ayıklama | `_test_ocr` |

## Dikkat

- **Tk main thread kuralı.** Bot callback'leri **bot thread'inden** gelir; yalnızca
  `_post_ui(func, *args)` ile `_ui_queue`'ya konur, ana thread `_drain_ui_queue`
  ile her `UI_POLL_MS` (50 ms) uygular. Doğrudan widget çağrısı ya da bot
  thread'inden `root.after` `stop()`→`join()` sırasında kilitlenir (gotcha §2).
  Bkz. [gotchas.md](../gotchas.md).
- Yeni girdi alanı eklerken `_start_bot`'ta `int()`/`float()` parse **ve**
  `ValueError` yakalama unutulmamalı; ayrıca `configure()`'a parametre geçmelidir.
- `_test_ocr` dosyayı CWD'ye yazar; `.gitignore`'da `debug_log_region.png` yok —
  depo köküne düşebilir.
- Renkler (`green`/`orange`/`red`) durum semantiğini taşır; yeni durum eklersen
  `_on_status_change` içindeki `elif` zincirini güncelle.
