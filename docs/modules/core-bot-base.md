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
| `_click_at(x, y, delay_ms=50)` | **pywin32** varsa `win32api.SetCursorPos` + `mouse_event(MOUSEEVENTF_LEFTDOWN/LEFTUP)`; yoksa `ctypes` `SetCursorPos` + `mouse_event` |
| `_window_title_candidates(title)` | Sıralı, tekilleştirilmiş başlık parçaları: `title` → `SRO_Client` → `Silkroad` |
| `_bring_window_to_front(title="SRO_Client")` | **pygetwindow** varsa `getWindowsWithTitle` + `restore()`/`activate()` (≈0.4 sn); yoksa `EnumWindows` + `ShowWindow(SW_RESTORE)` + `SetForegroundWindow` + `BringWindowToTop` + Alt-tuşu hilesi (≈0.5 sn) |
| `_play_alarm(kind)` | `success`: 523→659→784→1047 Hz yükselen; `failure`: 400→300→200 Hz düşen; `warning`: 1000 Hz |

> Girdi backend'i isteğe bağlı iki katmanlıdır (birincil: pywin32 + pygetwindow,
> yedek: saf `ctypes`) — bkz. [ADR-0006](../adr/0006-input-backend-pywin32-pygetwindow.md).

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
- `stop()` thread'i `timeout=2.0` ile join eder; `_perform_iteration` içindeki
  uzun beklemeler (animasyon) stop'u geciktirebilir — `_check_pause_stop` ancak
  iterasyon sonunda kontrol edilir.
- `pause()` bir **toggle**'dır; her çağrı durumu ters çevirir.
- `_bring_window_to_front` artık `window_title` parametresini gerçekten kullanır:
  `_window_title_candidates` sırayla `title` → `SRO_Client` → `Silkroad` arar
  (ADR-0006). Tanılamak için: `python list_windows.py`.
- Girdi backend'i isteğe bağlıdır: `pywin32`/`pygetwindow` yoksa `ctypes` yedek
  yolu devreye girer; uygulama çökmez ama tıklama güvenilirliği düşer.