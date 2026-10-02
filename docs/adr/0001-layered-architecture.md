# ADR-0001: Katmanlı Mimari

**Durum:** Kabul

## Bağlam

Proje, ekran görüntüsü alan (L3), bunu yorumlayan (L2) ve kullanıcıya kontrol
sunan (L1) birbirine karışan dosyalar halinde büyüyordu. Plan dokümanı
`core/` altında düz bir yapı öngörüyordu; bu, GUI mantığının servis katmanına
sızmasına yol açardı.

## Karar

Beş katman tanımlanır ve bağımlılık **tek yönlüdür: yukarı doğru**.

```
L0 main.py        → L1 gui → L2 bot → L3 servisler
                                    ↘ L4 config (herkes kullanabilir)
```

| Katman | Yapı | Kural |
|---|---|---|
| L0 | `main.py` | Yalnızca GUI'yi başlatır |
| L1 | `src/gui/` | Core'u import eder; Tk **main thread**'de |
| L2 | `src/core/bot_*` | Tkinter/customtkinter **import etmez** |
| L3 | `ocr.py`, `screen_capture.py` | GUI veya bot import etmez |
| L4 | `config.py` | Ağır kütüphane import etmez |

`core` asla `gui` import etmez. Bu kural `tools/verify_docs.py` tarafından
`module-index.json` bağımlılık kenarları üzerinden **otomatik denetlenir**.

## Sonuçlar

**Artılar**
- Bir servisin nerede kullanılabileceği tek kuralla belirlidir.
- OCR katmanı GUI olmadan test edilebilir (saf metin → `ParseResult`).
- Yeni mod eklemek `docs/patterns.md` Tarif 1'e dönüşür.

**Eksiler**
- Katmanlar arası veri geçişi için `config_manager` gibi global erişim gerekir.
- Bazı işler doğal olarak iki katmana ait (ör. Win32 tıklaması) → ADR-0005.

## Alternatifler

- **Düz yapı (plan dokümanı):** `core/` altında 4 düz dosya. Reddedildi çünkü
  GUI bağımlılıklarının nereye gideceği belirsizleşiyordu.
- **Event-bus tabanlı katmanlar:** Fazla altyapı; bu boyutta bir projede
  maliyeti karşılığını vermiyor.