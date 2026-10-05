# Modül: `core/ocr.py`

**Katman:** L3 Servis · **Örnek adı:** `ocr_processor` · **Bağımlılık:** yok (saf servis)

## Ne yapar

Ekran görüntüsü ROI'sini metne, metni de anlamlı bir `ParseResult`'e çevirir.
Bu modül **tek OCR kapısıdır**: botlar doğrudan Tesseract çağırmaz, her zaman
`ocr_processor.process_log_region(...)` kullanır.

Tooltip yüzdesi ayrı `read_tooltip_percent(image)` yolundan okunur. Bu yol log
kaydırma çubuğu kırpmasını kullanmaz; küçük görüntüyü eşikleyip büyütür ve tek
satır olarak OCR yapar. `parse_tooltip_percent(text)` önce tek bir parantezli
bonus `(+N%)` arar; varsa aynı satırdaki aralık yüzdelerini yok sayıp onu döner.
Dar ROI parantezleri kesmişse tek bir `+N%` kabul edilir; artı işareti olmayan
aralık yüzdesi asla hedef olmaz. Ekranda `(+0%)` görüldüğü halde küçük `)`
karakteri OCR'da `(+0%0)` olabiliyor; yalnızca **parantez içindeki bonusun**
`%` sonrasındaki tek fazla `0` tolere edilir. Birden çok
bonus veya başka belirsiz alan okuma hatasıdır;
sessizce başka yüzde seçilmez.
Sağ kenarda kapanış parantezi kesilmişse `...(+22%` gibi yalnızca satırın
**sonunda** biten açık parantezli bonus da `22%` okunur.
`+` işareti `4` okunursa `(422%)` → `22%` olarak düzeltilir; yalnızca iki
basamaklı bonuslar (ve `100`) için bu dönüşüm yapılır, `(40%)` belirsiz kalır.
Tooltip alanı önce x2, sonra x3 nearest büyütmeyle okunur; tam alan başarısızsa
sağ yarısı da denenir. Geçerli okumalar farklı yüzde verirse sonuç reddedilir.

## Boru hattı

| Adım | Metot | Ne yapar |
|---|---|---|
| 0 | `locate_tesseract` (import anında) | `PATH` → yaygın kurulum dizinleri → `TESSERACT_CMD`; `get_tesseract_version()` ile doğrular |
| 1 | `preprocess_image(image, threshold, scale=2)` | `cvtColor(BGR2GRAY)` → **sabit** `threshold` → **invert** (mean<127) → `resize(scale, INTER_NEAREST)` → 20 px beyaz kenarlık |
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
# RANGE deseni: [(538 ~ 630) -> (551 ~ 646)]  (yüzdeli de olabilir)
{'old_range': (538.0, 630.0), 'new_range': (551.0, 646.0),
 'old_avg': 584.0, 'new_avg': 598.5, 'new_max': 646.0, 'improved': True}

# SIMPLE / ARROW desenleri: [12.2->12.4], (297->301]
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

Her desen için **son** (en yeni) eşleşme alınır. Köşeli/normal parantezler OCR'da
sık bozulduğu (`(`→`f`, `]`→`j`/`)`) için isteğe bağlıdır; `->` oku zorunludur.

1. `STAT_RANGE_PATTERN` `[(538 ~ 630) -> (551 ~ 646)]`, `[(82.9%~98.6%) -> (81.6%~97.1%)]`
   — yalnızca `_plausible_range` geçen eşleşmeler (her iki tarafta min ≤ max, sınır
   başına değişim 0.5x–2x). Aralık önce gelir: aksi halde sayıları `N->N` sanılır.
2. `STAT_SIMPLE_PATTERN` `[12.2->12.4]` / `(297->301]`
3. `STAT_ARROW_PATTERN` (çıplak `N->N`) — yalnızca metinde `chang` geçiyorsa
4. `FAILED_PATTERN` → `"failed"`
5. `"unknown"`

`stat_events(text)`: aynı desenlerle metindeki **tüm** sonuçları sırayla döner (aralık,
tek değer ve `ALCHEMY_FAILED_PATTERN` — sadece "alchemy/enhancement ... fail"). Bot yeni
sonucu, yeni satır şeridinde (`BotBase._new_line_strip`) bu listeyi okuyarak bulur (gotcha §20).

`crop_scrollbar(image)`: log alanının sağındaki kaydırma çubuğunu (sağ %15'te, yüksekliğinin
≥%60'ı parlak olan sütun) keser; `preprocess_image` her görüntüde uygular.

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
- **Oyun log'u 1 px bitmap fonttur** (yazı pikselleri tam 201, kenar yumuşatma
  yok). Önce eşikle, sonra `INTER_NEAREST` ile büyüt. Blur / cubic / Otsu /
  `MORPH_OPEN` ince çizgileri bozar: `538`→`638`, `551`→`651`, `]`→`j` (gotcha §18).
- Ölçüm (gerçek log görüntüsü): x2 eşik 120–180 her rakamı doğru okur; x3 `646]`'i
  `6463`, x4 `538`'i `638` okur. Varsayılan `DEFAULT_OCR_SCALE = 2`.
- 20 px beyaz kenarlık Tesseract'ın satır/karakter segmentasyonunu iyileştirir.
- `threshold` (config `ocr_threshold`, 150) sabit eşiktir; 90–180 arası çalışır.
- Tesseract konumu import anında çözülür (`locate_tesseract`); kullanıcı motoru
  sonradan kurarsa `extract_text` ilk çağrıda bir kez daha arar — uygulamayı
  yeniden başlatmak gerekmez.

## Test noktası

Gerçek log satırını dene (oyun açıkken):

```powershell
python main.py   # -> Log Area seç -> Test OCR
```

`Result Type` ve `Parsed Value` çıktısı bu modülün sözleşmesini doğrudan gösterir.
