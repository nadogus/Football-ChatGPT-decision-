# Durdurma kuralı

Bu kural, sonuçlar görülmeden önce yazılmıştır ve sonuçlara göre değiştirilmez.

**Kural:** Kapanış fiyatı kaydedilmiş **50 PLAY** kararı tamamlandığında ortalama **CLV negatifse** sistem durdurulur.

- CLV = alınan oran × kapanıştaki marjsız piyasa olasılığı − 1 (`daily_pipeline.py settle`).
- Ölçüt ROI değil CLV'dir: 50 bahiste ROI şanstan ayırt edilemez, CLV çok daha az gürültülüdür.
- Kural tetiklenince `daily_pipeline.py record` yeni PLAY kararını reddeder; `decisions/REPORT.md` ve
  `decisions/STATUS.json` durumu gösterir. PASS/WATCH kaydı ve veri toplama sürer.
- Bu aşamada kararlar kâğıt üzerindedir (gerçek para yok).
- Kuralı gevşetmek ("biraz daha bekleyelim") kuralın ihlalidir. Sistemi yeniden başlatmanın tek yolu,
  neyin değiştiğini yazıp sayacı sıfırdan başlatmaktır.

Dayanak: aynı model ailesinin (Dixon-Coles / Elo) 2019–2026 geriye dönük testi, 17.463 maçta kapanış
oranını yenemedi (`nadogus/football-backtest`). Başlangıç varsayımı "avantaj yok"tur; aksini veri gösterir.
