# Modül: `core/bot_stat.py`

**Katman:** L2 Orkestrasyon · **Sınıf:** `StatModeBot(BotBase)` · **Mod:** `stat`

## Ne yapar

Fuse butonuna tıklar, log'dan **stat / yüzde değerini** okur ve
`current_stat >= target_threshold` olduğunda başarı alarmıyla durur.
Ayrıca basılan değerlerin **en iyi / en kötü** değerini izler.

## Durum alanları

| Alan | Not |
|---|---|
| `_current_stat` | Son okunan değer |
| `_target_threshold` | Hedef eşik (GUI'den) |
| `_best_stat` / `_worst_stat` | `_run_loop` başında `_worst_stat = float('inf')` olarak sıfırlanır |
| `_consecutive_failures` / `_max_failures` | Plus moduyla aynı mantık (`10`) |
| `_animation_delay` / `_click_delay` | `configure()` ile gelir |

## `_extract_stat_value` — kritik nokta

OCR'ın stat sonucu **polimorfiktir** (bkz. [core-ocr.md](core-ocr.md)). Bu metot
tek noktada normalleştirir:

```python
if 'new_range' in value_data:   return value_data['new_range'][1]  # aralık: ÜST sınır
if 'new_value' in value_data:   return value_data['new_value']     # basit değer
return 0.0
```

- Aralık logunda `[(538 ~ 630) -> (551 ~ 646)]` hedef **yeni aralığın üst sınırıyla**
  (646) karşılaştırılır — kullanıcının istediği bu (2026-10-04).
- **Yeni bir stat desen ekliyorsan** sonucu bu iki anahtardan birine normalize et,
  yoksa `_extract_stat_value` `0.0` döner ve hedefe asla ulaşılamaz.
- `get_worst_stat()` `inf` durumunu `0.0` olarak maskeler (arayüz `inf` göstermesin diye).

## Akış

Plus moduyla **yapısal olarak aynı**; tek fark:
`ocr_processor.process_log_region(..., mode="stat")` ve `result_type == "stat"` dalı.

| Sonuç | Davranış |
|---|---|
| `"stat"` | `_extract_stat_value` → `current/best/worst` güncelle, eşiği geçtiyse `True` |
| `"failed"` | `_consecutive_failures += 1` |
| `success=False` | Hata logla, döngüde kal |

Durum mesajı best değerini de içerir:
`"Current: 89.35 (Best: 90.75)"`.

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Değer normalleştirme | `_extract_stat_value` |
| Eşik mantığı | `_perform_iteration` içindeki `>=` karşılaştırması |
| Yeni log formatı | `core/ocr.py` (desen) **ve** burada (anahtar eşlemesi) |
| Best/worst takibi | `_perform_iteration` |

## Dikatt

- **`start()` öncesi `configure()` zorunlu** (plus moduyla aynı neden).
- Stat modunda `log_roi` değişkeni `_run_loop` içinde atanır ama kullanılmaz
  (yalnızca `_perform_iteration` okur) — ölü atama, davranışsal etkisi yok.
- `_worst_stat` `inf` ile başlar; `get_worst_stat()` bunu maskeler.
- Eşik karşılaştırması aralık varsa **yeni üst sınıra** göredir (`new_range[1]`),
  ortalamaya göre değil.
- Sonuç ancak `BotBase._confirm_result` onaylarsa gelir: önceki sonuca zincirlenme
  (yeni logun `old_range`'i = öncekinin `new_range`'i) ya da birden çok OCR geçişinin
  uyuşması gerekir.