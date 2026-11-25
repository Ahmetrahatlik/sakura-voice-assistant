# XTTS'e gitmeden önce metni "okunduğu gibi" yazar (balon metni değişmez, yalnız ses).
#   1) sayilar(): saat, yüzde, ondalık, sıra sayısı, 9'da gibi ekler → ayrı yazılmış Türkçe kelimeler
#      (XTTS'in kendi çevirisi "onbeş", "ondördüncükırkbeş", "yedi:otuz" gibi bitişik/bozuk çıkıyor)
#   2) sozluk(): telaffuz_sozluk.txt — XTTS'in bozduğu kelimelerin doğru okunan yazımı (Whisper ile seçildi)
import os, re

KOK = os.path.dirname(os.path.abspath(__file__))
BIRLER = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
ONLAR = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
BUYUK = [(10 ** 9, "milyar"), (10 ** 6, "milyon"), (1000, "bin")]
SIRA = {"bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci", "altı": "altıncı",
        "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu", "on": "onuncu", "yirmi": "yirminci",
        "otuz": "otuzuncu", "kırk": "kırkıncı", "elli": "ellinci", "altmış": "altmışıncı", "yetmiş": "yetmişinci",
        "seksen": "sekseninci", "doksan": "doksanıncı", "yüz": "yüzüncü", "bin": "bininci", "milyon": "milyonuncu",
        "milyar": "milyarıncı", "sıfır": "sıfırıncı"}
KISALTMA = {"TL": "lira", "₺": "lira", "vs.": "vesaire", "vb.": "ve benzeri", "dk.": "dakika", "sn.": "saniye",
            "km": "kilometre", "kg": "kilo", "GB": "gigabayt", "MB": "megabayt"}


def sayi(n):
    if n == 0:
        return "sıfır"
    s = []
    for b, ad in BUYUK:
        if n >= b:
            k, n = divmod(n, b)
            s += ([] if (b == 1000 and k == 1) else [sayi(k)]) + [ad]
    if n >= 100:
        k, n = divmod(n, 100)
        s += ([] if k == 1 else [BIRLER[k]]) + ["yüz"]
    s += [w for w in (ONLAR[n // 10], BIRLER[n % 10]) if w]
    return " ".join(s)


def sira(n):
    w = sayi(n).split()
    return " ".join(w[:-1] + [SIRA[w[-1]]])


def _saat(m, i=1):
    h, d = int(m.group(i)), int(m.group(i + 1))
    if h > 24 or d > 59:
        return m.group(0)
    return sayi(h) + ("" if d == 0 else " " + ("sıfır " if d < 10 else "") + sayi(d))


def sayilar(t):
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", _saat, t)
    t = re.sub(r"(?i)\b(saat\s+)(\d{1,2})\.(\d{2})\b", lambda m: m.group(1) + _saat(m, 2), t)
    t = re.sub(r"\b(\d{1,3}(?:\.\d{3})+)\b", lambda m: m.group(1).replace(".", ""), t)   # 1.250 → 1250
    t = re.sub(r"%\s?(\d)", r"yüzde \1", t)
    t = re.sub(r"\b(\d+),5\b", lambda m: sayi(int(m.group(1))) + " buçuk", t)
    t = re.sub(r"\b(\d+),(\d+)\b", lambda m: sayi(int(m.group(1))) + " virgül " + sayi(int(m.group(2))), t)
    t = re.sub(r"\b(\d+)\.(?=\s+[a-zçğıöşü])", lambda m: sira(int(m.group(1))), t)      # "3. kat" → üçüncü
    t = re.sub(r"\b(\d+)['’](\w+)", lambda m: sayi(int(m.group(1))) + m.group(2), t)    # 9'da → dokuzda
    t = re.sub(r"\b\d+\b", lambda m: sayi(int(m.group(0))), t)
    # TL'ye → liraya: ek "tele" okunuşuna göre yazılmış, "lira"ya göre kalın ünlüye çevrilir
    t = re.sub(r"\bTL['’](\w+)", lambda m: "lira" + m.group(1).translate(str.maketrans("eiüö", "aıuo")), t)
    for k, v in KISALTMA.items():
        t = re.sub(r"(?<!\w)" + re.escape(k) + r"(?!\w)", v, t)
    return re.sub(r"(?<=\w)['’](?=\w)", "", t)   # kesme işareti XTTS'te gereksiz durak yapabiliyor


def _sozluk_oku():
    d = []
    yol = os.path.join(KOK, "telaffuz_sozluk.txt")
    if os.path.exists(yol):
        for satir in open(yol, encoding="utf-8"):
            satir = satir.split("#")[0].strip()
            if "=" in satir:
                k, v = (x.strip() for x in satir.split("=", 1))
                # kelimenin başı eşleşir, ek korunur: "alarm" → "alarmı", "alarmlar" da düzelir
                d.append((re.compile(r"(?i)(?<!\w)" + re.escape(k) + r"(?=\w*)"), v))
    return d


SOZLUK = _sozluk_oku()
_SOZLUK_ZAMAN = [0.0]


def sozluk(t):
    # Sakura, Dino düzeltince sözlüğe kendisi yazıyor: dosya değiştiyse yeniden oku (yeniden başlatmadan işe yarasın)
    global SOZLUK
    yol = os.path.join(KOK, "telaffuz_sozluk.txt")
    z = os.path.getmtime(yol) if os.path.exists(yol) else 0.0
    if z != _SOZLUK_ZAMAN[0]:
        SOZLUK, _SOZLUK_ZAMAN[0] = _sozluk_oku(), z
    for r, v in SOZLUK:
        t = r.sub(v, t)
    return t


def duzelt(t):
    t = sozluk(sayilar(t))
    # XTTS metni Python lower() ile küçültür: "I" → "i" (Iğdır → iğdir), "İ" → "i̇" (fazladan nokta işareti)
    t = t.replace("I", "ı").replace("İ", "i")
    # "~" silinince cümle noktasız kalıyor; XTTS noktasız sonu uzatıyor ("tatlım" → "tatlımın").
    # Ünlem en iyisi (aday_test: "~"→"!" 16/20 tam cümle, "." 11/20, "..." 14/20)
    t = re.sub(r"\s*~+\s*$", "!", t.strip())
    t = re.sub(r"~+", ",", t)
    if t and t[-1] not in ".!?…":
        t += "."
    return t


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or ["Saat 9'da toplantı var, şarj %15'e düştü.", "Alarmı 07:30'a kurdum, saat 14.45 oldu.",
                               "3. kattaki 1.250 TL'lik ürün 3,5 kilo, 2026 yılı.", "Bugün 4 Kasım, 12,75 derece."]:
        print(s, "→", duzelt(s))
