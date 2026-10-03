# Mimari

> Kaynak gerçek: kod. Bu doküman kodun okunabilir özetidir; çelişirse **kod kazanır**.

## Katman modeli

| Katman | Konum | Thread | Sorumluluk |
|---|---|---|---|
| L0 | `main.py` | Tk main | logging, bağımlılık kontrolü, uygulama başlatma |
| L1 | `src/gui/` | Tk main **only** | Widget'lar, overlay, kullanıcı girdisi |
| L2 | `src/core/bot_*` | bot daemon | Basma döngüsü, durum makinesi, hedef kararı |
| L3 | `src/core/ocr.py`, `screen_capture.py` | çağıran thread | Piksel → metin → değer |
| L4 | `src/core/config.py` | herhangi (kilitli) | Ayarların kalıcı saklanması |

Bağımlılık yönü **yukarı**: `core` asla `gui` import etmez; `gui` `core`'u import eder.

## Tek iterasyonun veri akışı

`PlusModeBot` / `StatModeBot` içindeki `_perform_iteration()` şu sırayı izler:

```
 1. _bring_window_to_front()          SRO_Client penceresini öne getir
 2. sleep(0.3)                        odaklanma bekle
 3. _click_at(fuse_x, fuse_y, 50)     Win32 SetCursorPos + mouse_event
 4. sleep(animation_delay / 1000)     oyun animasyonu + log satırının oluşması
 5. _bring_window_to_front() + 0.1s   yakalamadan önce tekrar öne getir
 6. screen_capture.capture_region(*log_roi)          → BGR ndarray
 7. ocr_processor.process_log_region(img, mode, threshold, psm) → ParseResult
 8. sonuca göre karar:
      result_type == "plus" | "stat"  → değeri güncelle, hedefe ulaştıysa True döndür
      result_type == "failed"         → _consecutive_failures += 1
      success == False                → hata logla, döngüde kal
```

1 → 7 **her modda birebir aynıdır**; yalnızca 8. adım ve `mode`/`target` farklıdır.
Bu ortak kasıtlıdır: yeni mod eklerken 1–7'yi kopyalamak yerine `BotBase` yardımcılarını kullan.

## OCR boru hattı

```
BGR ndarray
  → cvtColor(BGR2GRAY)                 gri tonlama
  → resize(3x/2x) (h<200 / h<400)      küçük kırpımları büyüt
  → GaussianBlur(3,3)                 gürültü azaltma
  → threshold(THRESH_BINARY + THRESH_OTSU)   Otsu ile otomatik eşik
  → invert (mean < 127 ise)            açık-yazı/koyu-zemin → koyu-yazı/açık-zemin
  → morphologyEx(OPEN, 2x2)           kaydırma çubuğu / benek gürültüsünü at
  → morphologyEx(CLOSE, 2x2)          kopan çizgileri birleştir
  → copyMakeBorder(15 px beyaz)        Tesseract kenar boşluğu ister
  → pytesseract.image_to_string(--psm N --oem 3 -c tessedit_char_whitelist=...)
  → regex ayrıştırma                  ParseResult
```

Tesseract whitelist'i `ocr.py` içinde sabittir ve rakam, `+ - . > % ~ [ ] ( )` ile
harfleri içerir. Karakter kümesini genişletmek OCR hızını ve doğruluğunu etkiler —
değiştiriyorsan `docs/modules/core-ocr.md` ve `docs/gotchas.md` güncelle.

Tesseract motoru `ocr.py` import edilirken `locate_tesseract()` ile bulunur: önce
`PATH`, sonra `C:\Program Files\Tesseract-OCR`, `C:\Program Files (x86)\Tesseract-OCR`,
`%LOCALAPPDATA%\Programs\Tesseract-OCR` ve `TESSERACT_CMD` ortam değişkeni denenir;
`get_tesseract_version()` ile çalıştığı doğrulanır. Bulunamazsa OCR boş string döner
(`ocr_processor.is_tesseract_available` → `False`).

## Desen öncelik sırası (sözleşme)

`process_log_region` içinde hangi desenin önce denendiği **davranışsal bir sözleşmedir**.

| Mod | Öncelik sırası |
|---|---|
| `plus` | `FAILED` → `PLUS (+N)` → `PLUS_ALT (plus N / item +N)` → `SUCCESS` + 1..20 arası sayı → `unknown` |
| `stat` | `CHANGEDTO` → `PARENS` → `RANGE` → `SIMPLE` → `ARROW` → `FAILED` → `unknown` |

Yeni desen eklerken: **mevcut doğru davranışı bozmayacaksa** en uygun yere ekle.
`FAILED` plus'ta en başta çalışır çünkü "Failed" logu da `+N` içerebilir ve
başarısızlık başarı sanılmamalıdır.

