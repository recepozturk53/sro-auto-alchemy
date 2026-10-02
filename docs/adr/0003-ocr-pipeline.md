# ADR-0003: OCR + Regex, Model Eğitimi Değil

**Durum:** Kabul

## Bağlam

Soru şuydu: "Log okumak için binlerce ekran görüntüsü toplayıp bir model
eğitmemiz gerekir mi?"

SRO log yazıları sabit piksel fontunda, yüksek kontrastlı ve bilinen formatta
(`+7`, `[12.2->12.4]`, `[(82.9%~98.6%) -> (81.6%~97.1%)]`) basılır. Hızlı
geliştirme ve düşük bağımlılık için bu yapı yeterlidir.

## Karar

Makine öğrenmesi **kullanılmaz**. Pipeline:

```
BGR → gri tonlama → GaussianBlur → Otsu threshold → MORPH_CLOSE
    → Tesseract (psm 6, oem 3, dar karakter whitelist'i)
    → katı regex ayrıştırma → ParseResult
```

Ayırıcının ikinci aşaması regex'tir; eşleşen kalıplar `docs/modules/core-ocr.md`
içinde **öncelik sırasıyla** listelenmiştir (sözleşmdir).

## Sonuçlar

**Artılar**
- Sıfır eğitim süresi, sıfır veri toplama, sıfır model bakımı.
- Yeni log formatı = yeni regex (dakikalar, eğitim değil).
- Sonuçlar yorumlanabilir: ham metin `ParseResult.raw_text` içinde loglanır,
  hata ayıklamak "hangi regex geçti/hangi geçmedi" demektir.
- CPU-only, düşük bellek; her iterasyonda saniyeler değil yüzlerce ms.

**Eksiler**
- Oyun fontu/renkleri değişirse ön işleme ayarları gerekebilir.
- OCR hatası kalıcıdır; "12.2" yerine "l2.2" gibi hatalar regex'e kadar sızar.
- Whisitelist dar olduğu için dil değişikliklerinde güncelleme gerekir.

## Alternatifler

- **Kendi modelini eğitmek:** Veri toplama maliyeti, eğitim altyapısı ve
  sürüm/dağıtım yükü; mevcut gereksinim için orantısız.
- **Template matching (piksel eşleme):** Sadece tam aynı metinlerde çalışır;
  sayı değerleri her seferinde değiştiği için uygun değil.
- **Tesseract yerine EasyOCR/PaddleOCR:** Daha yüksek doğruluk ama büyük
  bağımlılık ve daha yavaş; SRO formatlarında mevcut pipeline yeterli.