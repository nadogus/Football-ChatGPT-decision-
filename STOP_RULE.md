# Durdurma kuralı

Bu kural, sonuçlar görülmeden önce yazılmıştır ve sonuçlara göre değiştirilmez.

**Kural:** Kapanış fiyatı kaydedilmiş **50 PLAY** kararı tamamlandığında ortalama **CLV negatifse** sistem durdurulur.

- CLV = alınan oran ÷ **aynı bahisçinin** kapanış oranı − 1 (`daily_pipeline.py settle`). Aynı bahisçi kapanış fiyatlarında yoksa o bahis CLV sayısına girmez.
- Ölçüt ROI değil CLV'dir: 50 bahiste ROI şanstan ayırt edilemez, CLV çok daha az gürültülüdür.
- Kural tetiklenince `daily_pipeline.py record` yeni PLAY kararını reddeder; `decisions/REPORT.md` ve
  `decisions/STATUS.json` durumu gösterir. PASS/WATCH kaydı ve veri toplama sürer.
- Bu aşamada kararlar kâğıt üzerindedir (gerçek para yok).
- Kuralı gevşetmek ("biraz daha bekleyelim") kuralın ihlalidir. Sistemi yeniden başlatmanın tek yolu,
  neyin değiştiğini yazıp sayacı sıfırdan başlatmaktır.

Dayanak: aynı model ailesinin (Dixon-Coles / Elo) 2019–2026 geriye dönük testi, 17.463 maçta kapanış
oranını yenemedi (`nadogus/football-backtest`). Başlangıç varsayımı "avantaj yok"tur; aksini veri gösterir.

## Değişiklik kaydı

**17 Kasım 2026 — ölçüt düzeltildi (sayaç 0 iken, hiçbir karar kapanmamıştı).**
Eski ölçüt: alınan oran × kapanıştaki *marjsız* olasılık − 1. Marj içeren bir bahisçinin oranı marjsız olasılıkla kıyaslandığı için beceri
olmasa bile CLV marj kadar (≈ −%4; 8 maçlık gerçek veride en iyi oranlar için ortalama −%4,0) negatif çıkıyordu: kural neredeyse kesin "dur" derdi.
Yeni ölçüt aynı bahisçinin kapanış oranına karşı ölçer. Eşik (50 PLAY, ortalama CLV < 0) ve kuralın geri kalanı aynıdır. Eski ölçüt bilgi olarak `clv_vs_fair`
alanında ve raporda durur ama kural onu kullanmaz. Bu, sonuç görülmeden önce yapılmış bir düzeltmedir, gevşetme değildir.
