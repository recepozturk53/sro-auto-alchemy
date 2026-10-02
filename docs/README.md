# Dokümantasyon Haritası

> Katmanlı bilgi mimarisi: **önce az, sonra çok.** Ajanlar yukarıdan aşağı okur.

## Katman 0 — Her zaman

| Dosya | Ne zaman |
|---|---|
| [`AGENTS.md`](../AGENTS.md) | SESSION BAŞI. Mimari, katman kuralları, "nereye yazılır" tablosu. |
| [`module-index.json`](module-index.json) | Makine-okunur harita. `tools/ctx.py` bunu okur. |

## Katman 1 — Konuya göre seç

Ajan önce `tools/ctx.py <konu>` çalıştırır; o olmadan tahmin yürütmesin.

```powershell
python tools/ctx.py ocr           # OCR / regex / ön işleme değişikliği
python tools/ctx.py gui           # arayüz, widget, buton, girdi alanı
python tools/ctx.py config        # yeni ayar, varsayılan, kalıcılık
python tools/ctx.py bot           # bot döngüsü, mod, durum makinesi
python tools/ctx.py thread        # thread güvenliği, donma, callback
python tools/ctx.py window        # SRO_Client penceresi, tıklama, Win32
python tools/ctx.py capture       # ekran görüntüsü, ROI, monitör
python tools/ctx.py packaging     # .exe, pyinstaller, spec
python tools/ctx.py --list        # tüm konular
```

## Katman 2 — Modül sözleşmeleri

Her modül için: **ne yapar · neyi garanti eder · nereye dokunulur · nereye dokunulmaz.**

| Doküman | Kapsam |
|---|---|
| [modules/entrypoint.md](modules/entrypoint.md) | `main.py` |
| [modules/gui-main-window.md](modules/gui-main-window.md) | `src/gui/main_window.py` |
| [modules/gui-coordinate-picker.md](modules/gui-coordinate-picker.md) | `src/gui/coordinate_picker.py` |
| [modules/core-bot-base.md](modules/core-bot-base.md) | `src/core/bot_base.py` |
| [modules/core-bot-plus.md](modules/core-bot-plus.md) | `src/core/bot_plus.py` |
| [modules/core-bot-stat.md](modules/core-bot-stat.md) | `src/core/bot_stat.py` |
| [modules/core-ocr.md](modules/core-ocr.md) | `src/core/ocr.py` |
| [modules/core-screen-capture.md](modules/core-screen-capture.md) | `src/core/screen_capture.py` |
| [modules/core-config.md](modules/core-config.md) | `src/core/config.py` |

## Katman 3 — Derinlemesine

| Doküman | Ne içerir |
|---|---|
| [architecture.md](architecture.md) | Katman modeli, tek iterasyonun veri akışı, thread modeli, durum makinesi, OCR boru hattı |
| [conventions.md](conventions.md) | Kod kuralları: isimlendirme, tip ipuçları, docstring, hata yönetimi, import düzeni |
| [patterns.md](patterns.md) | Tarifler: yeni mod, yeni regex, yeni config alanı, yeni GUI alanı, yeni Win32 işlemi |
| [gotchas.md](gotchas.md) | Bilinen tuzaklar ve teknik borç (koddan doğrulanmış) |
| [glossary.md](glossary.md) | SRO alan dili: plus, stat, fuse, ROI, PSM, pazar/baz arası fark |
| [testing.md](testing.md) | Doğrulama prosedürleri ve manuel test senaryoları |
| [adr/](adr/) | Mimari karar kayıtları (neden böyle seçildi, alternatif neydi) |

## Bakım

- Yeni modül eklerken: `module-index.json` + `modules/<yeni>.md` + kaynak dosyada doküman başlığı.
- Harita koda bağlıdır: `python tools/verify_docs.py` kırık bağlantıları ve kapsam boşluklarını raporlar.