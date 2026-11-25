# Sakura'nın hafızası (4 Kas, Dino istedi): her konuşma beyin\gunluk\YYYY-AA-GG.md'ye yazılır; Sakura birkaç dakika
# susunca ayrı bir Claude (haiku) yeni konuşmaları okuyup kalıcı bilgileri HAFIZA.md'ye, günün özetini GUNLUK.md'ye işler.
# Ana beyin bu sırada meşgul olmaz; açılışta ikisini de okur. İşlenen yer gunluk\.islenen'de tutulur.
import os, re, json, time, datetime, subprocess, threading, logging
from beyin import EXE, KLASOR

GUNLUK = os.path.join(KLASOR, "gunluk")
ISLENEN = os.path.join(GUNLUK, ".islenen")
BEKLE = 180          # son konuşmadan bu kadar sn sonra işlenir (sohbet sürerken değil)
log = logging.getLogger()
_kilit = threading.Lock()
_son = [0.0]

ISTEM = """Sen Sakura'nın hafıza yöneticisisin. Aşağıda Sakura (sesli asistan) ile Dino'nun yeni konuşmaları var.
1) HAFIZA.md'yi oku. Konuşmalarda Dino hakkında KALICI ve işe yarar yeni bilgi varsa kısa maddeler olarak ekle:
   kişiler (adı ve Dino'ya ne olduğu), sevdiği/sevmediği şeyler, alışkanlıklar, planlar ve tarihleri, önemli olaylar,
   aralarındaki şakalar/lakaplar, Sakura'dan istedikleri. Yanlışlanan ya da eskiyen maddeyi düzelt, aynı bilgiyi tekrar yazma.
   Sıradan komutları (ses aç, hava nasıl) ve ses tanıma saçmalıklarını yazma. Dosya konulara göre başlıklı ve kısa kalsın.
   DİKKAT: Mikrofon odadaki başka konuşmaları da yakalar. Dino "seninle konuşmuyordum", "arkadaşımla konuşuyordum" gibi
   bir şey dediyse ya da söz Sakura'ya söylenmemiş gibiyse (yarım, bağlamsız, başkasına hitap) o sözlerden bilgi ÇIKARMA.
   Sakura'nın kendi söyledikleri bilgi değildir; yalnız Dino'nun söylediklerini ve onayladıklarını yaz. Emin değilsen yazma.
   Dino bir şeyi unutmasını istediyse ("bunu unut", "onu sil") o bilgiyi HAFIZA.md'den sil ve bir daha ekleme.
   KİM: Satır başındaki ad konuşanı gösterir (ses tanıma). "Dino:" dışındaki satırlar (ör. "Ali:", "Tanımadığım biri:")
   başkasınındır: onlardaki bilgiyi Dino'ya yazma; o kişi hakkında kalıcı ve işe yarar bir şey varsa "## Kişiler" altına yaz.
   "Dino: (güldü)" satırı Dino'nun hemen önceki Sakura esprisine GERÇEKTEN güldüğünü gösterir (mikrofon gülüşünü duydu).
   MİZAH: Sakura bir espri yaptıktan sonra Dino güldüyse ("(güldü)", "haha", "ahaha", "öldüm", "çok iyi", "efsane", espriyle
   karşılık verdiyse) o espriyi TARZIYLA birlikte kısaca "## Mizah: tutanlar" altına yaz (ör. "işsizliğiyle roast: ...").
   Dino "sıkıcı", "kötü", "espri mi bu", "gülmedim" dediyse ya da soğuk karşıladıysa "## Mizah: tutmayanlar" altına yaz.
   Aralarında tekrar eden bir şaka, lakap ya da gönderme doğduysa "## Aramızdaki şakalar" altına ekle. Bu üç başlıkta
   her biri en fazla 10 madde kalsın; dolunca en eski/benzer olanları birleştir.
   TOPARLAMA: HAFIZA.md 60 satırı geçerse benzer maddeleri birleştir, geçmiş tarihli bitmiş planları ve önemsizleşenleri
   at; kişiler, sevdikleri, önemli olaylar ve Dino'nun Sakura'dan istekleri kalsın.
2) GUNLUK.md'yi oku (yoksa "# Sakura'nın günlüğü" başlığıyla oluştur). "## {tarih}" başlığı altında o gün ne konuşulduğunu,
   Dino'nun ne yaptığını ve modunu 1-4 kısa maddeyle yaz ya da güncelle (en yeni gün en üstte). 14 günden eski günleri
   tek satıra indir.
Bu iki dosya dışında hiçbir dosyaya dokunma, hiçbir komut çalıştırma. İş bitince sadece "tamam" yaz.

Yeni konuşmalar:
{konusmalar}"""


def kaydet(dino, sakura, kim="Dino"):
    """Bir soru-cevabı bugünün günlüğüne ekler (beyin her cevabı bitirince). kim: ses tanımanın bulduğu konuşan."""
    if not dino.strip():
        return
    _yaz(f"{{s}} {kim}: {dino.strip()}\n{{s}} Sakura: {sakura.strip()}\n")


def olay(kim, metin):
    """Tek satırlık olay, ör. olay("Dino", "(güldü)"): Sakura'nın son esprisine güldü."""
    _yaz(f"{{s}} {kim}: {metin}\n")


