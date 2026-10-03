# AGENTS.md — SRO Auto-Alchemy Bot

> **Bu depo için tek zorunlu giriş noktası.** Kod yazmadan/okumadan önce burayı oku.
> Hangi dosyayı açacağını bilmiyorsan: `python tools/ctx.py <konu>` → sana minimal dosya listesi verir.
> Bu dosyayı güncellemeden kod değiştirme (bkz. [Bölüm 9](#9-bir-dosya-değiştirdiysen)).

---

## 1. Proje

Silkroad Online `SRO_Client` penceresi üzerinde çalışan **OCR tabanlı otomatik Alchemy botu**.
Fuse (basma) butonuna tıklar → animasyonu bekler → oyun log'unun ekran görüntüsünü alır →
Tesseract ile okur → hedef değere ulaşınca durur, sesli alarm çalar.

- **Windows-only**: `ctypes.windll`, `winsound`, `mss` kullanılır. Başka OS desteği yok.
- **Modlar**: `plus` (+ basma) ve `stat` (attribute / magic powder).
- **Arayüz**: CustomTkinter (dark tema), Tk **main thread**'de.
- **Dağıtım**: PyInstaller → `dist/SROAutoAlchemyBot.exe` (`sro_alchemy_bot.spec`).
- **Dil/konuş**: Kod ve yorumlar İngilizce, dokümantasyon Türkçe. Bu ayrımı koru.

## 2. Doğrulama komutları

```powershell
python -m compileall -q src main.py           # sözdizimi kontrolü (en hızlı)
python -c "import src.core.ocr, src.core.config"   # saf içe aktarma kontrolü
python main.py                                # tam uygulama (GUI açar, oyun gerekir)
python tools/verify_docs.py                   # bu harita kodla uyumlu mu?
python tools/ctx.py <konu>                    # "bu iş için hangi dosyalar?" (bkz. Bölüm 5)
```

> Test klasörü yok ve `.gitignore` `tests/`'i hariç tutuyor. Yeni test kütüphanesi
> ekliyorsan `requirements.txt` **ve** `sro_alchemy_bot.spec` hiddenimports'ını da güncelle.
> Doğrulama prosedürleri: `docs/testing.md`.

## 3. Mimari (5 katman, bağımlılık yönü ↓)

```
┌─ main.py ──────────── giriş: logging + bağımlılık kontrolü + Tk mainloop
│
├─ L1 GUI ············· src/gui/          CustomTkinter widget'ları, koordinat seçici
│                          │  yalnızca Tk main thread
├─ L2 ORCHESTRATION ···· src/core/bot_base.py   BotBase (ABC), BotState, StopReason, BotStatus
│                        src/core/bot_plus.py   PlusModeBot
│                        src/core/bot_stat.py   StatModeBot        ← bot thread (daemon)
│
├─ L3 SERVICES ········· src/core/screen_capture.py  mss → BGR ndarray  (singleton)
│                        src/core/ocr.py             OpenCV + Tesseract + regex (singleton)
│
└─ L4 CONFIG ·········· src/core/config.py   BotConfig (dataclass) + ConfigManager (singleton, JSON)
                                        │
              Win32 primitifleri (bot_base.py içinde) ── tıklama, pencere öne getirme, alarm
```

**Bağımlılık kuralı (asla ihlal etme):**

| Katman | İzin verilen import | Yasak |
|---|---|---|
| L1 GUI | `core.*` | `core.*` içinden GUI'ye import |
| L2 | `core.*` (aynı seviye) | Tkinter, customtkinter |
| L3 | `numpy`, `cv2`, `mss`, `pytesseract` | `gui.*`, `bot_*` |
| L4 | `json`, `os`, `threading`, `dataclasses` | `cv2`, `mss`, `pytesseract`, `gui.*`, `bot_*` |

`core` modülleri asla `gui`'ye bağımlı olmaz; bağımlılık yönü daima **yukarı**.

## 4. Modül haritası (hızlı yönlendirme)

| Dosya | Katman | Sorumluluk | Modül dokümanı |
|---|---|---|---|
| `main.py` | L0 | logging kurulumu, bağımlılık kontrolü, uygulama başlatma | [modules/entrypoint.md](docs/modules/entrypoint.md) |
| `src/gui/main_window.py` | L1 | Ana pencere, mod seçimi, girdi alanları, butonlar, log kutusu | [modules/gui-main-window.md](docs/modules/gui-main-window.md) |
| `src/gui/coordinate_picker.py` | L1 | Tam ekran overlay ile nokta (fuse) / dikdörtgen (log ROI) seçimi | [modules/gui-coordinate-picker.md](docs/modules/gui-coordinate-picker.md) |
| `src/core/bot_base.py` | L2 | `BotBase` ABC, thread yönetimi, durum makinesi, tıklama (SendInput→SetCursorPos; **yönetici yetkisi gerekir**) ve pencere (pygetwindow→ctypes) | [modules/core-bot-base.md](docs/modules/core-bot-base.md) |
| `src/core/bot_plus.py` | L2 | Plus modu ana döngüsü ve hedef kararı | [modules/core-bot-plus.md](docs/modules/core-bot-plus.md) |
| `src/core/bot_stat.py` | L2 | Stat modu ana döngüsü, `new_avg`/`new_value` çözümleme | [modules/core-bot-stat.md](docs/modules/core-bot-stat.md) |
| `src/core/screen_capture.py` | L3 | `mss` ile bölge yakalama, BGR ndarray üretimi | [modules/core-screen-capture.md](docs/modules/core-screen-capture.md) |
| `src/core/ocr.py` | L3 | Tesseract konum tespiti → ön işleme (Otsu + otomatik ters çevirme) → Tesseract → regex ayrıştırma (`ParseResult`) | [modules/core-ocr.md](docs/modules/core-ocr.md) |
| `src/core/config.py` | L4 | `BotConfig` alanları, JSON kalıcılık, thread-safe erişim | [modules/core-config.md](docs/modules/core-config.md) |

> `sro_alchemy_bot_entegration_plan.md` **tarihsel plan dokümanıdır; kodla uyuşmaz.**
> Gerçekleşmeyen isimler: `ocr_engine.py` → `ocr.py`, `bot_worker.py` → `bot_base.py`+
> `bot_plus.py`+`bot_stat.py`, `input_controller.py` → `bot_base.py` içindeki Win32 yardımcıları,
> `assets/alarm.wav` → `winsound.Beep` ile üretilen tonlar, `app_window.py` → `main_window.py`.
> Doğru kaynak **koddur**, bu plan değil. ADR'ler: [adr/](docs/adr/).
---

## 5. Görev → dosya yönlendirmesi (nereye ne yazılır)

Bu tablo **kaynak gerçeğidir**. Emin değilsen `python tools/ctx.py <konu>` çalıştır.

| Görev | Düzenlenecek dosya | Önce oku |
|---|---|---|
| OCR ön işleme / Tesseract ayarı | `src/core/ocr.py` | `docs/modules/core-ocr.md` |
| Tesseract bulunamıyor / OCR motoru | `src/core/ocr.py` (`locate_tesseract`) | `docs/modules/core-ocr.md` |
| Yeni log formatı / regex | `src/core/ocr.py` | `docs/modules/core-ocr.md` (sıra kuralı) |
| Stat değer çözümleme (`new_avg`/`new_value`) | `src/core/bot_stat.py` | `docs/modules/core-bot-stat.md` |
| Plus modu döngüsü / hedef | `src/core/bot_plus.py` | `docs/modules/core-bot-plus.md` |
| Yeni bot modu | `src/core/bot_<mod>.py` **+ `config.py` + `ocr.py` + `main_window.py`** | `docs/patterns.md` Tarif 1 |
| Thread / pause / stop / durum | `src/core/bot_base.py` | `docs/modules/core-bot-base.md` |
| Tıklama, pencere, alarm | `src/core/bot_base.py` | `docs/modules/core-bot-base.md` |
| Widget / buton / arayüz | `src/gui/main_window.py` | `docs/modules/gui-main-window.md` |
| Koordinat / ROI seçimi | `src/gui/coordinate_picker.py` | `docs/modules/gui-coordinate-picker.md` |
| Yeni ayar / varsayılan | `src/core/config.py` | `docs/modules/core-config.md` |
| Ekran görüntüsü / monitör | `src/core/screen_capture.py` | `docs/modules/core-screen-capture.md` |
| Bağımlılık / `.exe` paketleme | `requirements.txt` + `sro_alchemy_bot.spec` | `docs/modules/entrypoint.md` |
| Başlangıç / log kurulumu | `main.py` | `docs/modules/entrypoint.md` |

### 5.1 Sık yapılan yanlışlar

| Yanlış | Doğrusu |
|---|---|
| `core/` içine `import tkinter` | Botlar Tk bilmez; UI güncellemesi callback ile gelir |
| `start()` çağırıp `configure()`'ı atlamak | `configure()` önce; aksi halde `AttributeError` |
| Yeni regex'i ilk sıraya koymak | Mevcut öncelik sırasını koru, gerekçeni dokümana yaz |
| `config_manager.update(fuse_bttn_x=...)` | Alan adı `BotConfig` ile birebir olmalı, yoksa **sessizce** yutulur |
| Yeni stat deseni eklerken `_extract_stat_value`'yi unutmak | Sonuç `new_avg`/`new_value` anahtarlarına normalize edilmeli |
| Yeni bağımlılık eklerken spec'i atlamak | `requirements.txt` **+** `sro_alchemy_bot.spec` hiddenimports |
| Tıklamayı yalnızca `ctypes` ile bırakmak | pywin32/pygetwindow birincil; `ctypes` yedek yolunu da koru (ADR-0006) |
| `Click error: (0, 'SetCursorPos', ...)` görünce koda dalmak | Kök neden UIPI: botu **yönetici** olarak çalıştır (ADR-0007) |
| `mouse_event` ile oyuna tıklamayı beklemek | Raw Input oyunları görmez; `SendInput` kullan (ADR-0007) |
| Bot thread'den doğrudan `widget.configure()` | `root.after(0, ...)` ile marshal et |
| Yeni modül ekleyip haritayı güncellememek | `module-index.json` + `docs/modules/*.md` + `verify_docs.py` |

---

## 6. Değişiklik sonrası zorunlu kontrol

```powershell
python -m compileall -q src main.py     # sözdizimi
python tools/verify_docs.py             # harita <-> kod tutarlılığı
python tools/ctx.py <konu>              # yönlendirmeyi doğrula
```

Oyun gerektiren doğrulamalar: `docs/testing.md`.

---

## 7. Bilinen tuzaklar (özet)

Tamamı ve kanıtları: `docs/gotchas.md`.

1. `configure()` çağrılmadan `start()` → sessiz `AttributeError`.
2. Tk widget'ları bot thread'inden güncelleniyor (thread-unsafe).
3. `config_manager.update()` yazım hatalarını **sessizce** yutar.
4. `update()` her çağrıda diske yazar (döngüde çağırma).
5. OCR parser sırası davranışsal sözleşmedir.
6. Stat sonucu polimorfiktir; yeni desen `_extract_stat_value` ile eşleşmeli.
7. ~~`_bring_window_to_front` başlık parametresini kullanmıyor.~~ (ADR-0006 ile çözüldü)
8. `mss` import anında açılır; Tesseract eksikse uygulama yine açılır (uyarı).
9. `Test OCR` çalışma dizinine `debug_log_region.png` yazar.
10. `.gitignore` `tests/` ve `test_*.py`'yi dışlıyor.
11. `SetCursorPos` yönetici olmayan süreçte sessizce başarısız olur (UIPI, hata 0) → botu **yönetici** çalıştır.
12. `mouse_event` Raw Input oyunlarına ulaşmaz; tıklama **SendInput** ile yapılır.
13. İmleç doğrulanmadan tuşa basılmaz → yanlış yere tıklama koruması.
14. Log panelindeki kaydırma çubuğu OCR'a sahte satır üretir → `MORPH_OPEN` + beyaz kenarlık.

---

## 8. Araçlar

| Komut | Ne yapar |
|---|---|
| `python tools/ctx.py <konu>` | Konuya göre **minimal context**: oku → düzenle → kurallar → doğrula |
| `python tools/ctx.py --list` | Tüm görev ve modül anahtarları |
| `python tools/ctx.py --module <ad>` | Bir modülün sözleşmesi ve sembolleri |
| `python tools/ctx.py --file <yol>` | Bir dosyayı hangi modüller/görevler sahipleniyor |
| `python tools/verify_docs.py` | Haritanın kodla uyumunu denetler (CI'ya bağlanabilir) |
| `python list_windows.py` | SRO_Client penceresini bulur (pencere adı değiştiyse güncelle) |
| `python diagnose_input.py` | Tıklama teşhisi: yönetici mi, SendInput imleci hedefe taşıyor mu (imleci oynatır, **tıklamaz**) |

---

## 9. Bir dosya değiştirdiysen

Bu harita koda **bağlıdır**. Şunları yapmadan işi bitmiş sayma:

- [ ] Yeni kaynak dosya → `docs/module-index.json` modül girdisi + `docs/modules/<ad>.md`
- [ ] Yeni davranış kuralı → `docs/conventions.md` veya ilgili modül dokümanı
- [ ] Yeni tuzak keşfettin → `docs/gotchas.md`
- [ ] Mimari karar değişti → `docs/adr/` (eskiyi silme, `Superseded` işaretle)
- [ ] Yeni gerçek kullanım kalıbı → `docs/patterns.md` tarifi
- [ ] `python tools/verify_docs.py` → **PASSED** olmalı

---

## 10. Terimler

`+` basma, harmony, stat, fuse, ROI, PSM, Otsu, parse, iteration, daemon thread →
`docs/glossary.md`.