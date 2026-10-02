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
| `src/core/bot_base.py` | L2 | `BotBase` ABC, thread yönetimi, durum makinesi, Win32 tıklama/pencere/alarm | [modules/core-bot-base.md](docs/modules/core-bot-base.md) |
| `src/core/bot_plus.py` | L2 | Plus modu ana döngüsü ve hedef kararı | [modules/core-bot-plus.md](docs/modules/core-bot-plus.md) |
| `src/core/bot_stat.py` | L2 | Stat modu ana döngüsü, `new_avg`/`new_value` çözümleme | [modules/core-bot-stat.md](docs/modules/core-bot-stat.md) |
| `src/core/screen_capture.py` | L3 | `mss` ile bölge yakalama, BGR ndarray üretimi | [modules/core-screen-capture.md](docs/modules/core-screen-capture.md) |
| `src/core/ocr.py` | L3 | ön işleme → Tesseract → regex ayrıştırma (`ParseResult`) | [modules/core-ocr.md](docs/modules/core-ocr.md) |
| `src/core/config.py` | L4 | `BotConfig` alanları, JSON kalıcılık, thread-safe erişim | [modules/core-config.md](docs/modules/core-config.md) |

> `sro_alchemy_bot_entegration_plan.md` **tarihsel plan dokümanıdır; kodla uyuşmaz.**
> Gerçekleşmeyen isimler: `ocr_engine.py` → `ocr.py`, `bot_worker.py` → `bot_base.py`+
> `bot_plus.py`+`bot_stat.py`, `input_controller.py` → `bot_base.py` içindeki Win32 yardımcıları,
> `assets/alarm.wav` → `winsound.Beep` ile üretilen tonlar, `app_window.py` → `main_window.py`.
> Doğru kaynak **koddur**, bu plan değil. ADR'ler: [adr/](docs/adr/).