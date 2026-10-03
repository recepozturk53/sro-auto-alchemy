# ADR-0007: Tıklama için SendInput + yönetici yetkisi

**Durum:** Kabul
**Tarih:** 2026-10-02

## Bağlam

ADR-0006 tıklamayı `SetCursorPos` + `mouse_event` (pywin32) üzerine kurmuştu.
Gerçek kullanımda fuse butonuna **hiç tıklanmadı** ve log'a şu hata düştü:

```
Click error: (0, 'SetCursorPos', 'No error message is available')
```

İki bağımsız kök neden tespit edildi:

1. **Yönetici yetkisi (UIPI).** `SetCursorPos` `FALSE` dönüyor ve `GetLastError`
   `0` (ERROR_SUCCESS) olduğu için pywin32 "No error message is available"
   üretiyor. Windows, ön planda **yükseltilmiş (elevated)** bir pencere varken
   yükseltilmemiş süreçlerin fare/klavye kontrol etmesine izin vermez.
   SRO_Client tipik olarak yönetici olarak çalıştırılır; bot ise yönetici
   değildi (`IsUserAnAdmin()` → `False`).
   Kaynak: "Why is Windows's SetCursorPos ineffective when certain programs are
   in foreground?" — yanıt: *admin privileges*.

2. **Yanlış API katmanı.** `mouse_event`/`SetCursorPos` olayları üst düzey mesaj
   kuyruğuna enjekte eder. SRO DirectInput/Raw Input okur; bu olaylar Raw Input
   kuyruğuna hiç ulaşmaz, oyun onları görmez. `SendInput` aynı Raw Input
   kuyruğuna yazar ve oyun için gerçek donanım girdisinden ayırt edilemez.

Ayrıca eski akış, `SetCursorPos` başarısız olsa bile `mouse_event(LEFTDOWN)`
gönderiyordu; imleç hedefte olmadığı için **rastgele bir yere tıklıyordu**.

## Karar

`BotBase._click_at` sırayla iki strateji dener ve **imleç konumunu doğrulamadan
asla tuşa basmaz**:

1. **SendInput** — `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK`
   ile imleç konumlanır, `GetCursorPos` ile hedefte olduğu doğrulanır, sonra
   `LEFTDOWN`/`LEFTUP` gönderilir. Koordinatlar tam sanal masaüstüne göre
   0..65535 aralığına normalize edilir (çok monitör desteği).
2. **Yedek: `SetCursorPos` + `mouse_event`** — aynı doğrulama ile.

İmleç hiçbir yolla hedefe gitmiyorsa **tıklama yapılmaz** ve kullanıcıya
"yönetici olarak yeniden başlat" mesajı gösterilir.

Ek olarak `BotBase.start()` yönetici yetkisini denetleyip uyarı loglar; `main.py`
de konsola aynı notu basar.

`INPUT` struct'ı `MOUSEINPUT`/`KEYBDINPUT`/`HARDWAREINPUT` union'ı ile tam
boyutta (x64'te 40 bayt) tanımlanır; yalnızca `MOUSEINPUT` içeren bir struct
`SendInput` tarafından reddedilir.

## Sonuçlar

**Artılar**

- Tıklama, Raw Input okuyan oyunlarda (SRO/DirectInput) gerçekten kaydedilir.
- Yönetici değilken bile **yanlış yere tıklama olmaz** (güvenlik kazancı).
- Çok monitörlü kurulumlar desteklenir.
- Hata mesajı kök nedeni ve çözümü söyler (`[SendInput]` / `[SetCursorPos...]`).

**Eksiler / borç**

- **Uygulamanın yönetici olarak çalıştırılması gerekir.** Bu, kod ile
  çözülemez (UIPI kısıtı); kullanıcı eylemi şarttır.
- İki tıklama yolu bakım yükü; ikisi de test edilmelidir.
- Bazı anti-cheat'ler SendInput imzasını tespit eder (bu proje tek oyunculu
  alchemy botu bağlamında kabul edilmiştir).

## Alternatifler

- **Yalnızca `PostMessage`/`SendMessage`:** SRO'nun buton mesajlarını dinlediği
  kanıtlanmadı.
- **`mouse_event` ile devam etmek:** Raw Input oyunlarına ulaşmadığı için
  reddedildi.
- **`SetPhysicalCursorPos` / `ClipCursor`:** Aynı UIPI kısıtına takılır.