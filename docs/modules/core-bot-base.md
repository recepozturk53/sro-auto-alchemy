# Modül: `core/bot_base.py`

**Katman:** L2 Orkestrasyon · **Taban sınıf:** `BotBase(ABC)` · **Bağımlılık:** yok

## Ne yapar

Tüm bot modlarının ortak tabanıdır. Şunları sağlar:

1. **Thread yönetimi** — `start()` daemon thread başlatır, `stop()`/`pause()` yönetir.
2. **Durum makinesi** — `BotState`, `StopReason`, `BotStatus`.
3. **Win32 birimleri** — tıklama, pencere öne getirme, alarm. (Ayrı modül yok.)
4. **Ortak döngü iskeleti** — `_run_loop` + `_perform_iteration` şablonu.

> Alt sınıflar **yalnızca** `_run_loop()` ve `_perform_iteration()` uygulamak zorundadır.

## Tip referansı

| Sembol | Konum | Açıklama |
|---|---|---|
| `BotState` | :15 | `IDLE`, `RUNNING`, `PAUSED`, `STOPPED`, `COMPLETED`, `FAILED` |
| `StopReason` | :25 | `TARGET_REACHED`, `CRITICAL_FAILURE`, `USER_STOPPED`, `ERROR` |
| `BotStatus` | :34 | `state`, `message`, `current_value`, `target_value`, `iterations`, `failures`, `stop_reason` |
| `BotBase` | :45 | ABC |

## Win32 yardımcıları

| Metot | Davranış |
|---|---|
| `_click_at(x, y, delay_ms=50)` | Önce **SendInput** (`MOVE\|ABSOLUTE\|VIRTUALDESK` → `LEFTDOWN`/`LEFTUP`), olmazsa `SetCursorPos` + `mouse_event`. İmleç doğrulanmadan tuşa basılmaz. Başarıda `True` döner |
| `_abort_blocked_click()` | Tıklama iletilemezse çağrılır: durum `FAILED`/`StopReason.ERROR`, failure alarmı, `_stop_event.set()`. Plus/Stat iterasyonu bu durumda OCR'a geçmez |
| `_to_virtual_desktop(x, y)` | Ekran pikselini sanal masaüstüne göre 0..65535 absolüt aralığa normalleştirir (çok monitör) |
| `_is_elevated()` | `IsUserAnAdmin()`; `start()` yönetici değilse uyarı loglar |
| `_cursor_near(x, y, tol=3)` | `GetCursorPos` ile imlecin hedefte olduğunu doğrular |
| `_find_game_window(title)` | `EnumWindows` → görünür, süreci `Macro_Client.exe` olan (okunamazsa sınıfı `MaxiGuard` olan) pencere; `MaxiGuard` sınıfı ve başlık eşleşmesi önceliklidir |
| `_bring_window_to_front(title="SRO_Client")` | Zaten öndeyse hemen `True`. Pencere donmuşsa (`IsHungAppWindow`) uyarı + `False`. Yoksa `ShowWindowAsync(SW_RESTORE)` (simge durumundaysa) + `SetForegroundWindow` (+ Alt-tuşu hilesi), ≈0.3 sn bekleyip doğrular |
| `_play_alarm(kind)` | `success`: 523→659→784→1047 Hz yükselen; `failure`: 400→300→200 Hz düşen; `warning`: 1000 Hz |

> Tıklama için [ADR-0007](../adr/0007-sendinput-and-elevation.md) (SendInput +
> **yönetici yetkisi**), pencere aktivasyonu için
> [ADR-0008](../adr/0008-game-window-by-process.md).

## Döngü şablonu (yeni mod eklerken kopyala)

```python
def _run_loop(self) -> None:
    if not config_manager.is_configured():
        self._update_status(state=BotState.FAILED,
                           message="Bot not configured!", stop_reason=StopReason.ERROR)
        return
    self._update_status(current_value=0.0, iterations=0, failures=0)

    while not self._check_pause_stop():          # ← zorunlu ilk kontrol
        try:
            if self._perform_iteration():       # True → hedef bulundu
                self._update_status(state=BotState.COMPLETED,
                                   stop_reason=StopReason.TARGET_REACHED)
                self._play_alarm("success")
                return
            if self._consecutive_failures >= self._max_failures:
                self._update_status(state=BotState.FAILED,
                                   stop_reason=StopReason.CRITICAL_FAILURE)
                self._play_alarm("failure")
                return
            time.sleep(self._click_delay / 1000.0)
        except Exception as e:
            self._log(f"Iteration error: {e}")
            self._consecutive_failures += 1
            self._update_status(failures=self._consecutive_failures)

    self._update_status(stop_reason=StopReason.USER_STOPPED)
```

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Yeni Win32 işlemi | Bu modüle `_yardımcı` metot olarak ekle (bot sınıflarına değil) |
| Yeni durum | `BotState` veya `StopReason` enum'una ekle **ve** GUI'deki `_on_status_change` eşlemesini güncelle |
| Yeni ortak döngü adımı | `_run_loop` alt sınıflarda; ortaklaştırılacaksa buraya |
| Bekleme/kilit mantığı | `_check_pause_stop`, `start`, `stop`, `pause` |
| Alarm tonları | `_play_alarm` |

