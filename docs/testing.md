# Doğrulama

Test klasörü yok (`.gitignore` `tests/` ve `test_*.py` desenlerini dışlıyor).
Bu doküman, mevcut koşullarda **neyi nasıl doğrulayacağını** anlatır.

## Katman 0 — Sözdizimi (oyun gerekmez, en hızlı)

```powershell
python -m compileall -q src main.py
```

Hiçbir çıktı = başarılı. Bu, değişikliğin en azından **parse** edilebildiğini garanti eder.

## Katman 1 — İçe aktarma (oyun gerekmez, dikkat gerektirir)

```powershell
python -c "import src.core.ocr, src.core.config, src.gui.main_window; print('imports OK')"
```

> `src.core.screen_capture` içe aktarıldığında `mss.mss()` **oluşturulur**; etkin bir
> masaüstü oturumu gerekir. Terminal/GUI üzerinde sorunsuz çalışır.

## Katman 2 — Yapılandırma (oyun gerekmez)

```powershell
python -c "from src.core.config import config_manager; print(config_manager.config)"
```

Varsayılan `BotConfig(...)` gösterilmeli. `config.json` okunamıyorsa konsola
`Error loading config` basılır ve varsayılanlar kullanılır (çökmmez).

## Katman 3 — Pencere tespiti (oyun açıkken)

```powershell
python list_windows.py
```

Oyun penceresi `Macro_Client.exe` sürecine ait, sınıfı `MaxiGuard` olmalı
(başlık girişten sonra `[<karakter>] Oasis 2005` olur). Bulunamıyorsa
`bot_base.GAME_PROCESS_NAME` / `GAME_WINDOW_CLASS` sabitlerini kontrol et.

## Katman 3.5 — Tıklama teşhisi (oyun açıkken, botla aynı PowerShell'den)

```powershell
.\.venv\Scripts\python.exe diagnose_input.py          # yalnızca imleç kontrolü
.\.venv\Scripts\python.exe diagnose_input.py --click  # fuse butonuna basar
```

Beklenen çıktı:

```
Administrator : True/False
Game elevated : True/False/None
Fuse button   : (1237, 927)
Cursor area   : (...) - (...)
Fuse in area  : True
Before game   : OK -> cursor at (1237, 927)
Window        : activated
SendInput move: OK -> cursor at (1237, 927)
```

`Administrator : False` tek başına arıza değildir; oyun da aynı yetkiyle
çalışıyorsa giriş kabul edilebilir. `SendInput move: FAILED` durumunda
`Fuse in area`, `Before game`, `Game elevated`, gerçek imleç konumu ve
`SetCursorPos` sonucuna bak. `Game elevated: None` token okunamadı demektir;
`Game elevated: True`, `Administrator: False`, `Before game: OK` ve oyun önde
`SendInput move: FAILED` birleşimi yetki farkını doğrular. Bu durumda botu
yönetici PowerShell'den başlat; UAC bunu engelliyorsa sistem yöneticisinin
izni gerekir.

## Katman 4 — Entegrasyon: OCR testi (oyun açıkken)

Uygulamayı başlat: `python main.py`

1. **Pick Fuse Button** → oyundaki basma butonuna tıkla.
2. **Select Log Area** → log panelinin **yalnızca sayısal satırlarını** içine al.
3. **Test OCR** → log kutusunda şunları kontrol et:
   - `OCR Raw Text:` → ham metin (hata ayıklamanın ilk durağı)
   - `Result Type:` → `plus` / `stat` / `failed` / `unknown`
   - `Parsed Value:` → ayrıştırılan değer
   - `Tesseract ready: <sürüm>` → motor bulundu (yoksa `ERROR: Tesseract engine not found` → `TESSERACT_CMD` ayarla)

`unknown` dönüyorsa:
- Ham metne bak: beklediğiniz rakamlar var mı?
- Yoksa **ROI yanlış** (yanlış alan seçilmiş) veya **ön işleme** zayıf.
- Varsa **regex eşleşmiyor** → `docs/patterns.md` Tarif 2.

Ayrıca `debug_log_region.png` çalışma dizinine düşer: seçilen alanın gerçekten
doğru olduğunu görselle doğrula.

Bot çalışırken her tıklamadan önce `Log area before click: ...` satırı alanda
okunan metni gösterir (`<empty>` → alan yanlış/örtülü). Sonuç okunamayıp bot
durursa `logs/fuse_before.png`, `fuse_after.png` (ham) ve `*_ocr.png` (Tesseract'a
giden siyah-beyaz görüntü) kaydedilir.

## Katman 5 — Entegrasyon: bot turu (oyun açıkken)

0. **Botu yönetici olarak çalıştır** — SRO_Client yönetici ise bu şarttır (gotcha #13).
   Log'da `WARNING: Not running as Administrator...` varsa oyunun yetkisini de kontrol et.
1. Hedef değeri **gerçekçi** seç (ör. hedef `+1`); yüksek hedefle bekleme.
2. `▶ Start` → 3 saniyelik geri sayım → oyun penceresine geç.
3. Beklenen: pencere öne gelir, `Clicked at (x, y) [SendInput]` loglanır,
   `Iterations` artar, `Current` değişir.
   - `Click FAILED ... cursor could not be positioned` → `diagnose_input.py` ile imleç alanı ve giriş sonucunu kontrol et.
4. `⏸ Pause` → sayılar durur. `▶ Resume` → devam eder.
5. `⏹ Stop` → durur, durum `Stopped` olur.

## Katman 6 — Paketleme (isteğe bağlı, yavaş)

```powershell
pyinstaller sro_alchemy_bot.spec
```

`dist/SROAutoAlchemyBot.exe` çıkar. Tesseract sistemde kurulu olmalıdır
(bundled değildir). `console=False` olduğu için hata çıktısı görünmez;
sorun yaşarsan `console=True` yapıp yeniden derle.

## Hata ayıklama sırası

Sorun yaşadığında **dışarıdan içeri** doğru ilerle:

| Belirti | İlk kontrol |
|---|---|
| OCR boş/`unknown` | Katman 4 → `debug_log_region.png` ile ROI'yi gör |
| Değer yanlış çıkıyor | `raw_text` ile regex'in yakaladığı kısmı karşılaştır |
| Tıklama olmuyor | Aynı ortamda `diagnose_input.py` çalıştır; imleç alanı, hedef koordinat ve iki taşıma sonucuna bak. Oyun daha yüksek yetkideyse yetkileri eşitle. |
| Bot başlamıyor | Log kutusunda `ERROR: Please configure fuse button and log ROI` var mı? |
| Hemen duruyor | `current_plus >= target` → hedefi düşür |
| Düzensiz donuyor | `animation_delay` yetersiz olabilir → artır |
| GUI donuyor | `animation_delay` çok büyük → `stop()` işleyemiyor (gotcha #11) |

## Loglar

- `logs/bot.log` — uygulama başlangıç/bitiş kayıtları (`logging`)
- GUI log kutusu — bot mesajları (`_log` → `_on_log` → textbox)

İkisi farklı kanallardır; davranış hatası genelde **GUI log kutusundadır**.
