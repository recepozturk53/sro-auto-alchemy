# Modül: `core/ocr.py`

**Katman:** L3 Servis · **Örnek adı:** `ocr_processor` · **Bağımlılık:** yok (saf servis)

## Ne yapar

Ekran görüntüsü ROI'sini metne, metni de anlamlı bir `ParseResult`'e çevirir.
Bu modül **tek OCR kapısıdır**: botlar doğrudan Tesseract çağırmaz, her zaman
`ocr_processor.process_log_region(...)` kullanır.

## Boru hattı

| Adım | Metot | Ne yapar |
|---|---|---|
| 0 | `locate_tesseract` (import anında) | `PATH` → yaygın kurulum dizinleri → `TESSERACT_CMD`; `get_tesseract_version()` ile doğrular |
| 1 | `preprocess_image` | `cvtColor(BGR2GRAY)` → `resize(2x)` (h<200) → `GaussianBlur(3,3)` → `threshold(THRESH_BINARY + THRESH_OTSU)` → **invert** (mean<127) → `morphologyEx(MORPH_CLOSE, 2x2)` |
| 2 | `extract_text` | Tesseract yoksa boş string döner; varsa `pytesseract.image_to_string(..., --psm N --oem 3 -c tessedit_char_whitelist=...)` |
| 3 | `parse_*_result` | Saf metin → `ParseResult` (regex) |

## `ParseResult` sözleşmesi

```python
@dataclass
class ParseResult:
    success: bool                      # ayrıştırıldıysa True
    result_type: str                   # "plus" | "stat" | "failed" | "unknown"
    value: Optional[Any] = None
    raw_text: str = ""                 # OCR'ın ham çıktısı (debug için)
    error: Optional[str] = None
```

`value` şekli `result_type`'a bağlıdır:

| `result_type` | `value` tipi | İçerik |
|---|---|---|
| `"plus"` | `int` | Güncel + seviyesi |
| `"stat"` | `Dict[str, Any]` | Aşağıdaki iki şekilden biri |
| `"failed"` | `None` | Başarısızlık |
| `"unknown"` | `None` | Ayrıştırılamadı + `error` dolu |

Stat dict şekilleri **polimorfiktir** — bu, `bot_stat._extract_stat_value`'ın var olma
nedenidir:

```python
# RANGE deseni (yüzdeli aralık)
{'old_range': (82.9, 98.6), 'new_range': (81.6, 97.1),
 'old_avg': 90.75, 'new_avg': 89.35, 'improved': False}

# SIMPLE / PARENS / CHANGEDTO / ARROW desenleri
{'old_value': 297.0, 'new_value': 301.0, 'improved': True}
```

## Desen öncelik sırası (DEĞİŞTİRME, sözleşme)

`parse_plus_result` (satır ~125):

1. `FAILED_PATTERN` → `"failed"`
2. `PLUS_PATTERN` (`\+(\d+)`) → `"plus"`
3. `PLUS_ALT_PATTERN` (`plus N` / `item +N`) → `"plus"`
4. `SUCCESS_PATTERN` + 1..20 arası ilk tam sayı → `"plus"`
5. aksi halde `"unknown"`

> Neden `failed` önce? Başarısız basma logları da `+N` içerebilir; öncelik tersine
> çevrilirse başarısızlık başarı sanılır ve bot hedefe ulaşmış gibi durur.

`parse_stat_result` (satır ~191):

1. `STAT_CHANGEDTO_PATTERN` (SRO'ya özgü "been changed to")
2. `STAT_PARENS_PATTERN` `(297->301]`
3. `STAT_RANGE_PATTERN` `[(82.9%~98.6%) -> (81.6%~97.1%)]`
4. `STAT_SIMPLE_PATTERN` `[12.2->12.4]`
5. `STAT_ARROW_PATTERN` (genel `N->N`)
6. `FAILED_PATTERN` → `"failed"`
7. `"unknown"`

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Yeni log formatı | Sınıf seviyesine `re.compile` desen ekle, `parse_*` içinde uygun **sıraya** yerleştir |
| OCR ön işleme ince ayarı | `preprocess_image` |
| Tesseract parametreleri | `extract_text` içindeki `config` satırı (whitelist dahil) |
| Tesseract konumu / doğrulama | `locate_tesseract`, `_tesseract_path_candidates` |
| Yeni mod | `process_log_region`'a `elif mode == ...` ve eşleşen `parse_*` |
| Hata ayıklama görseli | `debug_save_preprocessed` |

## Dikkat

- `parse_*` metotları **saf fonksiyondur**: OCR çağrısı yapmaz, yalnızca metin işler.
  Test edilebilirlik için bu ayrım korunmalı.
- Tüm metotlar `self._ocr_lock` (RLock) altında çalışır: Tesseract serileştirilir.
- OCR hatası istisna fırlatmaz; `extract_text` boş string döner, `process_log_region`
  `ParseResult(success=False, error="No text extracted")` üretir.
- Whitelist dar tutulmalıdır; genişletmek hem yavaşlatır hem yanlış karaktere yol açar.
- `mode` `"plus"`/`"stat"` dışındaysa `success=False` + `error` döner.
- `preprocess_image` çıktısı **koyu yazı / açık zemin** olmalıdır: oyun log'u
  açık-yazı/koyu-zemin olduğu için görüntü ortalama < 127 ise otomatik ters
  çevrilir. Bu adım kaldırılırsa Tesseract doğruluğu ciddi biçimde düşer.
- `threshold` parametresi yalnızca **yedektir**; `THRESH_OTSU` aktifken OpenCV onu
  yok sayar.
- Tesseract konumu import anında çözülür (`locate_tesseract`); kullanıcı motoru
  sonradan kurarsa `extract_text` ilk çağrıda bir kez daha arar — uygulamayı
  yeniden başlatmak gerekmez.

## Test noktası

Gerçek log satırını dene (oyun açıkken):

```powershell
python main.py   # -> Log Area seç -> Test OCR
```

`Result Type` ve `Parsed Value` çıktısı bu modülün sözleşmesini doğrudan gösterir.