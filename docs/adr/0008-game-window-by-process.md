# ADR-0008: Oyun penceresi süreç + sınıf ile, mesaj göndermeden

**Durum:** Kabul
**Tarih:** 2026-10-04

## Bağlam

ADR-0007 sonrası bot yönetici olarak çalıştırıldı ve "1 second..." logundan sonra
**hiçbir şey olmadı**: bot thread'i `_bring_window_to_front` içinde kilitlendi.

Kök nedenler:

1. **Mesaj gönderen API'ler.** `GetWindowTextLength` (`WM_GETTEXTLENGTH`) ve
   çapraz-thread `ShowWindow` / `BringWindowToTop` hedef pencereye **senkron
   mesaj** gönderir. Bot yükseltilmemişken UIPI bu mesajları anında reddediyordu;
   yönetici olunca mesaj gerçekten gider ve donmuş (hung) bir pencere cevap
   vermediği için thread sonsuza kadar bekler. pygetwindow bu API'leri kullanır.
2. **Başlıkla arama.** Desteklenen istemci yalnızca
   `E:\Games\Oasis 2005 MACRO\Macro_Client.exe`. Penceresinin başlığı giriş
   ekranında `SRO_Client`, girişten sonra `[<karakter>] Oasis 2005`. Ölü (hung,
   görünmez) eski bir `SRO_Client` penceresi ve başka SRO istemcileri de aynı
   anda açık olabiliyordu; başlık araması yanlış/donmuş pencereyi seçiyordu.
3. **Elle "Yönetici olarak çalıştır".** Oyun yükseltilmiş çalıştığı için araç da
   yükseltilmeli (ADR-0007); kullanıcı bunu her seferinde elle yapmak istemiyor.

## Karar

- `_find_game_window()` görünür üst düzey pencereleri `EnumWindows` ile gezer ve
  **süreç adı** `macro_client.exe` olanı seçer (`QueryFullProcessImageNameW`,
  `PROCESS_QUERY_LIMITED_INFORMATION`); süreç okunamazsa sınıf `MaxiGuard`
  yeterlidir. Diğer istemciler yok sayılır.
- Pencere yardımcıları oyuna **hiç mesaj göndermez**: başlık
  `InternalGetWindowText`, sınıf `GetClassNameW`, geri yükleme `ShowWindowAsync`.
  Pencere `IsHungAppWindow` ise beklemeden uyarı loglanır. Zaten öndeyse
  aktivasyon atlanır.
- pygetwindow kaldırıldı (`requirements.txt`, spec hiddenimports).
- `main.py` yönetici değilse kendini `ShellExecuteW("runas")` ile yeniden başlatır
  (`--no-elevate` ile kapatılır).
- `_click_at` `bool` döner; tıklama iletilemezse `_abort_blocked_click()` botu
  `FAILED` durumuyla durdurur (eski log boşuna OCR'lanmaz).
- `stop()` thread 2 sn'de bitmezse takıldığı yığını loglar.

## Sonuçlar

- Donmuş oyun penceresi botu kilitleyemez; durum logda görünür.
- Hedef istemci değişirse `GAME_PROCESS_NAME` / `GAME_WINDOW_CLASS` güncellenmeli.
- Her başlatmada bir UAC onayı gerekir.
