# ADR-0006: Girdi Backend'i pywin32 + pygetwindow

**Durum:** Superseded by ADR-0007 (tıklama yolu) — pencere aktivasyonu (pygetwindow) hâlâ geçerli
**Tarih:** 2026-10-02

## Bağlam

SRO_Client penceresi üzerinde `ctypes.windll.user32.SetCursorPos` +
`mouse_event` ile yapılan fare simülasyonu bazı kurulumlarda basma (fuse)
butonuna **hiç tıklamıyordu**. SRO gibi DirectInput kullanan oyunlarda pencere
öne gelmeden gönderilen sentetik girdiler yok sayılabilir; ayrıca saf `ctypes`
çağrıları `SetForegroundWindow` foreground kilidine takılıyordu.

Kullanıcı, çalışan başka bir otomasyon projesinde kanıtlanan bir reçete verdi:
tıklama için `win32api`/`win32con` (pywin32), pencere öne getirme için
`pygetwindow`.

## Karar

`BotBase` Win32 yardımcıları iki katmanlı hale getirildi:

1. **Birincil yol:** `pywin32` ile `win32api.SetCursorPos` +
   `win32api.mouse_event(MOUSEEVENTF_LEFTDOWN/LEFTUP, x, y, 0, 0)`; pencere için
   `pygetwindow` ile `restore()` + `activate()`.
2. **Yedek yol:** `pywin32`/`pygetwindow` kurulu değilse mevcut `ctypes`
   `SetCursorPos` + `mouse_event` ve `EnumWindows` + `SetForegroundWindow`
   zinciri (Alt-tuşu hilesiyle) çalışır.

Her iki kitaplık **isteğe bağlı** bağımlılıktır: import başarısız olursa
uygulama çökmez, otomatik olarak `ctypes` yoluna düşer.

`_bring_window_to_front(window_title)` artık parametresini gerçekten kullanır
(`_window_title_candidates` ile `window_title` → `SRO_Client` → `Silkroad`
sırayla denenir) — eski gotcha #7 çözüldü.

Bu karar ADR-0005'i **geçersiz kılmaz**: yardımcılar hâlâ `bot_base.py`
içindedir; yalnızca çağırdıkları API değişir.

## Sonuçlar

**Artılar**

- Fuse tıklaması SRO_Client üzerinde güvenilir çalışır.
- Pencere aktivasyonu `pygetwindow` sayesinde daha kararlı; başlık parametresi
  işlevsel hale geldi.
- Geriye dönük uyumluluk: yedek yol sayesinde eski davranış korunur.

**Eksiler / borç**

- İki yeni 3. parti bağımlılık (`pywin32`, `pygetwindow`) → `requirements.txt`
  **ve** `sro_alchemy_bot.spec` hiddenimports güncellenmelidir.
- İki kod yolu bakım yükü: ikisi de değişiklikte test edilmelidir.
- `pygetwindow.activate()` bazı makinelerde foreground kilidine takılabilir; bu
  durumda `ctypes` yedek yolu devreye girer.

## Alternatifler

- **Yalnızca `SendInput`:** SRO'da kanıtlanmadı; `mouse_event` kadar yaygın değil.
- **`PostMessage` ile doğrudan buton mesajı:** SRO'nun pencere yapısı
  çözümlenmeden güvenilir değil.
- **Ayrı `input_controller` modülü:** ADR-0005 gerekçeleriyle ertelendi.