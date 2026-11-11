# Futbol kanıt hattı

Maç öncesi veriyi toplar, temizler ve yapay zekânın yorumlayacağı kısa bir kanıt paketi üretir.
**Kod karar vermez.** PLAY / WATCH / PASS kararını paketleri okuyan yapay zekâ yorumcu verir
(şu an Claude; yorumlar Slack `#futbol-yorum` kanalına gider). Kurallar: `CHATGPT_DECISION_POLICY.md`.

## Tek kayıt

Futbol kararlarının tek kaydı bu repodur (`decisions/`). Önceki sistemler arşivdir ve yeni kararlar için
kullanılmaz: "Futbol Sistemi V1.2/V1.3" belgesi ve Excel kayıt defteri, S1, `Final-football-prematch`.
İki sistemi paralel yürütmek, hangi kararın hangi kurala göre verildiğini ve CLV sayacını bulandırır.

## Akış

| Ne zaman | Ne | Nerede |
|---|---|---|
| Her gün 05:37 UTC | Dünü kapat (skor, kapanış fiyatı, CLV), bugünü tara | `daily-scan.yml` → `daily_pipeline.py` |
| ~10 dakikada bir | Maça 75–10 dk kala resmi kadro | `xi-watch.yml` → `xi_watch.py` |
| Maça ~30 dk kala | Yorum + karar (repo dışında, zamanlanmış Claude görevi) | Slack |

Çıktılar:
- `daily/<tarih>/OZET.md` — günün okunabilir özeti; `packets/<id>.json` — maç başına paket
- `daily/<tarih>/xi/<id>.md` — resmi kadro, önceki maça göre değişiklik, eksikler, güncel piyasa
- `daily/<tarih>/health.json` — kaynak sağlığı (bir kaynak maçların yarısından azında veri verdiyse uyarı)
- `daily/<tarih>/closing.json` — skorlar ve kapanış fiyatları
- `decisions/decisions.jsonl`, `settlements.jsonl`, `REPORT.md`, `STATUS.json` — karar defteri ve performans

## Kaynaklar (hepsi anahtarsız)

| Veri | Kaynak | Not |
|---|---|---|
| Fikstür, oranlar (~20 bahisçi, açılış + güncel), xG, sezon sonuçları | Flashscore (sabit sürüm kazıyıcı) | Kadro ve sakatlık beslemeleri boş döner |
| Resmi kadro | ESPN, ikinci kaynak FotMob | 11+11 değilse resmi sayılmaz |
| Sakatlık / ceza | FotMob | Tür ve tahmini dönüş |
| Hava durumu | Open-Meteo | Şehir düzeyinde |

Flashscore ve FotMob resmi API değildir; değişirlerse sistem veri uydurmaz, "VERİ YOK" yazar.
Test edilip çıkarılanlar: Transfermarkt (GitHub'dan 403), Pinnacle (kullanım şartları riski, lig eşleşmesi zayıf).

## İlkeler

- Eksik veri uydurulmaz; her eksik pakette `data_gaps` içinde listelenir.
- Piyasa: bahisçi başına marjsız (power) olasılık, bahisçiler arası medyan, açılıştan hareket, en iyi güncel fiyat.
- **Modeller kabadır** (xG ortalaması, sezon içi Elo). Bu model ailesi geriye dönük testte kapanış oranını
  yenemedi; paket model için EV ya da "aday" sıralaması üretmez, yalnızca piyasadan farkını gösterir.
- Kararlar yalnızca maç başlamadan kaydedilir. Başarı ölçütü CLV'dir.
- **Durdurma kuralı:** `STOP_RULE.md`.

## Komutlar

```bash
python daily_pipeline.py scan   --date 2026-11-22
python daily_pipeline.py settle --date 2026-11-21
python daily_pipeline.py record --match-id <id> --decision PLAY --market 1X2 --selection HOME --price 2.10 --bookmaker bet365
python daily_pipeline.py report
python xi_watch.py
pytest -q
```

Ligler: `config/leagues.json`.
