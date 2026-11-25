# Sakura'nın ONAYLI gelişimi (8 Kas 2026, Dino istedi: "onaylı gelişme mantıklı", haftada bir).
# Her Pazar 20:00'den sonra bir kez (PC o saatte kapalıysa sonraki açılışta, 8 gün geçtiyse): son 7 günün günlüklerinden
# kısa istatistik + konuşmalar toplanır, sonnet en çok 5 küçük ve güvenli geliştirme önerir. Her öneri Telegram'a
# "✅ Yap / ❌ Geç" düğmeleriyle gider. ✅ → is_ver.py ile ayrı bir Claude Code oturumu (yedekli, tek değişiklik, test,
# yeniden başlatmadan önce Telegram'dan haber); ❌ → bir daha önerilmez. Dino onaylamadan HİÇBİR ŞEY değişmez.
#   python gelisim.py --simdi    hemen öner ve Telegram'a gönder
#   python gelisim.py --deneme   önerileri yalnız ekrana yaz (göndermez)
import os, re, sys, json, glob, time, logging, datetime, subprocess, collections

KOK = os.path.dirname(os.path.abspath(__file__))
DURUM = os.path.join(KOK, "gelisim.json")
PY = os.path.join(os.path.dirname(KOK), "ses", "venv_xtts", "Scripts", "python.exe")
GUN, SAAT = 6, 20          # Pazar, 20:00
log = logging.getLogger()

# Dino'nun daha önce açıkça reddettiği şeyler (hafıza notlarından): bunlar önerilmez
REDDEDILEN_KALICI = [
    "ses tonu/duygu algılama (HuBERT) — iptal edildi",
    "PC'yi hep açık tutmak ya da bulut yedeği — Dino PC'nin kapanmasını istiyor",
    "Sakura'nın sesini LoRA/F5 ile değiştirmek — denendi, reddedildi",
    "şaşırma/iç çekme/esneme sesleri — reddedildi",
    "kapak kapanınca uyumama ayarı — Dino istemedi",
    "sohbette sonnet'e geçmek (sesli kanal haiku kalsın) — Dino ara yolu seçti",
]

ISTEM = """Sen Sakura adlı masaüstü sesli asistanın (Dino'nun kişisel asistanı, Türkçe, tatlı anime kızı kişiliği) gelişim
danışmanısın. Kodu """ + KOK + """ klasöründe (BENI-OKU.txt her şeyi anlatır). Aşağıda son 7 günün
verisi var. Bu veriye DAYANAN en çok 5 tane KÜÇÜK, somut ve güvenli geliştirme öner. Kurallar:
- Her öneri tek başına küçük bir iş olsun (birkaç dosya, yarım saatten kısa). Büyük yeniden yazım, yeni ücretli servis ya da
  büyük indirme önerme (gerekiyorsa açıkça yaz).
- Veride bir kanıtı olsun (ör. "bu hafta 12 kez kendini düzeltti: şu kelimeler", "cevap gecikmesi ortalama 9 sn").
- Şunları ÖNERME: {reddedilen}
- Veri azsa ya da iyi bir öneri yoksa daha az öner; boş liste de olur.
- "neden" Dino için: sade Türkçe, 1-2 cümle, teknik terim yok. "yapilacak" bir mühendis için: net ve ayrıntılı.
Çıktın YALNIZ şu JSON dizisi olsun, başka hiçbir şey yazma:
[{{"baslik": "en çok 60 harf", "neden": "...", "yapilacak": "...", "risk": "düşük|orta|yüksek", "yeniden_baslatma": true}}]

=== VERİ ===
{veri}
"""


def _durum():
    try:
        return json.load(open(DURUM, encoding="utf-8"))
    except (OSError, ValueError):
        return {"son": 0, "oneriler": {}}


def _kaydet(d):
    tmp = DURUM + ".tmp"
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, DURUM)


def _sayi(desen, satirlar):
    return [float(m.group(1)) for s in satirlar for m in [re.search(desen, s)] if m]


