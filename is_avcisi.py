# İş avcısı (5 Kas 2026, Dino istedi): her sabah 09:00'dan sonra (bilgisayar açıksa, günde bir kez) LinkedIn'deki son
# 24 saatin ilanlarına bakar, Dino'nun CV'sine uyanları seçip Telegram'dan gönderir. Başvuru YAPMAZ: Dino seçer.
# - Kaynak: LinkedIn'in girişsiz ilan sayfaları. Kariyer.net / Indeed / SecretCV programla açılmıyor (403 / JS), yok.
# - Eleme: başlıkta kıdemli/stajyer işler, izinli şehir/uzaktan dışı, daha önce gönderilen ilan, is_avcisi_haric.txt'deki
#   şirketler (önceden başvurulan/elenenler; Dino ekleyebilir). Kalanlar Claude'a (sonnet) CV ile birlikte puanlatılır.
# - Elle: python is_avcisi.py --simdi (hemen gönder) · --deneme (göndermeden ekrana yaz, gördü sayma)
import os, re, sys, json, time, html, random, logging, datetime, subprocess, urllib.request, urllib.parse

KOK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KOK)
DURUM = os.path.join(KOK, "is_avcisi.json")
HARIC = os.path.join(KOK, "is_avcisi_haric.txt")
CALISMA = os.path.join(KOK, "is_avcisi_calisma")   # Claude burada çalışır (beyin\CLAUDE.md kişiliği karışmasın)
SAAT = 9
ARAMALAR = ["python", "yazılım geliştirici", "backend developer", "yapay zeka", "junior developer", "otomasyon yazılım",
            "junior software", "yeni mezun yazılım", "python developer"]
SEHIRLER = ("istanbul", "ankara", "izmir", "i̇zmir", "bursa", "konya")
KIDEMLI = re.compile(r"\b(?:senior|sr\.?|lead|kıdemli|principal|staff|manager|müdür|yönetici|architect|head|direkt[öo]r|"
                     r"chief|cto|intern|internship|stajyer|staj|uzun dönem stajyer)\b", re.I)
EN_COK_DETAY = 30
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5"}
log = logging.getLogger()

CV = """Dino (Ahmet Rahatlık): Junior Python backend + yapay zekâ otomasyonu. Afyon Kocatepe Üniversitesi Bilgisayar
Programcılığı (2 yıllık, 2026 mezun) — LİSANS DEĞİL. İngilizce B1: İngilizce mülakat/İngilizce çalışma ortamı istemiyor,
Türkçe işler. Projeler: Klis (yapay zekâ asistanı), restoran veri hattı, GreenMap, bir hırdavat işletmesinin kullandığı stok
programı (telefon + PC), SpotMe (ilan sitesi; YouTube eğitim videoları ve Reels üretimi), Claude Code / yapay zekâ ajanlarıyla
otomasyon. Bilmediği (henüz): Docker, FastAPI/REST, PostgreSQL. Deneyim: yeni mezun (0-1 yıl). Konya'da; İstanbul, Ankara,
İzmir, Bursa'ya taşınabilir ya da uzaktan. Maaş beklentisi net 35-40 bin TL ve üstü."""

ISTEM = """Aşağıda Dino'nun özgeçmiş özeti ve bugün LinkedIn'de çıkan iş ilanları var. Her ilana Dino için 0-10 uygunluk puanı ver.
Yüksek puan: junior/yeni mezun/0-2 yıl kabul eden, Python, backend, otomasyon, yapay zekâ, yazılım geliştirme; Türkçe ortam.
Düşük puan: 2+ yıl deneyim şartı, lisans/mühendislik diploması ZORUNLU, akıcı İngilizce şartı, Java/.NET/C++ gibi bilmediği ana
dil, satış/çağrı merkezi, maaş yazıyorsa net 35 bin TL altı. Emin olmadığın ilanı orta puanla.
SADECE JSON dizi yaz, başka hiçbir şey yazma: [{{"id": "...", "puan": 7, "neden": "en çok 15 kelime, Türkçe, neden uygun / dikkat"}}]

ÖZGEÇMİŞ:
{cv}

İLANLAR:
{ilanlar}"""


