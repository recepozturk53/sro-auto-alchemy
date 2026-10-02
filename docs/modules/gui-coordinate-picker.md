# Modül: `gui/coordinate_picker.py`

**Katman:** L1 Arayüz · **Bağımlılık:** yok (sadece `tkinter` + `PIL`)

## Ne yapar

Kullanıcının ekran üzerinden **nokta** (fuse butonu) veya **dikdörtgen** (log ROI)
seçmesini sağlayan tam ekran saydam overlay.

## Sınıflar

| Sınıf | Sorumluluk |
|---|---|
| `CoordinatePicker` | Tek nokta seçimi (`pick_point`) |
| `RegionSelector` | Dikdörtgen seçimi (`select_region`) |
| `SelectionHelper` | GUI'ye sunulan ince sarmalayıcı |

`SelectionHelper` arayüz sözleşmesini belirler:

```python
pick_fuse_button(callback: Callable[[int, int], None])          # (x, y)
pick_log_roi(callback: Callable[[int, int, int, int], None])    # (x, y, w, h)
close_all()
```

## Overlay davranışı

- `Toplevel()`, `-fullscreen`, `-topmost`, `-alpha 0.3` (CoordinatePicker'da).
- `cursor='crosshair'`.
- ESC iptal eder.
- `focus_force()` ile odaklanır.

## Kritik kural: ekran-uzayı koordinatları

```python
x = event.x_root     # nokta seçimi
y = event.y_root
```

**`event.x` / `event.y` kullanma** — bunlar widget-relative'dır ve overlay tam ekran
olduğu için çoğunlukla aynı sonucu verir; ancak ROI sürüklemesinde
`_on_drag_release` **bilinçli olarak `event.x`/`event.y`** kullanır
(`_start_x` de canvas koordinatıdır). Bu kasıtlıdır: sürükleme başlangıcı da aynı
koordinat uzayında tutulur. Nokta seçiminde `x_root`/`y_root` kullanılır çünkü
tek tık doğrudan sonucu verir.

Karışıklık riski yüksek olduğundan: **yeni seçim türü eklerken hangi alanı
kullandığınızı buraya not edin.**

## Doğrulama

- `RegionSelector` minimum **10x10 px** şartı koyar; altındaysa `_cancel()` çağırır.
- Bölge normalleştirme: `x1=min(start,end)`, `x2=max(start,end)`.
- Seçim sonrası `after(500)` / `after(800)` ile görsel geri bildirim gösterilir,
  sonra `_complete_*` çağrılır.

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Yeni seçim aracı | Yeni sınıf + `SelectionHelper`'a metot |
| Overlay görünümü | `-alpha`, `bg`, `cursor` ayarları |
| Minimum boyut | `RegionSelector._on_drag_release` içindeki 10 px kontrolü |

## Dikkat

- **Bu modül `core` import etmez.** `SelectionHelper` yalnızca callback geçirir;
  kaydetme işini `main_window.py` yapar (`config_manager.set_*`). Bu ayrım bilinçlidir.
- Overlay açıkken uygulamanın ana penceresi arkada kalır; ESC ile kapatılmazsa
  kullanıcı uygulamaya dönemez.
- `close_all()` özel metotlara (`_close_existing`) erişir — `SelectionHelper` ve
  picker sınıfları arasındaki bu sızma mevcut tasarımdır, genişletirken dikkat et.
- Toplevel oluşturulduğunda `_close_existing()` önce çağrılır; eski overlay varsa
  birden fazla tam ekran pencere açılması engellenir.