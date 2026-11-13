# Canlı karar protokolü

Repo canlı veriyi toplar ve uyarı atar. **Kararı Claude verir.** Bahsi kullanıcı kendisi, telefondan oynar.

## Akış
1. `live-watch` 5 dakikada bir çalışır. Yalnızca lig listesindeki maçlar (başlamadan 2 dk önce, başladıktan 130 dk sonrasına kadar)
   ve elle eklenen FotMob id'leri izlenir (`LIVE_EXTRA_IDS` değişkeni ya da elle çalıştırma).
2. FotMob'dan anlık görüntü `daily/<tarih>/live/<fotmob_id>.jsonl` dosyasına eklenir.
3. Filtreye takılan maç Slack'e uyarı olarak gider: baskı (xG farkı ≥ 0,8 ve baskın taraf önde değil), açık maç,
   son 15 dakikada xG patlaması, kırmızı kart. Aynı uyarı aynı maç için bir kez gönderilir.
4. Kullanıcı Claude'a `canlı bak <fotmob_id>` (ya da takım adı) yazar.

## Claude ne yapar (`canlı bak`)
1. Repoyu çeker; `daily/<tarih>/live/index.json` ve ilgili `.jsonl` dosyasını okur. En son görüntü 10 dakikadan eskiyse bunu söyler.
2. Maç öncesi paket varsa (`daily/<tarih>/packets/`) okur: kadro, eksikler, maç öncesi piyasa.
3. Trendi okur: xG / xGOT / ceza sahası topla buluşma son 15 dakikada nasıl değişti, baskı sürüyor mu, sönüyor mu.
4. Canlı oranı kullanıcıdan ister (BetMGM'deki oran) ya da laptoptaki açık bahis sitesinden bakar. Oran görülmeden OYNA denmez.
5. Karar formatı:
   - **OYNA** ya da **PAS**
   - Pazar (örn. sıradaki gol, alt/üst 1,5, ev sahibi kazanır) ve **alınabilecek en düşük oran**
   - Birim (kâğıt üzerinde 1 birim; tam emin değilse 0,5)
   - 2–3 cümlelik gerekçe ve "bu olursa vazgeç" koşulu (örn. "gol gelirse ya da 75' geçerse oynama")
6. Kararı `ledger/live_decisions.jsonl` dosyasına yazar (zaman, fotmob_id, dakika, skor, karar, pazar, min. oran, gerekçe).

## İlkeler
- Eksik veri uydurulmaz. xG ya da xGOT yoksa bunu söyler ve büyük olasılıkla PAS der.
- Piyasa canlı istatistiği zaten hızla fiyatlar. Değer ancak oran hareketi istatistiğin gerisinde kalırsa vardır.
  Bu yüzden PAS varsayılan karardır.
- Canlı kararlar ayrı sayılır: 50 canlı karardan sonra sonuç negatifse canlı modül durur (`STOP_RULE.md` mantığı).
- İlk 50 karar kâğıt üzerindedir.

## Laptop modu (daha hızlı: ~1 dk, GitHub gecikmesi yok)
Tırdaki Windows laptopta `live_watch.py` sürekli çalışır. Kurulum bir kere (`kurulum_canli.bat` bunların 1-3'ünü kendisi yapar):
1. Python 3 ve Git kur (ikisi de ücretsiz). `git clone https://github.com/nadogus/Football-ChatGPT-decision-` ile repoyu indir.
   Push için Git'in GitHub'a giriş yapmış olması gerekir (ilk `git push`ta tarayıcı açılır).
2. Slack uyarısı için bir kere `setx SLACK_WEBHOOK_URL "<webhook>"` (komut istemi), sonra pencereyi kapatıp aç.
3. Repo klasöründeki `laptop_canli.bat` dosyasına çift tıkla. Pencere açık kalsın.
4. Başka ayar gerekmez: laptop veri gönderdiği sürece GitHub zamanlaması kendiliğinden atlar; laptop durursa
   15 dakika içinde GitHub yeniden devralır. (Elle tamamen kapatmak için: `LIVE_ACTIONS_OFF` = `true` değişkeni.)

Maç yokken döngü hiçbir şey çekmez; sadece bekler. Veri her ~3 dakikada bir repoya gider, `canlı bak` o veriyi okur.