def _al(url, deneme=2):
    import ssl, certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    for i in range(deneme):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=25, context=ctx) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == deneme - 1:
                log.info("iş avcısı: %s → %s", url[:80], e)
            time.sleep(3)
    return ""


def _metin(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def _tr_kucuk(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def ilanlari_bul(sure="r86400"):
    bulunan = {}
    for kelime in ARAMALAR:
        # f_WT=2 (uzaktan) girişsiz sayfada işlemiyor (5 Kas: her şehirden ilan döndü); uzaktan başlık/yerden anlaşılır
        for start in (0, 25):
            p = {"keywords": kelime, "location": "Türkiye", "f_TPR": sure, "start": start}
            t = _al("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + urllib.parse.urlencode(p))
            for kart in t.split("<li")[1:]:
                m = re.search(r"jobPosting:(\d+)", kart)
                if not m:
                    continue
                al = lambda sinif: _metin((re.search(sinif + r'[^>]*>(.*?)</', kart, re.S) or [None, ""])[1])
                ilan = dict(id=m.group(1), baslik=al(r'base-search-card__title"'), sirket=al(r'base-search-card__subtitle"[^>]*>\s*<a'),
                            yer=al(r'job-search-card__location"'))
                if not ilan["sirket"]:
                    ilan["sirket"] = al(r'base-search-card__subtitle"')
                ilan["uzaktan"] = bool(re.search(r"remote|uzaktan", _tr_kucuk(ilan["baslik"] + " " + ilan["yer"])))
                bulunan[ilan["id"]] = ilan
            time.sleep(random.uniform(1.0, 2.0))
            if t.count("<li") < 20:
                break   # ikinci sayfa yok
    return list(bulunan.values())


def _haric():
    try:
        return [_tr_kucuk(s.strip()) for s in open(HARIC, encoding="utf-8") if s.strip() and not s.startswith("#")]
    except OSError:
        return []


def _durum():
    try:
        return json.load(open(DURUM, encoding="utf-8"))
    except (OSError, ValueError):
        return {"son_gun": None, "gorulen": {}}


def ele(ilanlar, durum):
    haric = _haric()
    kalan = []
    for i in ilanlar:
        yer = _tr_kucuk(i["yer"])
        if i["id"] in durum["gorulen"] or KIDEMLI.search(i["baslik"]):
            continue
        if not (i["uzaktan"] or yer.strip() in ("türkiye", "turkey") or any(s in yer for s in SEHIRLER)):
            continue
        sirket = _tr_kucuk(i["sirket"])
        if any(re.search(r"(?<!\w)" + re.escape(h) + r"(?!\w)", sirket) for h in haric):   # tam kelime: Lime ≠ Limestone
            continue
        kalan.append(i)
    return kalan


def detay(i):
    t = _al(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{i['id']}")
    m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', t, re.S)
    i["aciklama"] = _metin(m.group(1))[:2500] if m else ""
    kriter = re.findall(r'description__job-criteria-text[^>]*>(.*?)</span>', t, re.S)
    i["kriter"] = ", ".join(_metin(k) for k in kriter)


def puanla(ilanlar):
    from beyin import EXE
    metin = "\n\n".join(f"[id {i['id']}] {i['baslik']} — {i['sirket']} — {i['yer']}{' (uzaktan)' if i['uzaktan'] else ''}\n"
                        f"Kriter: {i.get('kriter', '')}\n{i.get('aciklama', '')}" for i in ilanlar)
    os.makedirs(CALISMA, exist_ok=True)
    p = subprocess.run([EXE, "-p", "--model", "sonnet", "--disallowedTools", "Bash,Edit,Write,Read,WebFetch,WebSearch",
                        "--settings", json.dumps({"disableAllHooks": True})],
                       input=ISTEM.format(cv=CV, ilanlar=metin[:60000]).encode("utf-8"), cwd=CALISMA, capture_output=True,
                       timeout=600, creationflags=0x08000000)
    out = p.stdout.decode("utf-8", "replace")
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        log.info("iş avcısı: puan okunamadı: %s", out[-300:])
        return {}
    return {str(x["id"]): x for x in json.loads(m.group(0))}


def telegram_gonder(metin):
    from telegram_kopru import anahtar, AYAR, SSL
    token, sahip = anahtar(), json.load(open(AYAR, encoding="utf-8")).get("sahip")
    if not (token and sahip):
        return False
    veri = urllib.parse.urlencode({"chat_id": sahip, "text": metin[:4000], "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", veri), timeout=30, context=SSL)
    return True


def calistir(gonder=True):
    t = time.time()
    durum = _durum()
    ilk_kez = not durum["gorulen"]
    ilanlar = ilanlari_bul("r259200" if ilk_kez else "r86400")   # ilk çalışmada son 3 gün
    aday = ele(ilanlar, durum)
    log.info("iş avcısı: %d ilan bulundu, %d aday", len(ilanlar), len(aday))
    aday = aday[:EN_COK_DETAY]
    for i in aday:
        detay(i)
        time.sleep(random.uniform(0.8, 1.6))
    puan = puanla(aday) if aday else {}
    secilen = sorted((i for i in aday if puan.get(i["id"], {}).get("puan", 0) >= 6),
                     key=lambda i: -puan[i["id"]]["puan"])[:5]
    yakin = False
    if not secilen:   # tam uyan yoksa en yakın 2 tanesi (4-5 puan), "tam uymuyor" notuyla
        secilen = sorted((i for i in aday if puan.get(i["id"], {}).get("puan", 0) >= 4),
                         key=lambda i: -puan[i["id"]]["puan"])[:2]
        yakin = bool(secilen)
    if secilen:
        satir = [f"🧑‍💻 Bugün tam sana göre ilan yok tatlım, ama en yakın {len(secilen)} tanesi şunlar~ (LinkedIn)\n" if yakin else
                 f"🧑‍💻 Bugün sana uygun {len(secilen)} ilan buldum tatlım~ (LinkedIn, son {'3 gün' if ilk_kez else '24 saat'})\n"]
        for n, i in enumerate(secilen, 1):
            satir.append(f"{n}) {i['baslik']} — {i['sirket']} ({i['yer']}{', uzaktan' if i['uzaktan'] else ''})\n"
                         f"   ⭐ {puan[i['id']]['puan']}/10 · {puan[i['id']].get('neden', '')}\n"
                         f"   https://www.linkedin.com/jobs/view/{i['id']}\n")
        satir.append("Beğendiğin olursa söyle, başvuru yazısını birlikte hazırlarız~ Başvurmadan önce ilanın açık olduğuna bak.")
        mesaj = "\n".join(satir)
    else:
        mesaj = "🧑‍💻 Bugün LinkedIn'de sana uyan yeni ilan çıkmadı tatlım, yarın yine bakarım~"
    if not gonder:
        print(mesaj)
        return mesaj
    bugun = datetime.date.today().isoformat()
    for i in aday:
        durum["gorulen"][i["id"]] = bugun
    sinir = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
    durum["gorulen"] = {k: v for k, v in durum["gorulen"].items() if v >= sinir}
    durum["son_gun"] = bugun
    gitti = telegram_gonder(mesaj)
    json.dump(durum, open(DURUM, "w", encoding="utf-8"), ensure_ascii=False)
    try:
        import hafiza
        hafiza.olay("Sistem", "(İş avcısı: Dino'ya Telegram'dan bugünün ilanları gönderildi: " +
                    ("; ".join(f"{i['baslik']} — {i['sirket']}" for i in secilen) or "uygun ilan yok") + ")")
    except Exception:
        pass
    log.info("iş avcısı: %d ilan gönderildi (%s), %.0f sn", len(secilen), "Telegram" if gitti else "Telegram YOK", time.time() - t)
    return mesaj


def dongu(asistan=None):
    """Asistanın içinde: her gün SAAT'ten sonra bir kez (bilgisayar o saatte kapalıysa açılınca)."""
    time.sleep(120)
    while True:
        try:
            if datetime.datetime.now().hour >= SAAT and _durum().get("son_gun") != datetime.date.today().isoformat():
                calistir()
        except Exception as e:
            log.exception("iş avcısı: %s", e)
            time.sleep(1800)
        time.sleep(300)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if "--deneme" in sys.argv:
        calistir(gonder=False)
    elif "--simdi" in sys.argv:
        calistir()
    else:
        print(__doc__ or "python is_avcisi.py --simdi | --deneme")
