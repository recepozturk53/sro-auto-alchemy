# Mimari Karar Kayıtları (ADR)

Mimarinin **neden** bu şekilde olduğunu açıklar. Kod neyi yaptığını gösterir;
ADR neden o şekilde yaptığını korur.

| ADR | Karar | Durum |
|---|---|---|
| [0001-layered-architecture.md](0001-layered-architecture.md) | 5 katmanlı bağımlılık yönü | Kabul |
| [0002-threading-model.md](0002-threading-model.md) | Tek bot thread'i + callback tabanlı UI güncellemesi | Kabul |
| [0003-ocr-pipeline.md](0003-ocr-pipeline.md) | OCR + regex yerine ML modeli yok | Kabul |
| [0004-pervasive-singletons.md](0004-pervasive-singletons.md) | Servisler singleton | Kabul (teknik borç) |
| [0005-win32-primitives.md](0005-win32-primitives.md) | Tıklama/pencere/alarm `bot_base.py` içinde | Kabul (teknik borç) |
| [0006-input-backend-pywin32-pygetwindow.md](0006-input-backend-pywin32-pygetwindow.md) | Tıklama pywin32, pencere pygetwindow (ctypes yedekli) | Kabul |

## Şablon

```markdown
# ADR-XXXX: <karar>

**Durum:** Kabul / Reddedildi / Superseded by ADR-YYYY
**Tarih:** YYYY-MM-DD

## Bağlam
<kararın alındığı sorun>

## Karar
<neye karar verildi>

## Sonuçlar
Artılar, eksiler, kısıtlar

## Alternatifler
<reddedilen seçenekler ve nedenleri>
```

## İlke

Yeni bir mimari karar verirsen **bu klasöre dosya ekle** ve
`docs/module-index.json`/`AGENTS.md` gerekiyorsa güncelle.
Mevcut bir ADR'yi geçersiz kılacaksan **dosyayı silme** —
`Durum: Superseded by ADR-XXXX` yap ve yenisini yaz.