def veri_topla():
    parca = []
    # 1) asistan.log: son ~9000 satırdan istatistik (satırlarda tarih yok; bu kabaca son birkaç gündür)
    try:
        with open(os.path.join(KOK, "asistan.log"), encoding="utf-8", errors="replace") as f:
            log_s = collections.deque(f, maxlen=9000)
    except OSError:
        log_s = []
    log_s = [s for s in log_s if "Processing audio" not in s and "HTTP Request" not in s and '"GET /' not in s]
    gec = _sayi(r"cevap gecikmesi ([\d.]+) sn", log_s)
    ilk = _sayi(r"arama: ilk ses ([\d.]+) sn", log_s)
    duzeltti = [s.split("): ", 1)[-1].strip() for s in log_s if "kendini düzeltti" in s]
    duydum = [s for s in log_s if " duydum (" in s]
    yabanci = [s for s in duydum if "konuşan: ?" in s]
    kam_soru = sum(1 for s in log_s if "kamera: yüz ['?']" in s)
    kam_dino = sum(1 for s in log_s if "kamera: yüz ['Dino']" in s)
    sorun = [s.strip() for s in log_s if re.search(r"sağlık: sorun|hata|kopt|ulaşılamadı|yenisi açılıyor|başlatılamadı", s)]
    ort = lambda x: f"{sum(x) / len(x):.1f} sn (en çok {max(x):.1f}, {len(x)} kez)" if x else "veri yok"
    parca.append("## İstatistik (asistan.log son kısmı)\n"
                 f"- sesli cevap gecikmesi: {ort(gec)}\n- telefonda ilk ses: {ort(ilk)}\n"
                 f"- duyulan komut: {len(duydum)}, konuşanı tanıyamadığı: {len(yabanci)}\n"
                 f"- kamera değişimleri: Dino {kam_dino}, tanınmayan yüz {kam_soru}\n"
                 f"- kendini düzeltme (telaffuz/duyulma sorunu): {len(duzeltti)}\n")
    if duzeltti:
        parca.append("## Kendini düzelttiği cümleler (son 25)\n" + "\n".join(duzeltti[-25:]))
    if sorun:
        parca.append("## Sorun/hata satırları (son 30)\n" + "\n".join(sorun[-30:]))
    if duydum:
        parca.append("## Duyduğu komutlar (son 40; Whisper yanlış duymuş olabilir)\n" +
                     "\n".join(s.split("duydum", 1)[-1].strip()[:160] for s in duydum[-40:]))
    # 2) son 7 günün konuşma günlükleri
    bugun = datetime.date.today()
    for i in range(6, -1, -1):
        g = os.path.join(KOK, "beyin", "gunluk", (bugun - datetime.timedelta(days=i)).isoformat() + ".md")
        if os.path.exists(g):
            s = open(g, encoding="utf-8", errors="replace").read().splitlines()
            parca.append(f"## Konuşmalar {os.path.basename(g)[:-3]} (son 80 satır)\n" + "\n".join(x[:200] for x in s[-80:]))
    # 3) özet, hafıza (mizah), telaffuz sözlüğü, özellik başlıkları
    for ad, yol, n in [("Günlük özeti", "beyin/GUNLUK.md", 4000), ("Hafıza", "beyin/HAFIZA.md", 4000),
                       ("Telaffuz sözlüğü", "telaffuz_sozluk.txt", 1500)]:
        try:
            parca.append(f"## {ad}\n" + open(os.path.join(KOK, yol), encoding="utf-8", errors="replace").read()[-n:])
        except OSError:
            pass
    try:
        basliklar = [s.strip() for s in open(os.path.join(KOK, "BENI-OKU.txt"), encoding="utf-8").read().splitlines()
                     if s and not s.startswith((" ", "-", "\t")) and len(s) < 140]
        parca.append("## Var olan özellikler (BENI-OKU başlıkları)\n" + "\n".join(basliklar))
    except OSError:
        pass
    # 3b) son yapılan değişiklikler (BENI-OKU'nun sonu): zaten yapılmış şeyi yeniden önermesin
    try:
        parca.append("## SON YAPILAN DEĞİŞİKLİKLER (bunlar ZATEN YAPILDI, tekrar önerme)\n" +
                     open(os.path.join(KOK, "BENI-OKU.txt"), encoding="utf-8").read()[-9000:])
    except OSError:
        pass
    # 4) önceki öneriler (tekrar etmesin)
    eski = _durum()["oneriler"].values()
    if eski:
        parca.append("## Daha önce önerilenler (TEKRAR ÖNERME)\n" +
                     "\n".join(f"- {o['baslik']} → {o.get('durum')}" for o in list(eski)[-40:]))
    return "\n\n".join(parca)[-70000:]


