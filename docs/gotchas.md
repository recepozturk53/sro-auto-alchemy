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

Gerçek belirti (2026-10-04): "Durdur" → `stop()` ana thread'de `join()` beklerken
bot thread'i `configure()` içinde ana thread'i bekledi → karşılıklı kilit.
Bot thread'inden `root.after(...)` çağırmak da Tk çağrısıdır, aynı riski taşır.

**Savunma (uygulandı):** Bot callback'leri yalnızca `MainWindow._ui_queue`'ya yazar
(`_post_ui`); ana thread `_drain_ui_queue` ile her `UI_POLL_MS` (50 ms) uygular.
`BotStatus` kopyalanarak (`dataclasses.replace`) kuyruğa konur. Yeni callback
eklerken `_post_ui` kullan.

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

## 7. `_bring_window_to_front` başlıkla arıyordu  (ÇÖZÜLDÜ — ADR-0008)

Eskiden metot `window_title: str = "SRO_Client"` alır ama eşleştirme sabitti:
`'sro_client' in title.lower() or 'silkroad' in title.lower()`. Başka bir pencere
başlığı geçirsen bile o pencere bulunmazdı.

Başlık güvenilir değil: Macro_Client.exe giriş ekranında `SRO_Client`, girişten
sonra `[<karakter>] Oasis 2005` başlığını taşır. Artık `_find_game_window()`
pencereyi **süreç adı** (`Macro_Client.exe`) + **sınıf** (`MaxiGuard`) ile bulur;
başka SRO istemcileri yok sayılır. Başlık yalnızca aynı süreç içinde tercih için
kullanılır.

**Savunma:** Hedef istemci değişirse `bot_base.GAME_PROCESS_NAME` /
`GAME_WINDOW_CLASS` sabitlerini güncelle. Tanılamak için `python list_windows.py`.

## 8. `mss` ve `pytesseract` import/çalışma zamanı bağımlılıkları

- `screen_capture` import edilirken `mss.mss()` **oluşturulur** → etkin Windows masaüstü
  oturumu şarttır. CI/headless ortamda import patlayabilir.
- `check_dependencies()` Tesseract yoksa **uyarı** verir ama uygulamayı açık bırakır.
- `ocr.py` import edilirken `locate_tesseract()` çalışır: önce `PATH`, sonra
  `C:\Program Files\Tesseract-OCR`, `C:\Program Files (x86)\Tesseract-OCR`,
  `%LOCALAPPDATA%\Programs\Tesseract-OCR` ve `TESSERACT_CMD` denenir; sürüm
  çalıştırılarak doğrulanır. Bulunamazsa `extract_text` boş string döner ve
  `ocr_processor.is_tesseract_available` `False` olur (GUI'de "Test OCR" bunu loglar).
- `pywin32` import anında denenir; eksikse `bot_base` sessizce `ctypes` yedek
  yoluna düşer.

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

## 11. Animasyon bitmeden tekrar tıklamak fuse'u iptal eder  (ÇÖZÜLDÜ)

Fuse'a basınca animasyon başlar ve buton **"Cancel"** olur; sonuç log'a düşünce
tekrar "Fuse" olur. Eski kod sabit `animation_delay` bekleyip tekrar tıklıyordu;
animasyon daha uzun sürünce ikinci tıklama fuse'u iptal ediyordu.

Artık `BotBase._fuse_and_wait()` tıklamadan önce log'un metnini saklar, tıkladıktan
sonra log ROI'yi yoklar ve **yalnızca alta yeni eklenen satırlarda** parse edilebilir
bir sonuç görünce döner (`_new_line_strip`, bkz. §20). Araya giren sohbet satırları sonucu
tetiklemez; ekranda duran eski sonuç tekrar okunmaz. `animation_delay` artık
yalnızca **asgari** bekleme; üst sınır `RESULT_TIMEOUT_MS` (20 sn). Beklemeler
`_stop_event.wait()` ile yapılır, "Durdur" hemen işler.

**Savunma:** Log ROI en az 2–3 satır içermeli: tek satırlık ROI'de aynı metinli
art arda iki sonuç (ör. iki "failed") görüntüyü değiştirmez ve 20 sn zaman aşımına
düşer.

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

Bu bir işletim sistemi güvenlik sınırıdır; `SendInput`, `PostMessage` vb. hiçbir
yol yükseltilmemiş süreçten yükseltilmiş pencereye girdi taşıyamaz. Doğrulanmış
örnek: pencere başlığı `SRO_Client`, süreç `Macro_Client`, token `elevated=1`.
İpucu: kullanıcı botun kendi penceresine tıklayınca (ön plan değişince)
`SetCursorPos` birden çalışır.

**Savunma:** `main.py` yönetici değilse kendini UAC ile otomatik yeniden başlatır
(`relaunch_elevated()`). Tıklama yine engellenirse `_abort_blocked_click()` botu
durdurur; eski log boşuna OCR'lanmaz. `BotBase.start()` yönetici değilse uyarı
loglar. Tanılamak için:

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

**Savunma:** `MORPH_OPEN` 2026-10-04'te kaldırıldı (1 px fontu bozuyordu, §18).
Sahte satırlar artık sonucu etkilemez: yalnızca tıklamadan sonra alta **yeni**
eklenen satırlar parse edilir ve stat aralıkları akla yatkınlık testinden geçer.

## 17. Yönetici olarak çalışırken pencere API'leri botu kilitler

`GetWindowTextLength`, çapraz-thread `ShowWindow`/`BringWindowToTop` (ve bunları
kullanan pygetwindow) hedef pencereye senkron mesaj gönderir. Yükseltilmemiş
süreçte UIPI mesajı reddettiği için sorun görünmez; **yönetici olunca** donmuş bir
pencere thread'i sonsuza kadar bekletir. Belirti: "1 second..." logundan sonra
hiçbir şey gelmez.

**Savunma:** Oyun penceresine yalnızca mesaj göndermeyen API'lerle dokun
(`InternalGetWindowText`, `GetClassNameW`, `ShowWindowAsync`, `IsHungAppWindow`)
— [ADR-0008](adr/0008-game-window-by-process.md). `stop()` takılan thread'in
yığınını loglar.

## 18. Bitmap log fontu: blur/Otsu/cubic büyütme rakamları değiştirir

SRO log'u kenar yumuşatmasız 1 px bitmap fonttur. Eski ön işleme (cubic x3 +
GaussianBlur + Otsu + MORPH) `538`'i `638`, `551`'i `651`, `]`'yi `j`/`3` okuyordu;
bot hedefi (646 ≥ 640) kaçırdı. Ölçüm: sabit eşik + `INTER_NEAREST` x2 her rakamı
doğru okur; x3/x4 hâlâ hata yapar.

