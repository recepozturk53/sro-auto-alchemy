# Bilinen Tuzaklar

> Koddan doğrulanmış, **yeniden keşfetmeye gerek yok**. Yeni tuzak bulursan buraya ekle.

## 1. `configure()` çağrılmadan `start()` → sessiz `AttributeError`

`PlusModeBot` ve `StatModeBot` içinde `_animation_delay`, `_click_delay`,
`_max_failures` **yalnızca `configure()`** içinde atanır; `__init__`'te atanmaz.
GUI doğru sırayla çağırır, ama yeni bir giriş noktası (CLI, test, script) eklemek
bu tuzağa düşer. Sonuç: bot başlar, ilk iterasyonda `Iteration error: '_animation_delay'`
loglar, döngüde kalır ve kullanıcı sebebi anlamaz.

**Savunma:** Her yeni giriş noktasında `configure(...)` → `start()` sırasını koru.
Daha iyisi: `__init__`'te varsayılanları atayarak `configure`'ı opsiyonel yapmak.

## 2. Tk widget'ları bot thread'inden güncelleniyor

`BotBase._update_status` ve `_log`, callback'leri **senkron** çağırır; bu
callback'ler bot thread'inde çalışır. `MainWindow._on_status_change` ise doğrudan
`self._status_text.configure(...)` çağırır. Tk thread-safe **değildir**; pratikte
çoğu zaman çalışır ama ani çökme (`Tcl_AsyncUpdate: fatal error`) veya donma
olasılığı vardır. Hata seyrek olduğu için teşhisi zordur.

**Savunma:** Bot callback'lerinden gelen her UI güncellemesini
`self.root.after(0, ...)` ile main thread'e taşı. Yeni callback eklerken bu kurala uy.

## 3. `config_manager.update()` yazım hatalarını sessizce yutar

`update` her anahtarı `hasattr(self._config, key)` ile denetler. `BotConfig`'te
olmayan bir alan (`target_pluss`, `animation_dealy`) **hata vermez**, sadece
uygulanmaz ve `False` dönen `update` yüzünden "ayarım çalışmıyor" belirtisi oluşur.

**Savunma:** `update(...)` çağrısından sonra `config_manager.config.<alan>` ile
değeri doğrula. Alan adlarını `docs/modules/core-config.md` tablosundan al.

## 4. `update()` her çağrıda diske yazıyor

`update` → `save` → `open/write`. Bot döngüsü içinde (her iterasyonda) çağrılırsa
gereksiz disk I/O olur.

**Savunma:** Ayar değişikliklerini toplu `update(...)` ile tek seferde yap.

## 5. OCR parser sırası davranışsal bir sözleşme

`parse_plus_result` içinde `FAILED_PATTERN` **önce** kontrol edilir. Sıra tersine
çevrilirse "Upgrade failed +7" gibi loglar başarı sayılır ve bot yanlışlıkla hedefe
ulaştığını sanır. `parse_stat_result` içinde `STAT_CHANGEDTO` ilk sırada; onu
aşağı alırsan `ARROW` deseni önce eşleşir ve aynı değeri farklı bir anahtarla döner.

**Savunma:** Yeni desen eklerken mevcut sırayı koru; değiştiriyorsan gerekçeni
`docs/modules/core-ocr.md` içine yaz ve iki modun davranışını da kontrol et.

## 6. Stat sonucu polimorfiktir

`ParseResult.value`, desene göre iki farklı şema döner:
`{old_value, new_value, improved}` **veya** `{old_range, new_range, old_avg, new_avg, improved}`.
`bot_stat._extract_stat_value` bunu normalleştirir; **yeni desen eklerken sonucu bu
iki anahtardan birine getirmezsen** `_extract_stat_value` `0.0` döner ve bot hiç
durdurmadan sürekli basar (hedef eşiğe asla ulaşamaz).

**Savunma:** Yeni stat desenini eklerken `parse_stat_result` **ve**
`_extract_stat_value` birlikte güncelle.

## 7. `_bring_window_to_front` parametresini kullanmıyor  (ÇÖZÜLDÜ — ADR-0006)

Eskiden metot `window_title: str = "SRO_Client"` alır ama eşleştirme sabitti:
`'sro_client' in title.lower() or 'silkroad' in title.lower()`. Başka bir pencere
başlığı geçirsen bile o pencere bulunmazdı.

Artık `_window_title_candidates(window_title)` kullanılır: sırayla `window_title`
→ `SRO_Client` → `Silkroad` denenir (pygetwindow ve ctypes yollarının ikisinde de).

**Savunma:** Oyuncu pencere adı özelleştirilmişse `_bring_window_to_front("...")`
çağrısına doğru başlığı ver. Tanılamak için `python list_windows.py`.

## 8. `mss` ve `pytesseract` import/çalışma zamanı bağımlılıkları

- `screen_capture` import edilirken `mss.mss()` **oluşturulur** → etkin Windows masaüstü
  oturumu şarttır. CI/headless ortamda import patlayabilir.