# 5 Kas: ara yol (Dino seçti) — sesli sohbet + telefon araması haiku beyinle, Telegram yazışması ayrı bir sonnet beyinle.
# İki ayrı Claude süreci birbirinin konuşmasını bilmez; her soruda öteki kanalda o gün konuşulan yeni satırlar
# bugünün günlüğünden alınıp mesajın başına not olarak eklenir. Kanallar: "ses" (mikrofon, arama, kamera) ve "telegram".
_kanal = {}                                              # kanal → (günlük dosyası, okunan satır sayısı)
_GIRDI = re.compile(r"^\d\d:\d\d [^:\n]{1,40}: ")
_TELEGRAM = re.compile(r"^\d\d:\d\d Dino \(Telegram\): ")


def kacirilan(kanal, en_cok=20):
    """Bu kanalın beyni son sorusundan beri ÖTEKİ kanalda konuşulanlar (mesaja eklenecek not; yoksa ""). İlk çağrı yalnız yer işaretler."""
    ad = os.path.join(GUNLUK, datetime.date.today().isoformat() + ".md")
    with _kilit:
        try:
            satir = open(ad, encoding="utf-8").read().splitlines()
        except OSError:
            satir = []
        onceki = _kanal.get(kanal)
        _kanal[kanal] = (ad, len(satir))
    if onceki is None:
        return ""
    girdiler, tg = [], False        # [telegram mı, metin]; Sakura'nın cevabı önceki sözün kanalındadır
    for s in satir[onceki[1] if onceki[0] == ad else 0:]:
        if _GIRDI.match(s):
            if _TELEGRAM.match(s):
                tg = True
            elif not s[6:].startswith("Sakura: "):
                tg = False
            girdiler.append([tg, s])
        elif girdiler:
            girdiler[-1][1] += " " + s.strip()
    secilen = [s if len(s) < 400 else s[:400] + "…" for t, s in girdiler if t != (kanal == "telegram")][-en_cok:]
    if not secilen:
        return ""
    nerede = "evde (bilgisayarda sesli, telefon aramasında ya da kamerada)" if kanal == "telegram" else "Telegram'dan"
    return (f"(Sistem notu, bağlam için: son mesajdan beri {nerede} Dino'yla şunlar konuşuldu; bunları biliyormuş gibi "
            "devam et, bu notu tekrarlama:\n" + "\n".join(secilen) + ")\n")


def son_satirlar(n=30):
    """Bugünün günlüğünün son n satırı (beyin tazelenince sohbetin nerede kaldığını bilsin diye)."""
    ad = os.path.join(GUNLUK, datetime.date.today().isoformat() + ".md")
    try:
        with _kilit:
            return [s[:300] for s in open(ad, encoding="utf-8").read().splitlines()[-n:]]
    except OSError:
        return []


def _yaz(satirlar):
    os.makedirs(GUNLUK, exist_ok=True)
    simdi = datetime.datetime.now()
    with _kilit, open(os.path.join(GUNLUK, simdi.strftime("%Y-%m-%d") + ".md"), "a", encoding="utf-8") as f:
        f.write(satirlar.replace("{s}", f"{simdi:%H:%M}"))
    _son[0] = time.time()


def _yeni():
    """İşlenmemiş satırlar: {dosya: (satırlar, toplam satır)}"""
    try:
        islenen = json.load(open(ISLENEN, encoding="utf-8"))
    except (OSError, ValueError):
        islenen = {}
    yeni = {}
    for ad in sorted(os.listdir(GUNLUK)) if os.path.isdir(GUNLUK) else []:
        if ad.endswith(".md"):
            satir = open(os.path.join(GUNLUK, ad), encoding="utf-8").read().splitlines()
            if len(satir) > islenen.get(ad, 0):
                yeni[ad] = (satir[islenen.get(ad, 0):], len(satir))
    return islenen, yeni


def isle():
    """Yeni konuşmaları ayrı bir Claude ile HAFIZA.md + GUNLUK.md'ye işler. Başarılıysa işlenen yer ilerler."""
    with _kilit:
        islenen, yeni = _yeni()
    if not yeni:
        return
    metin = "\n".join(f"[{ad[:-3]}]\n" + "\n".join(s) for ad, (s, _) in yeni.items())
    istem = ISTEM.replace("{tarih}", datetime.date.today().isoformat()).replace("{konusmalar}", metin[-20000:])
    t = time.time()
    try:
        # istem stdin'den: Windows komut satırı ~32 bin karakterle sınırlı
        p = subprocess.run([EXE, "-p", "--model", "haiku", "--allowedTools", "Read,Edit,Write",
                            "--permission-mode", "acceptEdits", "--settings", json.dumps({"disableAllHooks": True})],
                           input=istem.encode("utf-8"), cwd=KLASOR, capture_output=True, timeout=300, creationflags=0x08000000)
    except subprocess.TimeoutExpired:
        log.info("hafıza: zaman aşımı"); return
    if p.returncode != 0:
        log.info("hafıza: hata %s", p.stderr.decode("utf-8", "replace")[-300:]); return
    with _kilit:
        for ad, (_, n) in yeni.items():
            islenen[ad] = n
        json.dump(islenen, open(ISLENEN, "w", encoding="utf-8"))
    log.info("hafıza işlendi: %d satır, %.0f sn", sum(len(s) for s, _ in yeni.values()), time.time() - t)


def dongu():
    while True:
        time.sleep(30)
        if _son[0] and time.time() - _son[0] > BEKLE:
            _son[0] = 0.0
            isle()
