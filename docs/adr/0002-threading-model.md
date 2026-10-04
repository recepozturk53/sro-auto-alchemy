# ADR-0002: Tek Bot Thread'i + Callback Tabanlı UI

**Durum:** Kabul (bilinen teknik borç: Tk güncellemeleri henüz marshal edilmiyor)

## Bağlam

Tkinter yalnızca main thread'de güvenlidir. Bot döngüsü ise tıklama + animasyon
bekleme + OCR nedeniyle **bloklayıcıdır**; main loop'ta çalışsa arayüz donardı.

## Karar

1. **Tk main thread** yalnızca widget sahibidir (`MainWindow.run()` → `mainloop()`).
2. **Tek bot thread** `BotBase.start()` içinde `daemon=True` ile başlatılır.
3. Bot, durumu callback üzerinden dışarı bildirir; GUI'ye hiçbir referans tutmaz:
   ```python
   bot.set_callbacks(on_status_change=self._on_status_change, on_log=self._on_log)
   ```
4. **İşbirliğisel (cooperative) pause/stop**: bot `Event` nesnelerini kendisi kontrol eder
   (`_check_pause_stop`), dışarıdan zorla kesilmez. `stop()` thread'i `join(timeout=2.0)` ile bekler.
5. Durum ve ayarlar `Event`/`RLock` ile korunur (`BotStatus` için `_state_lock`).

## Sonuçlar

**Artılar**
- Arayüz her zaman yanıt kalır (OCR beklerken bile).
- Durum akışı tek noktadan (`BotState`/`StopReason`) izlenebilir.
- Yeni mod, mevcut GUI'ye otomatik bağlanır (aynı callback sözleşmesi).

**Eksiler / borç**
- **Tk thread-güvenliği:** (2026-10-04 çözüldü) bot callback'leri `queue.Queue`'ya
  yazar, ana thread 50 ms'de bir boşaltır (`MainWindow._post_ui` /
  `_drain_ui_queue`) — bkz. `docs/gotchas.md` #2.
  Pratikte çoğu zaman çalışır, ancak nadir ani çökme riski taşır.
- `stop()` uzun `animation_delay` sırasında zaman aşımına uğrayabilir
  (`join(timeout=2.0)`); bot ancak iterasyon sonunda durur.
- Callback'ler senkron çağrıldığı için `_state_lock` kilitliyken UI güncellemesi yapılır.

## Alternatifler

- **Her bot için ayrı thread:** Birden fazla bot aynı anda basarsa fare çakışması
  ve yanlış tıklama riski; modlar zaten birbirini dışlıyor.
- **Queue + Tk `after` polling:** En doğru desen (marshal sorununu kökten çözerdi),
  ancak mevcut yapıda ek değer sağlamadığı için ertelendi.
- **`multiprocessing`:** Win32 fare tıklaması ve `mss` process sınırında
  çalışmadığı için uygun değil.