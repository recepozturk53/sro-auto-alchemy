# Modül: `core/ocr_samples.py`

**Katman:** L3 Servis · **Bağımlılık:** `core-ocr` · **Çıktı dizini:** `logs/ocr_samples/`

## Ne yapar

Botun okuduğu **her log şeridini**, okuduğu değerle isimlendirilmiş bir PNG olarak
diske yazar. Amaç kendi kendini büyüten, kendi kendini etiketleyen bir örnek
havuzu: parser bir satırı yanlış okuduğunda o kare elde kalır, elle düzeltilir ve
bundan sonraki her parser değişikliği o kareye karşı tekrar sınanır.

Bu modül **teşhis** içindir, bot akışının parçası değildir: `save_sample` her
istisnayı yutar ve `None` döner. Çalışan bir füzyon döngüsü örnek toplama
yüzünden asla bozulmaz.

## Dizin düzeni

```
logs/ocr_samples/
  ok/     10_to_3_20261009-184358-701.png       <- okunan değer dosya adında
          10_to_3_20261009-184358-701_ocr.png   <- Tesseract'ın gördüğü ikili görüntü
  error/  unreadable_timeout_<stamp>.png        <- okunamayan kare
          unreadable_timeout_<stamp>.txt        <- o karenin ham OCR metni
```

`error/` klasörü **iş kuyruğudur.** Bir kareyi öğretmek için:

1. `error/` altındaki PNG'ye bak, oyunun gerçekte ne yazdığını gör.
2. Dosyayı `ok/` altına, doğru değerle adlandırarak taşı:
   `10_to_3_<damgayı koru>.png`
3. `python tools/ocr_replay.py` → parser düzeltilene kadar **FAIL**, düzeltildikten
   sonra **PASS** gösterir.

## Etiket biçimi (`label_for`)

Dosya adının damgadan önceki kısmı etikettir; replay aracı `_<YYYYmmdd-HHMMSS-mmm>`
damgasını atıp geri kalanı parser'ın okuduğuyla karşılaştırır.

| `ParseResult` | Etiket |
|---|---|
| `{'old_value': 10, 'new_value': 3}` | `10_to_3` |
| `{'old_range': (549,644), 'new_range': (538,630)}` | `549-644_to_538-630` |
| `result_type="failed"` | `failed` |
| `None` / `success=False` | `unreadable` |

Sayılar `:g` ile yazılır, yani `549.0` → `549`. Kaydeden taraf ayrıca bir `note`
geçebilir (`timeout`, `passes-disagree`); replay bu ekleri karşılaştırmadan önce
siler.

## Kurallar

- **Dosya adı etiketin kendisidir.** İsimlendirme şeması değişirse
  `tools/ocr_replay.py` ile toplanmış tüm havuz geçersiz olur.
- `collect_ocr_samples` (bkz. `core-config`) kapalıysa hiçbir şey yazılmaz.
- Her dizin `MAX_SAMPLES_PER_DIR` (2000) ile sınırlıdır; en eski ham kare ve
  onun `_ocr.png` / `.txt` eşlikçileri birlikte silinir.
- `.gitignore` sadece ham PNG'leri izlenebilir bırakır: `_ocr.png` ve `.txt`
  gürültüsü depoya girmez. Elle etiketlenmiş `ok/` kareleri **commit edilmeye
  değerdir** — parser'ın regresyon takımıdır.

## Çağrı yerleri (`core-bot-base`)

`_collect_sample`, `_fuse_and_wait` içinde üç noktada çağrılır:

| Durum | Not | Nereye |
|---|---|---|
| Sonuç doğrulandı | — | `ok/` |
| OCR geçişleri anlaşamadı | `passes-disagree` | `error/` |
| `RESULT_TIMEOUT_MS` doldu | `timeout` | `error/` |

Kaydedilen görüntü, tüm ROI değil **yeni satır şeridi**dir (`_new_line_strip`):
eski sonuçlar kareye karışmaz.

## Doğrulama

```powershell
python tools/ocr_replay.py                 # tüm havuzu oynat
python tools/ocr_replay.py --only-failures # sadece uyuşmayanlar
python tools/ocr_replay.py --passes        # botun alternatif OCR geçişlerini de dene
```

Çıkış kodu: etiketli her örnek kendi etiketine ayrışıyorsa `0`, değilse `1`.
