# Sözlük (SRO alan dili)

> Projede geçen oyun ve implementasyon terimleri. Kod okurken karşına çıkabilecek
> her kısaltmanın karşılığı burada.

## Oyun terimleri

| Terim | Anlam | Kodda nerede |
|---|---|---|
| **SRO / Silkroad** | Silkroad Online (oyun) | README, pencere başlığı |
| **SRO_Client** | Macro_Client.exe'nin giriş ekranındaki pencere adı (girişten sonra `[<karakter>] Oasis 2005`); pencere süreç + `MaxiGuard` sınıfıyla bulunur | `bot_base.py` |
| **Alchemy / Harmony** | Bkz. Harmony |
| **+ (Plus) basma** | Bir eşyayı +1, +2, ... seviyeye yükseltme | `PlusModeBot`, `mode="plus"` |
| **Harmony basma** | Aynı eşyaya tekrar basma / yeniden harmoni | `StatModeBot`, `mode="stat"` |
| **Stat** | Eşyanın güç/özellik değeri (ör. `12.4`) | `StatModeBot` |
| **Fuse** | Basma butonu (nokta koordinatı seçilir) | `fuse_button_x/y` |
| **Başarısız basma (fail)** | Stat düşer / eşya kırılır | `result_type="failed"` |
| **Eşik (threshold)** | Basmayı durduracak hedef değer | `target_stat_threshold` |

## Implementasyon terimleri

| Terim | Anlam |
|---|---|
| **ROI** (Region of Interest) | Log'un okunacağı ekran dikdörtgeni `(x, y, w, h)` |
| **Iteration** | Bir basma turu: tıkla → bekle → yakala → OCR → karar |
| **Fuse click** | `fuse_button` koordinatına yapılan Win32 tıklaması |
| **Animation delay** | Tıklamadan sonra log yoklamaya başlamadan önceki **asgari** bekleme; asıl bekleme yeni sonuç satırı gelene kadar sürer |
| **Click delay** | İki tur arası bekleme |
| **Consecutive failures** | Üst üste gelen başarısız basma sayısı |
| **`ParseResult`** | OCR'ın çıktısını taşıyan veri sınıfı (`success`, `result_type`, `value`, `raw_text`, `error`) |
| **`result_type`** | `"plus"` \| `"stat"` \| `"failed"` \| `"unknown"` |
| **PSM** | Tesseract Page Segmentation Mode (`tesseract_psm`, varsayılan `6`) |
| **Otsu threshold** | OpenCV'nin otomatik eşik yöntemi; bitmap log fontunda yanlış okumaya yol açtığı için **kullanılmıyor** |
| **Whitelist** | Tesseract'a izin verilen karakter kümesi |
| **Bot state** | `IDLE`/`RUNNING`/`PAUSED`/`STOPPED`/`COMPLETED`/`FAILED` |
| **Stop reason** | Botun neden durduğu (`TARGET_REACHED`/`CRITICAL_FAILURE`/`USER_STOPPED`/`ERROR`) |
| **Singleton** | Modül başına tek örnek (`config_manager`, `ocr_processor`, `screen_capture`) |
| **RLock** | Yeniden girişli kilit; iç içe `with` güvenli |
| **Daemon thread** | Ana program çıkınca otomatik sonlanan arka iş parçacığı |
| **Marshal (thread)** | UI güncellemesini `root.after(0, ...)` ile ana thread'e taşımak |
| **pywin32** | `win32api`/`win32con`; tıklama + pencere kontrolü için birincil backend (ADR-0006) |
| **Macro_Client.exe** | Desteklenen tek oyun istemcisi (`E:\Games\Oasis 2005 MACRO`); yönetici olarak çalışır |
| **TESSERACT_CMD** | `tesseract.exe` yolunu elle belirten ortam değişkeni |
| **SendInput** | Fare/klavye olayını Raw Input kuyruğuna yazan Win32 API'si; `mouse_event`'ten farklı olarak oyunlara ulaşır (ADR-0007) |
| **Raw Input / DirectInput** | Oyunların girdiyi üst düzey mesaj kuyruğundan önce okuduğu katman |
| **UIPI / elevation** | Ön planda yükseltilmiş pencere varken yükseltilmemiş sürecin imleç kontrolünün engellenmesi; çözüm: botu yönetici çalıştırmak |

## Log formatları (gerçek örnekler)

| Format | Mod | Karşılık |
|---|---|---|
| `+7` | plus | `PLUS_PATTERN` → `value=7` |
| `Upgrade failed` | plus/stat | `FAILED_PATTERN` → `result_type="failed"` |
| `[12.2->12.4]` | stat | `STAT_SIMPLE_PATTERN` → `{old_value,new_value,improved}` |
| `[(538 ~ 630) -> (551 ~ 646)]` | stat | `STAT_RANGE_PATTERN` → `{old_range,new_range,old_avg,new_avg,new_max,improved}`; hedef **yeni aralığın üst sınırı** (646) ile karşılaştırılır |
| `(297->301]` | stat | `STAT_SIMPLE_PATTERN` |

> OCR bu metinleri **bozuk** üretebilir (`-` yerine `~`, eksik boşluk, fazladal şapka).
> Desenler bu varyasyonlara dayanıklı olacak şekilde yazıldı. Ham metni
> `ParseResult.raw_text` (log kutusunda "OCR Raw Text") altında görebilirsin.

## Terim → dosya hızlı haritası

| Aradığın | Aç |
|---|---|
| Basma döngüsü mantığı | `src/core/bot_plus.py` |
| Hangi regex hangi formatı yakalar | `docs/modules/core-ocr.md` |
| Ayar alanlarının tamamı | `docs/modules/core-config.md` |
| Ekran dikdörtgeni alma | `src/core/screen_capture.py` |
| Pencere bulma / tıklama | `src/core/bot_base.py` |
| Widget yerleşimi | `src/gui/main_window.py` |
| Bu işi hangi dosyada yapacağım | `python tools/ctx.py <konu>` |