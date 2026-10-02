# ADR-0005: Win32 Birimleri `bot_base.py` İçinde

**Durum:** Kabul — **teknik borç olarak işaretlendi**

## Bağlam

Plan dokümanı ayrı bir `core/input_controller.py` modülü öngörüyordu; oyun
penceresi bulma, tıklama ve alarm üretme sorumluluklarını oraya koyacaktı.

Gerçekleşen kodda bu yetenekler `BotBase` içinde üç yardımcı metot olarak
bulunur: `_click_at`, `_bring_window_to_front`, `_play_alarm`.

## Karar

Plan dokümanındaki ayrı modül **yapılmadı**; Win32 birimleri `BotBase`'e
yerleştirildi. Gerekçe: bu üç işlem de bot davranışının parçasıdır ve yalnızca
bot sınıfları tarafından kullanılır; ayrı bir modül tek bir çağıranı olan
yalın bir sarmalayıcı olurdu.

`docs/architecture.md` ve `AGENTS.md` bu yapıyı belgeliyor;
`list_windows.py` ise pencere tespitinin ayrı bir tanı aracı olarak kaldı.

## Sonuçlar

**Artılar**
- Win32 detayları tek yerde; yeni bot modu bunları doğrudan kullanır.
- `_bring_window_to_front` ve `_click_at` bot sınıflarının doğal bir parçası
  olarak okunur; soyutlama katmanı gereksizleşir.

**Eksiler / borç**
- **Katman ihlali izlenimi:** `bot_base.py` hem orkestrasyon hem Win32 bağlayıcısı
  sorumluluğu taşır (SRP riski).
- Win32 mantığını test etmek `BotBase` örneği gerektirir; saf fonksiyon değil.
- Oyuncu pencere adı değişirse (`SRO_Client` başlığı) burası güncellenmeli.
- `_bring_window_to_front` parametresi (`window_title`) fiilen kullanılmaz;
  eşleştirme sabit alt dize kontrolüdür → `docs/gotchas.md` #7.

## Gelecek için

Davranış doğrulanmadan ayrılmamalıdır: en az **bağımsız test edilebilir** bir
`win32` modülüne taşınmalı (`click_at(x, y)`, `find_window(pattern)`, `focus(hwnd)`),
`BotBase` ise onu çağırmalıdır. Taşıma, `list_windows.py` mantığının ve Alt
tuşu foreground hilesinin korunmasını gerektirir.