**Savunma:** `preprocess_image` önce eşikler, sonra nearest büyütür
(`DEFAULT_OCR_SCALE = 2`). Ek güvenceler: `_plausible_range` (min ≤ max, 0.5x–2x),
zincir kontrolü (yeni `old_range` = önceki `new_range`) ve `ALT_OCR_PASSES` oylaması
(`BotBase._confirm_result`). Sonuç okunamazsa bot **tekrar tıklamaz, durur**.

## 19. Tıklamadan sonra log alanı oyunun ARKASINDAKİ pencereyi gösteriyor

Gerçek vaka (2026-10-04): `fuse_before.png` oyunu gösteriyor, tıklamadan sonra 20 sn
boyunca yakalama oyunun arkasındaki VS Code terminalini gösterdi; oyun ise ön
plandaydı. Olası nedenler: bir pencere log alanını örtüyor ya da oyun kendini
ekran yakalamadan gizliyor (`SetWindowDisplayAffinity`, anti-cheat).

**Savunma:** Her yoklamada `_ensure_log_area_visible()` log alanını örten pencereleri
(Z-sırası, mesaj göndermeden) bulur, loglar ve oyunu öne getirir; display affinity
≠ 0 ise uyarır. Alan boş okununca ve zaman aşımında `_log_capture_diagnostics()`
ön plan / simge durumu / dikdörtgen / affinity / örten pencereleri loglar.

## 20. Satıra kaydırılan sonuç "yeni satır" karşılaştırmasını kandırır

Sonuç mesajı 2–3 satıra bölünür; son satır yalnızca `%)].` olur. Yeni sonucun son
satırı öncekininkiyle aynı olduğundan satır bazlı fark (`_new_log_lines`) "yeni bir
şey yok" dedi ve bot 20 sn sonra durdu (gerçek vaka, 2026-10-04). Kaydırma çubuğu
da satır sonlarına rastgele karakter (`i`, `fa`, `r`) ekler.

Değer karşılaştırması da yetmedi: aynı sonuç üst üste gelince (`(139.9~171.0)` iki
kez) eski ile yeni ayırt edilemedi (gerçek vaka, 2026-10-04).

**Savunma:** `BotBase._new_line_strip` satırları **piksel** olarak karşılaştırır:
maske satır bantlarına bölünür, öncekinin son satırlarıyla yeninin ilk satırlarının
en uzun örtüşmesi bulunur, kalan satırlar yenidir ve **yalnızca o şerit** OCR'lanır
(iki mod için de). Üst kenarda kesik satırlar ve iki görüntüde aynı yerde duran alt
bant (panel ikonu) yok sayılır. Kaydırma çubuğu `ocr_processor.crop_scrollbar` ile
kesilir. Sınır: log alanını tamamen dolduran ardışık **piksel-aynı** sonuçlar
ayırt edilemez → bot güvenli durur; log alanını yüksek seçmek bunu azaltır.