- `check_dependencies()` Tesseract yoksa **uyarı** verir ama uygulamayı açık bırakır.
- `ocr.py` import edilirken `locate_tesseract()` çalışır: önce `PATH`, sonra
  `C:\Program Files\Tesseract-OCR`, `C:\Program Files (x86)\Tesseract-OCR`,
  `%LOCALAPPDATA%\Programs\Tesseract-OCR` ve `TESSERACT_CMD` denenir; sürüm
  çalıştırılarak doğrulanır. Bulunamazsa `extract_text` boş string döner ve
  `ocr_processor.is_tesseract_available` `False` olur (GUI'de "Test OCR" bunu loglar).
- Yeni bağımlılıklar (`pywin32`, `pygetwindow`) da import anında denenir; eksikse
  `bot_base` sessizce `ctypes` yedek yoluna düşer.

**Savunma:** `mss`/`pytesseract` gerektiren testleri hedef makinede çalıştır.
Tesseract'ı PATH'e eklemek zorunda değilsin — yaygın kurulum dizinleri ve
`TESSERACT_CMD` otomatik denenir.

## 9. `Test OCR` çalışma dizinine PNG yazıyor

`main_window._test_ocr` → `cv2.imwrite("debug_log_region.png", log_image)` yol
kullanmadan CWD'ye yazar. Uygulamayı farklı bir dizinden başlatırsan dosya oraya düşer
ve depo kökü kirletilmez.

**Savunma:** Test ederken bu dosyayı temizle; sürüm kontrolüne sokma.

## 10. `tests/` ve `test_*.py` `.gitignore`'da

`.gitignore` hem `test_*.py`, `*_test.py` hem `tests/` desenlerini dışlıyor. Test
eklemek istersen bu engeli kaldırman gerekir (`.gitignore` güncellemesiyle birlikte).

## 11. `_perform_iteration` uzun süre bloklanabilir

`animation_delay` (varsayılan 2500 ms) boyunca döngü **hiç kontrol yapmaz**. Bu süre
içinde `stop()` çağrılsa bile `join(timeout=2.0)` zaman aşımına uğrar; döngü ancak
iterasyon sonunda `_check_pause_stop()` ile durur.

**Savunma:** `animation_delay` değerini gereğinden büyük ayarlama; kullanıcı "Durdur"
düğmesine bastığında lütfen beklenen süre kadar bekler.

## 12. Plan dokümanı kodla uyuşmuyor

`sro_alchemy_bot_entegration_plan.md` içindeki dosya adları (`ocr_engine.py`,
`bot_worker.py`, `input_controller.py`, `app_window.py`, `assets/alarm.wav`)
**gerçekleşmedi**. Gerçek yapı `docs/module-index.json` ve `docs/architecture.md`.

**Savunma:** Plan dokümanını kaynak olarak kullanma; AGENTS.md + module-index esas al.

## 13. `SetCursorPos` yönetici olmayan süreçte sessizce başarısız olur (UIPI)

Ön planda **yükseltilmiş (elevated)** bir pencere varken (SRO_Client genelde
yönetici olarak çalışır), Windows yükseltilmemiş süreçlerin fare/klavye
kontrolünü engeller. `SetCursorPos` `FALSE` döner; `GetLastError` `0`
(ERROR_SUCCESS) olduğu için pywin32 şu hatayı üretir:

```
Click error: (0, 'SetCursorPos', 'No error message is available')
```

**Savunma:** Botu **yönetici olarak** çalıştır. `BotBase.start()` yönetici
değilse uyarı loglar; `main.py` de konsola not basar. Tanılamak için:

```powershell
python -c "import ctypes; print(ctypes.windll.shell32.IsUserAnAdmin())"
```

## 14. `mouse_event` Raw Input okuyan oyunlara ulaşmıyor

SRO DirectInput/Raw Input kullanır. `SetCursorPos` + `mouse_event` olayları üst
düzey mesaj kuyruğuna enjekte eder ve oyun bunları **hiç görmez**; tıklama
sessizce kaybolur. `SendInput` aynı Raw Input kuyruğuna yazar.

**Savunma:** `_click_at` önce `SendInput` dener
([ADR-0007](adr/0007-sendinput-and-elevation.md)). Log'daki `[SendInput]` /
`[SetCursorPos + mouse_event]` etiketi hangi yolun kullanıldığını söyler.

## 15. İmleç doğrulanmadan tıklamak rastgele yere tıklar

Eski kod `SetCursorPos` başarısız olsa bile `mouse_event(LEFTDOWN)` gönderiyordu;
imleç hedefte olmadığı için tıklama rastgele bir pencereye gidiyordu.

**Savunma:** `_click_via_send_input` / `_click_via_set_cursor_pos` tıklamadan önce
`GetCursorPos` ile imlecin hedefte olduğunu doğrular (`_cursor_near`). Değilse
tuşa basılmaz ve `Click FAILED at (x, y)` loglanır.

## 16. Oyun log panelindeki kaydırma çubuğu OCR'a sahte satır üretir

SRO log ROI'sinin sağ kenarındaki kaydırma çubuğu ve panel butonları
binarizasyonda koyu lekelere dönüşür; Tesseract bunları `Van oe (Y]` gibi
satırlar olarak okur ve `raw_text` kirlenir.

**Savunma:** `preprocess_image` `MORPH_OPEN` uygular ve 15 px beyaz kenarlık
ekler. Kaldırılırsa sahte satırlar geri gelir.