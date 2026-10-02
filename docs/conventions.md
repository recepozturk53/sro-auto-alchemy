# Kod Kuralları

Mevcut kodun **fiili** konvansiyonları. Yeni kod bunlara uyar; sapma gerekiyorsa burada güncelle.

## Genel

- 4 boşluk girinti, satır sonu `\n`, dosyalar UTF-8 (Python 3 varsayılanı).
- Noktalı virgül ve iki nokta kullan; satır sonu noktası koyma.
- Tip ipuçları kullan: `x: int`, `roi: Tuple[int,int,int,int]`, `Optional[...]` nullable için.
  Dönüş tipi metot imzasında **her zaman** yazılı (`-> None`, `-> bool`).
- Docstring: modülün üstünde üç satır (tek satır özet + boşluk + ayrıntı).
  Metotlarda mevcut stil: `Args:` / `Returns:` blokları (Sphinx stili), opsiyonel.
- **Yorumlar İngilizce, dokümantasyon Türkçe.** Kod içi yorum eklerken İngilizce yaz.

## İsimlendirme

| Öğe | Biçim | Örnek |
|---|---|---|
| Modül | `snake_case` | `screen_capture.py` |
| Sınıf | `PascalCase` | `PlusModeBot` |
| Fonksiyon/metot | `snake_case` | `_perform_iteration` |
| Sabit / sınıf regex'i | `UPPER_SNAKE` | `PLUS_PATTERN` |
| Örnek değişken | `snake_case` | `log_roi` |
| Bot özel durum değişkeni | `_` öneki | `_current_plus`, `_animation_delay` |

`_` öneki: modül içi/privat. GUI'de `self._xxx` widget öznitelikleri bu kuralı kullanır.

## Import düzeni

```python
"""Module docstring."""            # 1. docstring

import re                           # 2. stdlib
import threading
from typing import Optional         #    stdlib from-import'lar

import cv2                          # 3. 3rd party (alfabetik)
import numpy as np

from .config import config_manager  # 4. göreli, proje içi
```

- `src/` içinde **daima göreli import** (`from .bot_base import BotBase`).
- `main.py` kök seviye olduğu için mutlak `from src.gui...` kullanır.
- Projeler arası import **yok**.

## Singleton deseni

`config.py`, `ocr.py`, `screen_capture.py` aynı deseni kullanır — yeni bir servis
eklerken **kopyala**:

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

my_service = MyService()   # dosya sonunda global örnek
```

Kural: `__init__` yeniden çalışsa da tekrar state üretmemesi için `_initialized`
kontrolü zorunlu. Tüketici modülleri **global örneği** import eder, sınıfı değil:
`from .ocr import ocr_processor`.

## Hata yönetimi

- Geniş `except Exception` **kabul** (Win32/OCR çağrıları çalışmada patlar), ancak
  `_log(...)` ile logla; sessizce yutma.
- Kullanıcıya görünür hatalar GUI log kutusuna: `self._log_message(f"ERROR: ...")`.
- `config.py` içinde `print()` kullanılır (GUI'den önce çalışabilir), `logging` değil.
- OCR hatası `ParseResult(success=False, result_type="unknown", error=...)` olarak
  döner; **istisna fırlatmaz**.

## Zamanlama

- Yalnızca `config` veya `configure()` ile gelen değerler ayarlanabilir.
- Sabit beklemeler (`0.3`, `0.1`, `1.0`) kasıtlıdır: pencere odaklanması ve
  animasyon güvenliği. Değiştiriyorsan `docs/gotchas.md` güncelle.

## Değişiklik disiplini

1. Katman bağımlılığını koru (`gui` → `core` tek yön).
2. Yeni modül ekle → `docs/module-index.json` + `docs/modules/<ad>.md` +
   `tools/verify_docs.py` yeşil.
3. Yeni ayar → `BotConfig` alanı + varsayılan + kaydediliyor mu kontrolü.
4. Yeni regex → sıra gerekçesi + `docs/modules/core-ocr.md`.
5. Yeni 3rd-party bağımlılık → `requirements.txt` **+** `sro_alchemy_bot.spec`
   `hiddenimports`.

## Ne yapma

- `core/` altında `tkinter`, `customtkinter`, `gui.*` import etme.
- Widget'a bot thread'den doğrudan dokunma (`root.after(0, ...)` kullan).
- `_perform_iteration` içinde `_check_pause_stop()` kontrolünü atlama.
- `config_manager.update()`'e `BotConfig`'te olmayan anahtar geçirme (sessizce düşer).
- `start()` çağırmadan önce `configure()` çağırmayı atlama.
- `parse_*` içinde OCR çağırma (ayrıştırma saf metin üzerinde çalışır).
- Kullanıcı `config.json`'u elle düzenlerken yeni anahtar uydurma (bilinmeyen alan sessizce yüklenmez).