## Thread modeli

| Yapı | Nerede | Not |
|---|---|---|
| Tk main loop | `MainWindow.run()` | Tüm widget'ların sahibi |
| Bot thread | `BotBase.start()` → `threading.Thread(daemon=True)` | `self._run_loop` içinde |
| Stop | `self._stop_event` (Event) | `stop()` set eder |
| Pause | `self._pause_event` (Event) | `pause()` toggle eder, `_check_pause_stop` bloklar |
| Durum kilidi | `self._state_lock` (RLock) | `BotStatus` okuma/yazma |
| Config kilidi | `ConfigManager._config_lock` (RLock) | JSON okuma/yazma |
| OCR kilidi | `OCRProcessor._ocr_lock` (RLock) | ön işleme + Tesseract serileştirilir |
| Capture kilidi | `ScreenCapture._capture_lock` (RLock) | mss serileştirilir |

Singleton deseni `__new__` + sınıf düzeyi `_lock` + `__init__` içinde `_initialized`
kontrolü ile uygulanır (`config.py`, `ocr.py`, `screen_capture.py`).

**Kritik kural:** `BotBase._update_status` ve `_log` içindeki callback'ler **bot
thread'inden** tetiklenir. `MainWindow._on_status_change` doğrudan `self._status_text.configure(...)`
çağırır — Tk thread-unsafe'dir. Yeni UI güncellemesi eklerken `root.after(0, ...)` ile
marshal et. Bkz. [gotchas.md](gotchas.md).

## Durum makinesi

```
        start()                hedef + eşik
IDLE ───────────► RUNNING ─────────────────────► COMPLETED
                   │  ▲                             │
         pause()   │  │ resume()         _max_failures│
                   ▼  │                             ▼
                 PAUSED ──────► FAILED ◄───── konfigüre değil / hata
                   │
                   │ stop()      user stop
                   ▼
                STOPPED
```

- `BotState`: `IDLE`, `RUNNING`, `PAUSED`, `STOPPED`, `COMPLETED`, `FAILED` (`bot_base.py:15`)
- `StopReason`: `TARGET_REACHED`, `CRITICAL_FAILURE`, `USER_STOPPED`, `ERROR` (`bot_base.py:25`)
- `BotStatus` (`bot_base.py:34`): `state`, `message`, `current_value`, `target_value`,
  `iterations`, `failures`, `stop_reason`

## Yapılandırma

`%APPDATA%\SroAutoAlchemy\config.json`, `BotConfig` dataclass'ı ile 1:1 eşlenir.
`config_manager.update(**kwargs)` her çağrıda diske yazar ve bilinmeyen anahtarları
sessizce düşürür. Alan adı = JSON anahtarıdır. Bkz. [modules/core-config.md](modules/core-config.md).

## Win32 birimleri

`bot_base.py` içinde üç yardımcı var ve bilinçli olarak ayrı modül yok:

| Yardımcı | Ne yapar |
|---|---|
| `_click_at(x, y, delay_ms)` | Önce **SendInput** (imleç + `LEFTDOWN`/`LEFTUP`), olmazsa `SetCursorPos` + `mouse_event`; imleç doğrulanmadan basılmaz |
| `_to_virtual_desktop(x, y)` | Sanal masaüstüne göre 0..65535 absolüt koordinat |
| `_is_elevated()` / `_cursor_near()` | Yönetici denetimi ve imleç doğrulaması |
| `_window_title_candidates(title)` | `title` → `SRO_Client` → `Silkroad` sıralı başlık parçaları |
| `_bring_window_to_front(title)` | pygetwindow varsa `restore()` + `activate()`; yoksa `EnumWindows` + `SetForegroundWindow` + Alt tuşu hilesi |
| `_play_alarm(kind)` | `winsound.Beep` ile success/failure/warning tonları |

Tıklama **SendInput** tabanlıdır ([ADR-0007](adr/0007-sendinput-and-elevation.md)):
SRO DirectInput/Raw Input okuduğu için `mouse_event` olayları oyuna ulaşmaz.
Pencere aktivasyonu **pygetwindow** ile yapılır
([ADR-0006](adr/0006-input-backend-pywin32-pygetwindow.md)); her iki bağımlılık da
isteğe bağlıdır ve yoksa saf `ctypes` yedeği devreye girer.

> **Yönetici yetkisi şarttır.** Ön planda yükseltilmiş bir pencere (genelde
> SRO_Client) varken Windows, yükseltilmemiş sürecin imleç kontrolünü engeller
> (`SetCursorPos` hata 0 ile başarısız olur). Bot yönetici olarak çalıştırılmalıdır.

Tanılamak için: `python list_windows.py`.