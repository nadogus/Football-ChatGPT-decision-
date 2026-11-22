# Durum ve devir notu

Son güncelleme: 10 Kasım 2026. Yeni bir sohbette kaldığımız yerden devam etmek için önce bu dosyayı oku.

## Ne kuruldu
- **Bu repo** (herkese açık): veri toplar, karar vermez. Ayrıntı: `README.md`.
  - `daily-scan` her gün 05:37 UTC: dünü kapatır (skor, kapanış, CLV), bugünü tarar → `daily/<tarih>/`.
  - `xi-watch` ~10 dakikada bir: maça 75–10 dk kala resmi kadro → `daily/<tarih>/xi/`.
  - `live-watch` 5 dakikada bir (yalnızca maç sırasında): FotMob canlı xG/xGOT/ceza sahası → `daily/<tarih>/live/`,
    filtreye takılan maç Slack'e uyarı. Kararı Claude verir, kullanıcı `canlı bak <id>` yazınca. Ayrıntı: `CANLI_KARAR.md`.
- **Zamanlanmış Claude görevleri** (repo dışında, kullanıcının Claude hesabında):
  - "Futbol günlük yorum planlayıcı" — her gün 06:13 UTC; her başlama saati için maçtan 30 dk önce yorum görevi kurar.
  - "Futbol haftalık performans özeti" — pazartesi 09:43 UTC.
  - Yorumlar ve uyarılar Slack `#futbol-yorum` kanalına gider.
- **Kaynaklar:** Flashscore (oran, xG, fikstür), ESPN (kadro), FotMob (sakatlık/ceza, ikinci kadro kaynağı), Open-Meteo.
- **Durdurma kuralı:** `STOP_RULE.md` — 50 PLAY sonunda ortalama CLV < 0 ise sistem durur. Kararlar kâğıt üzerinde.
- **Arşiv:** Futbol Sistemi V1.2/V1.3 belgesi ve Excel defteri, S1, `Final-football-prematch` (XI zamanlaması kapatıldı).
- **Ayrı repo:** `nadogus/football-backtest` — Dixon-Coles/Elo ailesi 17.463 maçta kapanış oranını yenemedi
  (CLV ≈ −%6,7); haftalık zamanlaması hâlâ açık ama Pinnacle kapanışı Ocak 2026'dan beri gelmediği için yeni sonuç üretmez.

## İlk hafta sonu dersleri (22 Kasım 2026)
- Zamanlanmış görev, kendi içinden yeni zamanlanmış görev AÇAMIYOR (kullanıcı onayı istiyor). Bu yüzden 21–22 Kasım'da hiç yorum/karar çıkmadı.
  22 Kasım'da ilk 8 grubun yorum görevleri sohbetten elle kuruldu. Kalıcı çözüm önerisi (henüz kurulmadı, kullanıcı onayı bekliyor):
  tekrarlayan "Futbol yorum nöbetçisi" görevi (her saat :20 ve :50'de, 25–55 dk sonra başlayacak maçlar; Slack'te yorumu olan maçı atlar)
  ve planlayıcıyı 06:13'ten ~06:50 UTC'ye kaydırmak.
- Canlı uyarılar Slack'e hiç gitmedi ama "gönderildi" diye işaretlendi (webhook secret'ı yok gibi). Artık gönderilemeyen uyarı
  işaretlenmiyor, `daily/<tarih>/live/unsent_alerts.md` dosyasına yazılıyor. Kalıcı çözüm: repo Settings → Secrets → Actions'a
  `SLACK_LIVE_WEBHOOK_URL` (Slack Incoming Webhook, #futbol-yorum) eklemek.
- GitHub'ın 5 dk'lık zamanlaması 20–50 dk gecikti. live-watch artık tek çalıştırmada 5 dk arayla 5 tur (≈25 dk) izliyor.

## Henüz denenmedi (ilk gerçek sınav: 21–22 Kasım 2026 hafta sonu)
- Zamanlamaların kendiliğinden çalışması; XI izleyicinin canlı maçta kadroyu zamanında yakalaması.
- Yorum görevleri: Slack'e yazma, karar kalitesi, kararı repoya kaydedebilme (yazma izni belirsiz).
- Bir yorum oturumunun ne kadar kullanım harcadığı.

## Bekleyen işler (kullanıcı "beklesin" dedi)
1. Oran bölgesi: şu an GB (İngiltere bahisçileri). Kullanıcı ABD'de; oynayabildiği bahisçilere göre ayarlanacak
   (bahisçi listesi kullanıcıdan bekleniyor; `ODDS_GEO`).
2. İlk hafta sonundan sonra ayar: kadro penceresi, yorum saati (30 dk → gerekirse 20 dk), günlük grup sınırı (8).
3. Model satırı: ya düzgün ayarlanmış sürüm ya tamamen kaldırma.
4. 17 Kasım 2026: `player_impact.py` eklendi (kadro değişiminin ağırlığı: dakika yükü, xG/xA/şut/kilit pas, yerine girenle fark, kaleci tek satır). Gerçek FotMob verisiyle HENÜZ DENENMEDİ (geliştirme ortamından FotMob'a erişilemedi, testler sahte veriyle); ilk hafta sonunda `daily/<tarih>/xi/*.md` ve `gaps` içindeki `PLAYER_IMPACT_*` satırlarına bak. FotMob'un `teams` ve `matchDetails.content.playerStats` şeması farklıysa burası "VERİ YOK" der, akışı bozmaz.
   Hâlâ aday: maç takvimi/yorgunluk,
   son 3–4 kadroyla karşılaştırma, kadro sonrası oran hareketi.
5. Eski 14 dal silinemedi (oturum izni yok); kullanıcı GitHub'dan silebilir.
6. Kapanış ölçütü Pinnacle değil ~20 bahisçinin ortası; pozitif CLV temkinli yorumlanmalı.

## Denetim (17 Kasım 2026)
Ayrıntı `DENETIM.md`. Durdurma kuralının CLV ölçütü düzeltildi (aynı bahisçinin kapanışına karşı; ayrıntı `STOP_RULE.md` değişiklik kaydı). Hâlâ açık: GB oran bölgesi, maç başına bir PLAY sayımı, aykırı en iyi oran, tedarik zinciri.

## İlkeler (unutma)
- Yeni motor/katman/kaynak ekleme eğilimine diren; önce 50 kararı biriktir.
- Piyasanın zaten fiyatladığı veri (form, H2H, genel istatistik) gürültüdür; değer geç gelen bilgide olabilir.
- Eksik veri uydurulmaz. "VERİ YOK" ≠ "sorun yok".
- Kullanıcıyla Türkçe konuş.
