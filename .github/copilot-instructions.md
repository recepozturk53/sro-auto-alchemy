# SRO Auto-Alchemy Bot — Copilot Instructions

Kuralların ve mimari haritasının tek kaynağı: **`AGENTS.md`** (kök dizin).
Değişiklik yapmadan önce oku.

Hızlı yönlendirme:
- Katmanlar: L0 `main.py` → L1 `src/gui/` → L2 `src/core/bot_*` → L3 `ocr.py`/`screen_capture.py` → L4 `config.py`
- Bağımlılık tek yönlüdür: `core` asla `gui` import etmez.
- Win32 birimleri (`_click_at`, `_bring_window_to_front`, `_find_game_window`, `_play_alarm`) `src/core/bot_base.py` içindedir; tıklama **SendInput** ile yapılır ve **yönetici yetkisi şarttır** (ADR-0007), pencere `Macro_Client.exe` süreci + `MaxiGuard` sınıfıyla bulunur ve oyuna mesaj göndermeden `ctypes` ile aktive edilir (ADR-0008).
- Tesseract `ocr.py` içindeki `locate_tesseract()` ile PATH + yaygın kurulum dizinleri + `TESSERACT_CMD` üzerinden bulunur.
- Servisler singleton'dır: `config_manager`, `ocr_processor`, `screen_capture`.
- `start()` öncesi `configure()` zorunludur (bot sınıflarında zamanlama alanları orada atanır).
- Yeni regex eklerken mevcut parser öncelik sırasını koru.
- Yeni ayar `BotConfig` alanı olmalı; `config_manager.update()` bilinmeyen anahtarı sessizce düşürür.
- Yeni 3. parti bağımlılık `requirements.txt` **ve** `sro_alchemy_bot.spec` hiddenimports'ına eklenir.

Araçlar:
- `python tools/ctx.py <konu>` → hangi dosyaları oku/edit et
- `python tools/verify_docs.py` → bilgi haritası kodla uyumlu mu
- `python -m compileall -q src main.py` → sözdizimi kontrolü