def oner():
    from beyin import EXE
    istem = ISTEM.format(reddedilen="; ".join(REDDEDILEN_KALICI), veri=veri_topla())
    p = subprocess.run([EXE, "-p", "--model", "sonnet", "--disallowedTools", "Bash,Edit,Write,Read,WebFetch,WebSearch",
                        "--settings", json.dumps({"disableAllHooks": True})],
                       input=istem.encode("utf-8"), cwd=KOK, capture_output=True, timeout=900, creationflags=0x08000000)
    out = p.stdout.decode("utf-8", "replace")
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        log.info("gelişim: öneri okunamadı: %s", out[-300:])
        return []
    return [o for o in json.loads(m.group(0)) if o.get("baslik") and o.get("yapilacak")][:5]


def _tg(yontem, veri):
    import urllib.request, urllib.parse
    from telegram_kopru import anahtar, AYAR, SSL
    token, sahip = anahtar(), json.load(open(AYAR, encoding="utf-8")).get("sahip")
    if not (token and sahip):
        raise RuntimeError("Telegram hazır değil")
    veri = dict(veri, chat_id=sahip)
    with urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/{yontem}",
                                urllib.parse.urlencode(veri).encode()), timeout=30, context=SSL) as y:
        return json.loads(y.read())["result"]


def calistir(gonder=True):
    t = time.time()
    oneriler = oner()
    d = _durum()
    d["son"] = time.time()
    if not gonder:
        print(json.dumps(oneriler, ensure_ascii=False, indent=1))
        return oneriler
    if not oneriler:
        _tg("sendMessage", {"text": "🌱 Bu hafta geliştirme önerim yok tatlım, her şey yolunda görünüyor~"})
    else:
        _tg("sendMessage", {"text": f"🌱 Haftalık gelişim önerilerim ({len(oneriler)} tane)~\n"
                                    "Beğendiğine ✅ Yap, istemediğine ❌ Geç de. Sen onaylamadan hiçbir şeyi değiştirmem 💕"})
    for i, o in enumerate(oneriler, 1):
        oid = os.urandom(3).hex()
        o.update(durum="bekliyor", t=round(time.time()))
        d["oneriler"][oid] = o
        _tg("sendMessage", {
            "text": (f"{i}) {o['baslik']}\n\n{o.get('neden', '')}\n\n"
                     f"Risk: {o.get('risk', '?')} · Yeniden başlatma: {'gerekir' if o.get('yeniden_baslatma') else 'gerekmez'}")[:4000],
            "reply_markup": json.dumps({"inline_keyboard": [[{"text": "✅ Yap", "callback_data": f"gl:{oid}:y"},
                                                            {"text": "❌ Geç", "callback_data": f"gl:{oid}:n"}]]})})
    _kaydet(d)
    log.info("gelişim: %d öneri gönderildi (%.0f sn)", len(oneriler), time.time() - t)
    return oneriler


def dugme(oid, secim):
    """telegram_kopru 'gl:' düğmesinden çağırır (asistanın içinde). Telegram'a yazılacak kısa metni döndürür."""
    d = _durum()
    o = d["oneriler"].get(oid)
    if not o or o.get("durum") != "bekliyor":
        return "Bu öneri kapandı~"
    if secim != "y":
        o["durum"] = "geçildi"
        _kaydet(d)
        log.info("gelişim: Dino geçti: %s", o["baslik"])
        return f"Tamam, \"{o['baslik']}\" yok; bir daha önermem~"
    gorev = (
        "Sakura'nın sesli asistanı (" + KOK + ") için Dino'nun Telegram'dan ONAYLADIĞI geliştirme:\n"
        f"Başlık: {o['baslik']}\nNeden: {o.get('neden', '')}\nYapılacak: {o['yapilacak']}\n\n"
        "Kurallar:\n- Önce BENI-OKU.txt'yi oku.\n"
        f"- Değiştireceğin her dosyanın yedeğini yedek-gelisim-{datetime.date.today().isoformat()}\\ klasörüne al.\n"
        "- Yalnız bu değişikliği yap, başka şeye dokunma. Her değişen .py dosyasını venv python'la py_compile et; mümkünse "
        "asistanı bozmayan küçük bir çevrimdışı deneme yap.\n"
        f"- Asistanı yeniden başlatman gerekiyorsa ÖNCE Dino'ya haber ver: \"{PY}\" \"{os.path.join(KOK, 'tg_yaz.py')}\" "
        "\"Geliştirme hazır, şimdi kendimi yeniden başlatıyorum (~2 dk)~\"; sonra durdur.ps1, baslat.ps1 ve asistan.log'da "
        "'hazır' satırını gör. Açılmazsa yedeği geri koy ve yeniden başlat.\n"
        "- Ne yaptığını BENI-OKU.txt'nin sonuna kısaca yaz.\n"
        "- Büyük, geri alınamaz ya da ücretli bir şey gerekiyorsa YAPMA, özetinde Dino'ya ne gerektiğini yaz.\n"
        "- Sonunda Türkçe, kısa ve samimi bir özet ver: ne değişti, Dino neyi fark edecek.")
    # 8 Kas dersi: 3 onay üst üste gelince 3 iş aynı anda aynı dosyaları düzenleyip asistanı ayrı ayrı yeniden başlattı.
    # Artık sıraya girer; _sira tek tek çalıştırır (önceki iş ===BITTI=== olunca sonraki başlar).
    onde = sum(1 for x in d["oneriler"].values() if x.get("durum") in ("sırada", "yapılıyor"))
    o.update(durum="sırada", gorev=gorev, onay=round(time.time()))
    _kaydet(d)
    log.info("gelişim: Dino onayladı, sıraya alındı (%d önde): %s", onde, o["baslik"])
    sira_baslat()
    return (f"✅ \"{o['baslik']}\" için Claude'a iş verdim, bitince haber veririm~" if not onde else
            f"✅ \"{o['baslik']}\" sıraya aldım (önünde {onde} iş var), sırası gelince yapılacak~")


