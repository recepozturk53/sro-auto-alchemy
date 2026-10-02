# ADR-0004: Servislerde Pervasive Singleton

**Durum:** Kabul — **teknik borç olarak işaretlendi**

## Bağlam

`ScreenCapture` (mss), `OCRProcessor` (Tesseract) ve `ConfigManager` kaynak
ağırlıklıdır ve birden çok yerden kullanılır: bot sınıfları, GUI, `_test_ocr`.
Her kullanımda yeni örnek üretmek hem pahalıdır hem de `mss.mss()` gibi
sistem kaynaklarını gereksiz yere açar.

## Karar

Üç servis de **modül düzeyinde singleton** olarak dışa açılır. Desen
`conventions.md` içinde şablon olarak tanımlıdır:

```python
class MyService:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            ...
            self._initialized = True

my_service = MyService()   # module-level instance
```

Tüketici **sınıfı değil örneği** import eder: `from .ocr import ocr_processor`.
Her servis ayrıca bir `RLock` ile kendi işini serileştirir (bkz. ADR-0002).

## Sonuçlar

**Artılar**
- Tek örnek garantisi (thread-safe `__new__`).
- Test ve hata ayıklamada paylaşılan durum: `_test_ocr` ile bot aynı
  `ocr_processor` örneğini kullanır, davranış birebir aynıdır.
- Çağrı tarafında kısa: `ocr_processor.process_log_region(...)`.

**Eksiler / borç**
- **Gizli bağımlılık:** Hangi servisin kullanıldığı import satırından görünmez;
  test sırasında mock'lamak zordur.
- **Import yan etkisi:** `screen_capture` import edilirken `mss.mss()` oluşturulur →
  etkin masaüstü oturumu şartı. CI'da import patlayabilir.
- `ConfigManager` import sırasında `config.json` okur; testler diske bağımlıdır.
- Singleton'lar testler arasında **state paylaşır** ve izolasyon gerektirir.

## Gelecek için

Boru hattı büyürse şu yönlerden birine geçilmelidir:
1. **Bağımlılık enjeksiyonu** — servisleri bot sınıflarına `__init__` ile geçirmek
   (`PlusModeBot(ocr=..., capture=...)`).
2. `contextvars` veya basit bir servis konteyneri.
3. En azından `close()`/reset hook'u ile test izolasyonu
   (`ScreenCapture.close` hâlihazırda mevcut).