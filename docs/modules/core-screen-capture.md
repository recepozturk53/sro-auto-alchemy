# Modül: `core/screen_capture.py`

**Katman:** L3 Servis · **Örnek adı:** `screen_capture` · **Bağımlılık:** yok

## Ne yapar

`mss` kütüphanesiyle ekranın belirli bir dikdörtgen bölgesini yakalar ve
**BGR numpy dizisi** olarak döner. Botların tek görüntü kaynağıdır.

## API

| Metot | Girdi | Çıktı | Not |
|---|---|---|---|
| `capture_region` | `x, y, width, height` | `np.ndarray` (BGR) | **Ana kullanım** |
| `capture_full_screen` | `monitor_index=0` | `np.ndarray` (BGR) | `monitors[1]` = primary |
| `capture_region_as_pil` | `x, y, w, h` | `PIL.Image` (RGB) | `ImageGrab` yerine kendi kuyruğunu kullanır |
| `get_screen_size` | `monitor_index=0` | `(width, height)` | |
| `save_capture` | `x, y, w, h, filepath` | `bool` | Hata durumunda `False` + `print` |
| `close` | — | `None` | `mss` oturumunu kapatır |

## Sözleşme

1. **Dönüş tipi BGR numpy.** `mss` BGRA verir; alfa kanalı `img[:, :, :3]` ile atılır.
   `cv2.cvtColor(..., COLOR_BGR2GRAY)` ve OCR bu sıralamayı bekler.
2. **Koordinatlar ekran-uzayı absolütdür** (widget-relative değil). `mss` çoklu monitör
   kavramını destekler; `capture_full_screen`'daki `monitor_index + 1` ofseti
   `monitors[0]`'ın tüm monitörler birleşimi olduğu içindir.
3. **Sınır doğrulaması yoktur.** Yanlış/ekran dışı dikdörtgen mss'nin davranışına bırakılır;
   ROI seçerken `RegionSelector` en az 10x10 px şartı koyar.
4. `_capture_lock` (RLock) ile serileştirilir: aynı anda iki yakalama yapılmaz.

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Yeni yakalama biçimi | Bu sınıfa metot ekle (bot sınıflarına değil) |
| Çoklu monitör desteği | `capture_full_screen` ve `capture_region` |
| Hata yönetimi | `save_capture` içindeki `try/except` |

## Dikkat

- **`mss.mss()` import anında oluşturulur** (`__init__` içinde). Bu modülü içe aktarmak
  etkin bir Windows masaüstü oturumu gerektirir; sunucu/CI ortamında import bile
  patlayabilir. Testleri hedef makinede çalıştır.
- `save_capture` hata durumunda `print` kullanır (GUI öncesi katman olduğu için
  `logging` yok) — bu bir istisnadır, yeni kod `logging` tercih etmeli.
- `capture_region_as_pil` **yeni bir yakalama yapmaz**; `capture_region` çağırıp
  kanal çevirir. İkisi arasında piksel farkı yoktur.