# Sistem denetimi — 17 Kasım 2026

Kod, iş akışları ve karar defteri baştan sona okundu; `record`/`settle` gerçekten çalıştırılıp denendi.
Canlı kaynaklara (FotMob, Flashscore, ESPN) geliştirme ortamından erişilemedi, o yüzden veri-şeması riskleri tahmindir.

## Düzeltildi (bu PR)
| # | Sorun | Kanıt | Düzeltme |
|---|---|---|---|
| 1 | `record` her şeyi kabul ediyordu: `TOTAL HOME`, `1X2 OVER_2.5`, `FOO BAR`, boş selection'lı PLAY, 0.9 fiyatlı PLAY | 7 sahte kayıt denendi, 7'si kaydedildi | Market/selection doğrulaması, PLAY/WATCH için selection zorunlu, fiyat > 1.0 |
| 2 | Bozuk bir kayıt `settle`'ı çökertiyordu (`unsupported market`) → o günden sonraki TÜM kararlar kapanmıyordu; `1X2 OVER_2.5` ise sessizce hep "LOSE" sayılıyordu | probe: `TOTAL HOME` ve `FOO BAR` çöktü | Çökmez, `UNGRADABLE` işaretler, kâr/CLV'ye girmez |
| 3 | İş akışında kapatma adımı çökerse bugünün taraması da atlanıyordu (adımlar sırayla, başarısızlıkta durur) | `daily-scan.yml` | Tarama `!cancelled()` ile her durumda çalışır; iş yine kırmızı biter, arıza bildirimi gider |
| 4 | Kapatma günde bir kez deneniyordu; maç o sırada bitmemişse ya da kaynak hata verdiyse karar sonsuza dek açık kalırdı | kod | `settle-pending`: son 7 günün açık kararlarını tekrar dener |
| 5 | Aynı saniyede aynı maç/seçim iki kez kaydedilirse aynı `decision_id` çıkıyor, ikincisi hiç kapanmıyordu | probe | Yinelenen id reddedilir |
| 6 | "0 maç" günü ile "kaynak bozuk" günü ayırt edilemiyordu (sağlık uyarısı n≥2 ister). 11–16 Kasım hep 0 maç | `health.json` | Kaynak listesinin ham maç sayısı kaydedilir; 20'den azsa uyarı |

## Düzeltilmedi — karar senin (önemli olandan başlayarak)
1. **Durdurma kuralının ölçütü yanlış kalibre.** CLV = alınan oran × kapanıştaki **marjsız** olasılık − 1. Kâr marjı içeren bir bahisçiden alınan oranla marjsız olasılık kıyaslanınca, hiç beceri yokken bile CLV marj kadar negatif çıkar. 8 maçlık gerçek pakette (`daily/2026-11-08`, maç sonrası fiyatlar) 20 bahisçinin **en iyi** oranının marjsız piyasaya göre ortalama değeri **−%4,0**; 24 seçimin yalnızca 1'i pozitif. Yani 50 PLAY sonunda kural, becerin ne olursa olsun büyük olasılıkla "dur" der. Doğru ölçüt: aynı bahisçinin kapanış oranına karşı ya da kapanıştaki en iyi oran. Sayaç şu an 0 olduğundan ölçütü değiştirmek ücretsiz; sonradan değiştirmek kuralı bozmak olur. Önerim: şimdi değiştir.
2. **Oran bölgesi GB, sen ABD'desin.** Kayıtlı fiyatlar senin oynayamayacağın bahisçilerin fiyatı. Defter kâğıt üstünde bile gerçeği ölçmüyor. (Zaten `DURUM.md` bekleyen işlerde.)
3. **50 PLAY bağımsız 50 maç değil.** Aynı maça PRE ve POST-XI iki PLAY, ya da 1X2 + Üst/Alt PLAY'i ayrı sayılıyor; birbirine bağlı bahisler örneklemi şişirir. Sayım "maç başına bir" olmalı.
4. **En iyi oran aykırı değer kontrolsüz.** Bir bahisçinin bayat/hatalı fiyatı "en iyi oran" olarak öne çıkabilir; fiyat zaman damgası yok. Yorumcu bunu kovalayabilir.
5. **Tedarik zinciri.** Flashscore kazıyıcısı sabit SHA'da ama bağımlılıkları (`requirements.txt`) sabit değil ve iş, repoya yazma yetkili token + Slack/ntfy gizli anahtarlarıyla birlikte çalışıyor (`env` iş akışı düzeyinde, `checkout` kimlik bilgisini saklıyor). Bağımlılıklardan biri ele geçirilirse repoya kötü commit atabilir. Çözüm: gizli anahtarları yalnızca kullanan adıma ver, `persist-credentials: false`. Test edemediğim için dokunmadım.
6. **Kaynaklar resmi API değil** (Flashscore, FotMob). Şema değişirse sistem "VERİ YOK" der, bozulmaz ama kör kalır. Ayrıca kullanım şartı riski.
7. **Zamanlama.** GitHub cron'u 5–15 dk (bazen çok daha fazla) gecikebilir; kadro penceresi 10–75 dk. Kadro geç yayınlanan ligde (özellikle Süper Lig) kaçırma olasılığı var; `MISSED` durumu bunu kaydediyor ama yorum görevi yine de boş çalışır.
8. **Kendi eklediğim `player_impact.py`:** FotMob `teams`/`playerStats` şemasını hafızadan yazdım, canlı denenmedi; bir maçta takım başına ~11 istek atıyor, araya bekleme koymadım (hız sınırına takılabilir). Veri yoksa "VERİ YOK" der, akışı bozmaz.
9. **Esas risk:** Sistem bir üstünlük kaynağı göstermedi. Kendi geriye dönük testin (17.463 maç) aynı model ailesinin kapanışı yenemediğini söylüyor. Elde somut olan tek şey kadro/eksik gibi geç bilgi; o da henüz hiç denenmedi (ilk sınav 21–22 Kasım).
