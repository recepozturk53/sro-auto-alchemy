# Modül: `core/bot_plus.py`

**Katman:** L2 Orkestrasyon · **Sınıf:** `PlusModeBot(BotBase)` · **Mod:** `plus`

## Ne yapar

Fuse butonuna tıklar, animasyonu bekler, log'dan **güncel + seviyesini** okur ve
`current_plus >= target_plus` olduğunda başarı alarmıyla durur.

## Durum alanları

| Alan | Değer |
|---|---|
| `_current_plus` | Son okunan + seviyesi |
| `_target_plus` | Hedef seviye (GUI'den) |
| `_consecutive_failures` | Ardışık başarısızlık sayacı |
| `_max_failures` | Varsayılan `10` (aşılırsa `FAILED`) |
| `_animation_delay` | `__init__`'te **yok**, `configure()` ile gelir |
| `_click_delay` | `__init__'`te **yok**, `configure()` ile gelir |

## Akış

`configure(target_plus, animation_delay=1500, click_delay=300, max_failures=10)`
→ `start()` → `_run_loop()`:

1. Konfigürasyon kontrolü: `is_configured()` değilse `FAILED` + `StopReason.ERROR`.
2. **3 saniyelik geri sayım** (kullanıcı oyun penceresine geçsin diye), ardından
   `_bring_window_to_front("SRO_Client")`.
3. `while not self._check_pause_stop():`
   - `_perform_iteration()` → hedef+seviye geldiyse `True`
   - `True` → `COMPLETED` + `StopReason.TARGET_REACHED` + `_play_alarm("success")` + `return`
   - `_consecutive_failures >= _max_failures` → `FAILED` + `CRITICAL_FAILURE` + `failure` alarmı + `return`
   - `sleep(click_delay / 1000)`
   - `except` → hata logla, `_consecutive_failures += 1`
4. Döngüden çıkışta `stop_reason=USER_STOPPED`.

`_perform_iteration()` ortak 7 adımı yapar (bkz. [architecture.md](../architecture.md));
sonunda `result.result_type` dalına göre karar verir:

| Sonuç | Davranış |
|---|---|
| `"plus"` | `_current_plus` güncelle, `_consecutive_failures = 0`, `+N >= target` ise `True` |
| `"failed"` | `_consecutive_failures += 1` (plus seviyesi sıfırlanmaz — OCR bir sonraki turda gerçek değeri okur) |
| `success=False` | Hata logla, döngüde kal |

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Varsayılan zamanlama | `configure()` parametre varsayılanları (GUI ayrıca geçirir) |
| Başarısızlık toleransı | `configure(max_failures=...)` veya `__init__`'teki `_max_failures` |
| Plus ayrıştırma davranışı | **Burada değil** → `core/ocr.py` |
| Döngü iskeleti | `BotBase` (ortak) |

## Dikkat

- **`start()` öncesi `configure()` zorunlu.** `_animation_delay`, `_click_delay`,
  `_max_failures` yalnızca `configure()` içinde atanır; atanmazsa
  `_perform_iteration` içinde `AttributeError` oluşur ve kullanıcı yalnızca
  "Iteration error" logu görür.
- Başlangıçtaki **3 saniyelik bekleme kasıtlıdır** (pencere geçişi). Test ederken kaldırma.
- `_max_failures` yalnızca `configure(max_failures=...)` ile değiştirilebilir;
  GUI bu parametreyi **geçmez**, her zaman `__init__`'teki `10` değerini kullanır.
- `self.status.iterations` her iterasyonda artırılır; GUI bunu "Iterations" etiketinde gösterir.
- Başarı tıklaması sonrası `_bring_window_to_front()` **iki kez** çağrılır: tıklamadan
  önce ve yakalamadan önce. Biri kaldırılırsa yakalama yanlış pencereyi alabilir.