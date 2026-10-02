# Tarifler (Patterns)

> "Şunu yapmak istiyorum" → izlenecek adımlar. Her tarif **dosya bazında** yazılmıştır.

---

## Tarif 1: Yeni bot modu ekle (örn. "Harmony Mode")

En sık yapılan iş. Katman sırası: **config → ocr → bot → gui → index → docs**

### 1. `src/core/config.py`
`BotConfig`'e hedef alanı ekle (tüm modlar için ortak alan yeterliyse atlama):

```python
target_harmony_threshold: float = 80.0
```

### 2. `src/core/ocr.py`
Yeni log formatı için desen ekle ve `parse_harmony_result` yaz:

```python
HARMONY_PATTERN = re.compile(r'\[\s*(\d+)\s*[-~>]+\s*(\d+)\s*\]', re.IGNORECASE)

def parse_harmony_result(self, text: str) -> ParseResult:
    with self._ocr_lock:
        if self.FAILED_PATTERN.search(text):
            return ParseResult(success=True, result_type="failed", raw_text=text)
        m = self.HARMONY_PATTERN.search(text)
        if m:
            old_v, new_v = float(m.group(1)), float(m.group(2))
            return ParseResult(success=True, result_type="harmony",
                               value={'old_value': old_v, 'new_value': new_v,
                                      'improved': new_v > old_v},
                               raw_text=text)
        return ParseResult(success=False, result_type="unknown", raw_text=text,
                           error="Could not parse harmony result")
```

Sonra `process_log_region` içine dal ekle:

```python
elif mode == "harmony":
    return self.parse_harmony_result(text)
```

> Deseni **var olan desenlerin uygun sırasına** yerleştir; en üste koyarsan
> mevcut davranışı bozabilir. Gerekçeni `docs/modules/core-ocr.md`'ye yaz.

### 3. `src/core/bot_harmony.py` (yeni dosya)
`bot_stat.py`'yi şablon al:

```python
class HarmonyModeBot(BotBase):
    def configure(self, target_threshold, animation_delay=1500,
                  click_delay=300, max_failures=10) -> None: ...
    def _run_loop(self) -> None:            # bot_base.md şablonu
        ...
    def _perform_iteration(self) -> bool:   # ortak 7 adım + sonuç dalı
        ...
```

1–7. adımları kopyalayabilirsin (`bot_plus.py:130`'dan itibaren) — kasıtlıdır.
`__init__` içinde zamanlama alanlarını da atamayı unutma (gotcha #1).

### 4. `src/gui/main_window.py`
- `_create_mode_selector` → yeni radio butonu (`_mode_var`'a yeni değer)
- `_on_mode_change` → yeni ayar çerçevesini göster/gizle
- `__init__` → `self._harmony_bot: Optional[HarmonyModeBot] = None`
- `_setup_bots` → örneği oluştur + `set_callbacks(...)`
- `_start_bot` / `_pause_bot` / `_stop_bot` → yeni dal (`elif self._current_mode == "harmony":`)
- `_create_settings_section` → hedef girdisi

### 5. Harita ve doküman
```powershell
python tools/verify_docs.py     # eksik kalanı raporlar
```
Sonra `docs/module-index.json`'a modül + görev girdisini ve `docs/modules/core-bot-harmony.md`
dosyasını ekle.

### 6. Doğrula
```powershell
python -m compileall -q src
python main.py                  # yeni modu seç, hedef gir, Start
```

---

## Tarif 2: Yeni regex / log formatı ekle

1. **Önce gerçek metni yaz.** Oyun log'undan ham satırı kopyala; tahmin etme.
   Ham metin `ParseResult.raw_text` içinde loglanır.
2. Sınıf seviyesine `re.compile` desen ekle, `re.IGNORECASE` kullan.
3. Uygun `parse_*_result` içinde, **mevcut sıraya göre** yerleştir.
4. Desen **genel olmalı**: OCR boşluk/şapka/dash varyasyonları üretir
   (`->`, `->>`, `~`, `-`). Karakter sınıflarını gevşek bırak:
   `r'\[\s*([\d.]+)\s*[-~>]+\s*([\d.]+)\s*\]'`
5. Sonucu mevcut şemalardan birine normalize et (`old_value/new_value` veya
   `old_range/old_avg`) — yoksa tüketici okuyamaz (gotcha #6).
6. **Test et:** oyun açıkken `Test OCR` → `Result Type` doğru mu?
   Sonra `Result Type: unknown` dönüyorsa desen eşleşmiyor demektir.
7. `docs/modules/core-ocr.md` sıra tablosunu güncelle.

---

## Tarif 3: Yeni config ayarı ekle

1. `src/core/config.py` → `BotConfig`'e alan + **açık varsayılan**.
2. GUI'den okunacaksa: `_create_settings_section` (widget) + `_start_bot`
   (parse + `configure`/`update` çağrısı) + `_load_config` (başlangıç değeri).
3. Kalıcı olacaksa: `update()` çağrısı diske yazar — `load()` otomatik gelir.
4. Doğrula:
   ```powershell
   python -c "from src.core.config import config_manager; print(config_manager.config)"
   ```
5. Alan adı `config.json` anahtarıdır; **yeniden adlandırma geriye uyumluluğu bozar**.

---

## Tarif 4: Yeni GUI widget / bölüm ekle

1. `_create_widgets` içine yeni `_create_xxx_section()` çağrısı ekle (bölüm sırası
   = ekran sırası).
2. Metot içinde `self._xxx` öznitelikleri oluştur (önek zorunlu).
3. Handler'ı `command=` ile bağla; handler'da **önce** girdi doğrula, sonra
   `config_manager.update(...)` çağır.
4. Bot callback'inden güncellenecekse `root.after(0, ...)` kullan (gotcha #2).
5. Pencere boyutu 500x720 sabit ve `resizable(False, False)`: yeni bölüm sığmazsa
   `geometry()` değerini büyüt **ve** `README.md`'deki ekran görüntüsü notunu güncelle.

---

## Tarif 5: Yeni Win32 işlemi ekle (klavye, ekran, pencere)

1. `src/core/bot_base.py` içine `_leading_underscore` metot olarak ekle — **bot
   sınıflarına değil**. Tüm Win32 birimleri burada toplanmıştır (ADR-0005).
2. `try/except Exception` içinde çalıştır, hatayı `self._log(...)` ile bildir.
3. `EnumWindows` tabanlı arama yapacaksan başlık eşleştirmesini `lower()` ile
   yap; sabit pencere adı kullanma, `list_windows.py` ile doğrula.
4. Test: oyun çalışırken konsol/log çıktısını gözlemle.

---

## Tarif 6: Yeni servis (singleton) ekle

`config.py`, `ocr.py`, `screen_capture.py` desenini **birebir** kopyala:
`__new__` + sınıf `_lock` + `__init__` içinde `_initialized` + dosya sonunda
global örnek. Tüketici modülleri sınıfı değil **örneği** import eder.