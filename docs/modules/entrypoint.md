# Modül: `main.py`

**Katman:** L0 Giriş · **Sorumluluk:** uygulamayı başlatmak

## Ne yapar

Projenin tek çalıştırma giriş noktası. Beş adım:

1. `sys.path.insert(0, str(Path(__file__).parent))` → `src` paketinin çözülebilmesi için.
1. Yönetici değilse `relaunch_elevated()` → `ShellExecuteW("runas")` ile kendini UAC
   üzerinden yeni pencerede yeniden başlatır ve çıkar (SRO_Client yükseltilmiş çalışır;
   bkz. [gotchas §13](../gotchas.md)). UAC reddedilirse ya da `--no-elevate` verilirse
   uyarı basıp normal yetkiyle devam eder. PyInstaller derlemesinde (`sys.frozen`) exe'nin kendisi yeniden başlatılır.
2. `setup_logging()` → `logs/bot.log` + konsol çıktısı (`INFO`, `%(asctime)s - %(name)s - %(levelname)s - %(message)s`).
3. `check_dependencies()` → `customtkinter`, `mss`, `pytesseract`, `cv2`, `PIL`; sonra `pytesseract.get_tesseract_version()` ile Tesseract kontrolü.
4. `MainWindow()` örneği + `app.run()` → Tk `mainloop()`.

## Kritik davranış

- **Eksik bağımlılıkta `sys.exit(1)`**: kontrol başarısızsa uygulama açılmaz.
- **Eksik Tesseract yalnızca uyarı**: uygulama açılır, OCR çalışmaz.
- `main()` tüm hataları yakalar, `logging.error(..., exc_info=True)` ile loglar ve `sys.exit(1)` yapar.
- `logs/` klasörü çalışma anında `mkdir(exist_ok=True)` ile oluşturulur.

## Nereye dokunulur

| Amaç | Yer |
|---|---|
| Yeni başlangıç kontrolü | `check_dependencies()` — `try/except ImportError` bloğu ekle |
| Log formatı / seviyesi | `setup_logging()` |
| Uygulama açılış akışı | `main()` |

## Dikkat

- `main.py` **yalnızca `src.gui.main_window`'ı** import eder. Core modülleri doğrudan
  import edilmez; bu katmanın bağımlılığı tek yönlüdür (L0 → L1).
- `sys.path` manipülasyonu gereklidir: `src/` bir paket olduğu için kök dizin
  `sys.path`'te bulunmalıdır. Kaldırırsan `from src.gui...` çalışmaz.
- PyInstaller `SPECPATH`'i proje kökü kabul eder; `main.py` yolunun spec'te
  (`['main.py']`) doğru yazıldığından emin ol.