_sira_kilit = __import__("threading").Lock()


def _is_bitti(ad, baslama):
    if not ad:
        return time.time() - baslama > 30 * 60   # iş adı bulunamadıysa 30 dk sonra bitti say
    try:
        return open(os.path.join(KOK, "isler", ad + ".txt"), encoding="utf-8", errors="replace").read().rstrip() \
            .endswith("===BITTI===")
    except OSError:
        return time.time() - baslama > 30 * 60


def _sira():
    if not _sira_kilit.acquire(blocking=False):
        return   # zaten çalışan bir sıra var
    try:
        while True:
            d = _durum()
            calisan = [o for o in d["oneriler"].values() if o.get("durum") == "yapılıyor"]
            degisti = False
            for o in calisan:
                if _is_bitti(o.get("is"), o.get("basladi", 0)):
                    o["durum"] = "yapıldı"
                    degisti = True
            if degisti:
                _kaydet(d)
            if any(o.get("durum") == "yapılıyor" for o in d["oneriler"].values()):
                time.sleep(15)
                continue
            sirada = sorted((o for o in d["oneriler"].values() if o.get("durum") == "sırada" and o.get("gorev")),
                            key=lambda o: o.get("onay", 0))
            if not sirada:
                return
            o = sirada[0]
            once = set(glob.glob(os.path.join(KOK, "isler", "*.json")))
            subprocess.Popen([PY, os.path.join(KOK, "is_ver.py"), o["gorev"], KOK], cwd=KOK, creationflags=0x08000000,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ad = None
            for _ in range(30):   # is_ver.py iş kaydını (isler\<ad>.json) oluşturunca adını al
                time.sleep(2)
                yeni = set(glob.glob(os.path.join(KOK, "isler", "*.json"))) - once
                if yeni:
                    ad = os.path.basename(sorted(yeni)[-1])[:-5]
                    break
            o.update(durum="yapılıyor", basladi=round(time.time()), **({"is": ad} if ad else {}))
            _kaydet(d)
            log.info("gelişim: sıradaki iş Claude'a verildi (%s): %s", ad or "?", o["baslik"])
    except Exception as e:
        log.info("gelişim sırası: %s", e)
    finally:
        _sira_kilit.release()


def sira_baslat():
    __import__("threading").Thread(target=_sira, daemon=True).start()


def dongu(asistan=None):
    """Asistanın içinde: Pazar SAAT'ten sonra haftada bir; PC o gün kapalıysa 8 gün dolunca ilk açılışta (10-22 arası)."""
    time.sleep(60)
    sira_baslat()   # yeniden başlatmadan önce sırada kalan onaylı işler varsa devam
    time.sleep(240)
    while True:
        try:
            simdi = datetime.datetime.now()
            gecen = time.time() - _durum().get("son", 0)
            if (simdi.weekday() == GUN and simdi.hour >= SAAT and gecen > 6 * 86400) or \
               (_durum().get("son") and gecen > 8 * 86400 and 10 <= simdi.hour < 22):
                calistir()
        except Exception as e:
            log.exception("gelişim: %s", e)
            time.sleep(1800)
        time.sleep(600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if "--deneme" in sys.argv:
        calistir(gonder=False)
    elif "--simdi" in sys.argv:
        calistir()
    else:
        print("python gelisim.py --simdi | --deneme")