## Dikkat

- `configure()` bu sınıfta **yoktur**; her alt sınıf kendi imzasını tanımlar.
- `_update_status` kilidi tutarken callback'i **senkron** çağırır → callback bot
  thread'inde çalışır. GUI tarafında `root.after(0, ...)` kullanılmalıdır.
- `stop()` thread'i `timeout=2.0` ile join eder. `_fuse_and_wait` beklemeleri
  `_stop_event.wait()` kullanır, stop hemen işler.
- `_fuse_and_wait(mode)`: pencereyi öne getir → log baseline'ı → **tek** tıklama →
  en az `_animation_delay` bekle → log ROI'yi `RESULT_POLL_INTERVAL_S` (0.25 sn)
  aralıkla yokla; yeni sonucu `_detect_new_result` bulur: `_new_line_strip` yeni satırları piksel karşılaştırmasıyla ayırır (aynı değer üst üste gelse de), yalnızca o şerit OCR'lanır; stat modunda `stat_events` + `_pick_event`, plus modunda `parse_plus_result`.
  Buton animasyon boyunca "Cancel" olduğundan sonuç gelmeden asla tekrar
  tıklanmaz. `RESULT_TIMEOUT_MS` (20 sn) dolarsa `success=False` döner; durdurma
  veya engellenen tıklamada `None`.
- `pause()` bir **toggle**'dır; her çağrı durumu ters çevirir.
- Oyun penceresi **süreç adı + sınıf** ile bulunur (`Macro_Client.exe` /
  `MaxiGuard`), başlıkla değil — başlık girişten sonra değişir (ADR-0008).
  Tanılamak için: `python list_windows.py`.
- Pencere yardımcıları oyuna **asla mesaj göndermez** (`InternalGetWindowText`,
  `ShowWindowAsync`). Yönetici olarak çalışırken `GetWindowTextLength` /
  `ShowWindow` donmuş bir pencerede thread'i sonsuza kadar kilitler.
- `stop()` thread 2 sn'de bitmezse takıldığı yığını loglar.
- **Tıklama yönetici yetkisi ister:** ön planda yükseltilmiş pencere varken
  Windows yükseltilmemiş sürecin imleç kontrolünü engeller (ADR-0007).
  `_is_elevated()` bunu denetler, `start()` uyarı loglar.
- `_click_at` imleci doğrulamadan tuşa basmaz (`_cursor_near`); doğrulanamazsa
  `Click FAILED at (x, y)` ve mevcut imleç konumu loglanır, **hiçbir yere tıklanmaz**.
  Bu hata tek başına oyunun yönetici olarak çalıştığını kanıtlamaz; hedefin
  `GetClipCursor` alanı dışında kalması veya masaüstü erişimi de kontrol edilir.
- `_confirm_result` yeni piksel şeridindeki açık `alchemy ... fail` sonucunu
  değer zinciri/çoklu OCR oylaması olmadan kabul eder. Başarısız sonuçta yeni
  stat değeri yoktur; alternatif OCR geçişleri çoğu kez `None` döndürür.
  Arka arkaya aynı `failed` metni de yeni şerit olduğu için yeni sonuçtur.
  Başarısızlık `_previous_result` içindeki son başarılı değeri değiştirmez;
  sonraki stat sonucunun zinciri eski değere bağlanır.
- Stat şeridinde birden fazla olay varsa `_pick_event` metindeki **son** olayı
  seçer. İlk OCR eski bir stat satırını seçmiş olsa bile `_confirm_result`, stat
  zincirini kabul etmeden önce alternatif OCR okumalarında açık alchemy
  başarısızlığını arar. Başarısız fuse sonrasında tooltip bulunmayabilir.
- `pywin32` isteğe bağlıdır: yoksa saf `ctypes` yedeği devreye girer; uygulama
  çökmez.
