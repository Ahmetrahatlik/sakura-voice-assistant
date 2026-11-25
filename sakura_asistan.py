# Sakura sesli asistan: "Sakura" deyince uyanır, Whisper ile dinler, Claude Code ile düşünür, B sesiyle (XTTS) konuşur,
# masaüstü Sakura'nın balonu ve ağzı eşlik eder. venv_xtts ile çalışır.
#   python sakura_asistan.py              → mikrofon
#   python sakura_asistan.py --dosya a.wav → test: mikrofon yerine dosya (her dosya bir konuşma)
import os, sys, re, glob, time, random, queue, socket, threading, collections, difflib, argparse, logging, ctypes, hashlib

KOK = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None:  # pythonw: pencere yok; kütüphanelerin ekrana yazdıkları hata vermesin, dosyaya gitsin
    sys.stdout = sys.stderr = open(os.path.join(KOK, "asistan.out"), "w", encoding="utf-8", buffering=1)
SES = os.path.join(os.path.dirname(KOK), "ses")
os.environ.setdefault("HF_HOME", os.path.join(SES, "hf"))
os.environ.setdefault("TTS_HOME", os.path.join(SES, "hf", "tts"))
os.environ["COQUI_TOS_AGREED"] = "1"
sys.path.insert(0, KOK)

import numpy as np
from scipy.signal import resample_poly
import torch
os.add_dll_directory(os.path.join(os.path.dirname(torch.__file__), "lib"))  # CTranslate2 torch'un cuBLAS/cuDNN'ini kullanır
import sounddevice as sd
import soundfile as sf
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad
from TTS.api import TTS

import hizli, hizli_xtts, sakura_ui, telaffuz, hafiza, ses_izi, gorevler
DINO_YAKIN = 60   # sn (6 Kas)
from beyin import Beyin

logging.basicConfig(filename=os.path.join(KOK, "asistan.log"), level=logging.INFO, encoding="utf-8",
                    format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger()

SR = 16000
PARCA = 512                       # 32 ms (silero VAD'in istediği boy)
SESSIZLIK_SONU = 0.65             # bu kadar sessizlik konuşmayı bitirir
YAVAS_ESIK = 10.0                 # 8 Kas: cevap bundan uzun sürerse aşama süreleri günlüğe ("yavaş: ...")
TAKIP = 8.0                       # Sakura SORU sorduysa, cevabını bu süre içinde "Sakura" demeden verebilirsin
BEYIN_MODEL = "haiku"             # haiku: ilk cümle ~2 sn; sonnet daha akıllı ama ~2 kat yavaş
TELEGRAM_MODEL = "sonnet"         # 5 Kas ara yol (Dino seçti): sesli sohbet + arama haiku, Telegram yazışması sonnet (telegram_kopru)
# 4 Kas: Dino 2 numarayı seçti = B'nin referansları Praat ile orta inceltildi (formant 1,08, perde 1,20; ses\test\uret_ince.py)
REF = [os.path.join(SES, "ornekler", "ince", "2_uzun_ref.wav"), os.path.join(SES, "ornekler", "ince", "2_9_xtts_yeni_ref.wav")]
B_AYAR = dict(temperature=0.3, top_p=0.7, top_k=30, repetition_penalty=5.0, speed=1.0)  # Dino'nun seçtiği B ayarı
IFADELER = {"mutlu", "nese", "gurur", "sevgi", "saskin", "utangac", "uzgun", "dusunce", "uykulu", "sinirli", "goz_kirp", "agla"}
# 4 Kas: seste duygu. Her duygunun kendi referansı (REF'in Praat ile tonlaması/temposu değiştirilmiş hâli, ses\test\uret_duygu.py);
# ifade etiketi hangisini kullanacağını seçer, listede olmayan ifade normal sesle (A) konuşur.
DUYGU_KLASOR = os.path.join(SES, "ornekler", "duygu")
SES_DUYGU = {"nese": "nese", "saskin": "saskin", "sevgi": "sevgi", "utangac": "sevgi", "uzgun": "uzgun", "agla": "uzgun",
             "uykulu": "uykulu", "sinirli": "sinirli"}
DENEME = 2                        # duygulu sesle en çok bu kadar deneme, tutmazsa bir kez normal sesle
YETER = 0.9                       # Whisper benzerliği bu kadarsa yeterli (kısa hitaplarda Whisper'ın kendi hatası tekrar yaptırmasın)
# 5 Kas: sözsüz sesler. Gerçek gülme/kıkırdama kayıtları (Bark üretti, Sakura tınısına çevrildi, Dino seçti:
# ses\test\bark_sesler.py). Beyin [kikir] / [gul] yazınca ya da "hehe", "ahaha" gibi gülme kelimesi yazınca XTTS okumaz,
# cümleden önce bu kayıtlardan biri çalar. Şaşırma/iç çekme/esneme kayıtları kötü çıktı (Dino), konmadı.
SOZSUZ_KLASOR = os.path.join(SES, "ornekler", "sozsuz", "sec")
SOZSUZ_BALON = {"kikir": "Hehe~", "gul": "Ahahaha~"}
GULME = re.compile(r"(?i)(?<![\wçğıöşü])[ae]?(?:h[aei]){2,}h?(?![\wçğıöşü])[!.,~…]*")
# 5 Kas: Dino'nun gülüşü. Sakura her cevabı bitirince bu kadar sn "Sakura" demeden gülme dinlenir (yalnız gülme kabul edilir).
GULME_PENCERE = 5.0
GULME_SOZ = re.compile(r"(?:[aeı]?h[aeıi][\s,.!]*){2,}|kah ?kah|öldüm|çok iyi|efsane|ahsj|asdf|komikmiş|çok komik")
# 5 Kas: ses tanıma (ses_izi.py). "Sakura sesimi öğren" / "Sakura Ali'nin sesini öğren"
SESIMI = re.compile(r"\bsesimi\s+(?:öğren|tanı|kaydet|ezberle)")
SESINI = re.compile(r"\b([a-zçğıöşü]+?)['’]?n?[ıiuü]n\s+sesini\s+(?:öğren|tanı|kaydet|ezberle)")
OGRENME_SURE = 20.0               # bu kadar sn konuşma toplanınca öğrenilir (en az 8 sn, en çok 60 sn beklenir)
DUYULAN = os.path.join(KOK, "duyulan")   # son 60 komutun sesi (ses tanıma eşiğini ayarlamak için), yalnız "Sakura" denenler
# Whisper'ın sessizlikte uydurduğu bilinen cümleler
UYDURMA = ("altyazı", "izlediğiniz için", "abone ol", "teşekkürler.", "m.k.")
# 8 Kas (gelişim): Whisper'a başlangıç metni — telefonda "bye bye" → "Billy", "Sakura" → "Fakura/Bakura" duyuluyordu
WHISPER_IPUCU = "Sakura, Dino, bye bye, hoşça kal, görüşürüz."
IPUCU_KELIME = ("sakura", "dino", "bye bye", "hoşça kal", "görüşürüz")
# Yalnız cümle başında, kelime sınırıyla: "Fakura'nın ..." → "Sakura'nın ...", "Sakur Aşağı" → "Sakura Aşağı"
SAKURA_BOZUK = re.compile(r"(?i)^(\W*)(?:fakura|bakura|sakur|sakara|zakura)\b")


def sakura_duzelt(metin):
    """Cümle başında Sakura'nın bilinen yanlış duyulmalarını 'Sakura' yapar (cümle içine dokunmaz)."""
    return SAKURA_BOZUK.sub(lambda m: m.group(1) + "Sakura", metin, count=1)


EKRAN_SORUSU = re.compile(r"ekran|bu ne|bu hata|görüyor musun|şuna bak|buna bak")
# 5 Kas: kamera (kamera.py)
KAMERA_SORUSU = re.compile(r"bana bak|beni gör|nasıl görünüyorum|yüzüme bak|kameradan bak|halime bak|neye benziyorum|elimde ne var")
YUZUMU = re.compile(r"\byüzümü\s+(?:öğren|tanı|kaydet|ezberle)")
YUZUNU = re.compile(r"\b([a-zçğıöşü]+?)['’]?n?[ıiuü]n\s+yüzünü\s+(?:öğren|tanı|kaydet|ezberle)")
YUZ_UNUT = re.compile(r"(?:son\s+)?öğrendiğin\s+yüzleri\s+unut")   # 8 Kas: kendi kendine öğrenilen son yüz kareleri
KAMERA_AC = re.compile(r"kamera(?:yı|n[ıi])?\s+(aç|kapat)")


def ilk_bol(p):
    """Cevabın ilk cümlesini ilk noktalama yerinden ikiye böler (8-45 harf arası; 30 harften kısaysa bölmez).
    5 Kas: gerçek akışlı seslendirme yerine — ses motoru kısa parçayı çabuk üretir, ilk ses ~0,5 sn erken başlar.
    Kelime ortasından/cümle ortasından bölmez: duraksama doğal yerde olsun."""
    if len(p) <= 30:
        return [p]
    for m in re.finditer(r"[,;:—]\s+", p):
        if 8 <= m.start() <= 45 and len(p) - m.end() >= 6:
            return [p[:m.start() + 1].strip(), p[m.end():].strip()]
    return [p]


def ekran_goruntusu():
    """Tüm ekranlar, en fazla 1600 px genişlikte JPEG (beyne gidecek, küçük olsun)."""
    import io
    from PIL import ImageGrab
    im = ImageGrab.grab(all_screens=True)
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)))
    b = io.BytesIO()
    im.convert("RGB").save(b, "JPEG", quality=80)
    return b.getvalue()


def tr_kucuk(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


def uyanma(metin):
    """Metin 'Sakura' ile başlıyorsa (ilk 3 kelimede) geri kalanını döndürür, yoksa None."""
    kel = re.findall(r"[a-zçğıöşüâîû']+", tr_kucuk(metin))
    for i, k in enumerate(kel[:3]):
        kok = k.split("'")[0]
        if kok.startswith("sakur") or difflib.SequenceMatcher(None, kok[:6], "sakura").ratio() >= 0.8:
            # Metnin orijinalinde o kelimeden sonrasını al (noktalama ve büyük harf korunur)
            m = re.search(r"(?i)" + re.escape(k.split("'")[0][:4]) + r"\S*[\s,.!?]*", metin)
            return metin[m.end():].strip() if m else " ".join(kel[i + 1:])
    return None


def temizle(metin):
    """Beyinden gelen cümleyi sese hazırlar: ifade etiketi, sözsüz ses (gülme), markdown, emoji, link ayıklanır.
    (ifade, sozsuz, metin) döner; sozsuz = "kikir" | "gul" | None."""
    ifade = sozsuz = None   # etiket yoksa cevabın önceki cümlesinin ifadesi sürer
    m = re.match(r"\s*\[(\w+)\]\s*", metin)
    if m and m.group(1) in IFADELER:
        ifade, metin = m.group(1), metin[m.end():]
    m = re.search(r"\[(kikir|gul)\]", metin)
    if m:
        sozsuz = m.group(1)
    # "hehe", "ahaha" XTTS'te kötü okunuyor: yazıdan çıkar, yerine gerçek gülme sesi çalsın
    for g in GULME.findall(metin):
        sozsuz = sozsuz or ("gul" if "a" in g.lower() else "kikir")
    metin = GULME.sub("", metin)
    metin = re.sub(r"\[[^\]]*\]", "", metin)
    metin = re.sub(r"https?://\S+", "", metin)
    metin = re.sub(r"[*_#`>|]", "", metin)  # "~" balonda kalır, sentez sırasında atılır
    metin = "".join(ch for ch in metin if ord(ch) < 0x2000 or ch in "…’‘“”–—")
    metin = " ".join(metin.split())
    metin = re.sub(r"\s+([,.!?~])", r"\1", metin)            # gülme silinince kalan " ," gibi boşluklar
    metin = re.sub(r"^[\s,.!?~…]+|[\s,]+$", "", metin)     # başta/sonda öksüz kalan noktalama
    if not re.search(r"[\wçğıöşü]", metin):
        metin = ""
    return ifade, sozsuz, metin


def gulme_mi(y, metin):
    """Dino gülüyor mu: Whisper gülme yazdıysa ya da hiçbir kelime duymadan ses ritmik patlamalardan (ha-ha-ha) oluşuyorsa."""
    k = tr_kucuk(metin or "").strip()
    if k:
        # gülme kelimeleri dışında en çok 3 kelime ("hahaha öldüm ya" evet, uzun cümle hayır)
        return bool(GULME_SOZ.search(k)) and len(GULME_SOZ.sub(" ", k).split()) <= 3
    if not 0.5 <= len(y) / SR <= 6:
        return False
    h = 256
    n = len(y) // h
    e = np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(1))
    e = np.convolve(e, np.ones(3) / 3, "same")
    tepe, son = [], -99
    for i in range(3, n - 3):
        if e[i] == e[i - 3:i + 4].max() and e[i] > 0.35 * e.max() and i - son >= 6:   # ≥ 96 ms aralıklı tepeler
            tepe.append(i); son = i
    # gülmede patlamaların arası derin çukurdur (nefes) ve ritim düzenlidir. Bu yol yalnız Whisper hiçbir şey
    # yazmadığında (ya da "izlediğiniz için..." uydurduğunda) kullanılır. Ölçüm: gülmelerin ~1/3'ü, konuşmanın ~%19'u.
    ara = np.array([b - a for a, b in zip(tepe, tepe[1:]) if e[a:b].min() < 0.25 * min(e[a], e[b])]) * h / SR
    if len(ara) < 3:
        return False
    return 0.1 <= np.median(ara) <= 0.4 and ara.std() / ara.mean() < 0.5


def bol(metin, en=180):
    """XTTS uzun cümlede bozulur: virgüllerden bölerek kısa parçalara ayır."""
    if len(metin) <= en:
        return [metin]
    out, cur = [], ""
    for p in re.split(r"(?<=[,;:])\s+", metin):
        if cur and len(cur) + len(p) > en:
            out.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        out.append(cur)
    return out


class Asistan:
    def __init__(self):
        t = time.time()
        self.asr = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo", device="cuda", compute_type="float16")
        self.vad = load_silero_vad()
        x = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cuda").synthesizer.tts_model
        self.sentez_kilit = threading.Lock()
        self.lat = {"A": x.get_conditioning_latents(audio_path=REF)}   # duygu → (gpt latent, konuşmacı)
        for d in set(SES_DUYGU.values()):
            r = [os.path.join(DUYGU_KLASOR, f"{d}_{os.path.basename(y)}") for y in REF]
            if all(map(os.path.exists, r)):
                self.lat[d] = x.get_conditioning_latents(audio_path=r)
        hizli_xtts.hizlandir(x)
        self.xtts = x
        self.izi = ses_izi.SesIzi(x)          # ses tanıma: XTTS'in konuşmacı kodlayıcısı
        self.ogrenme = None                   # ses öğretme sürüyorsa {ad, parca, bitis}
        self.gulme_bitis = 0.0                # bu ana kadar "Sakura" demeden gülme dinlenir
        self.son_kim = "Dino"
        self.beyin = Beyin(BEYIN_MODEL)
        self.soz_bitti = None                 # Dino'nun son sözünün bittiği an (gecikme ölçümü)
        self.olcum = None                     # 8 Kas: sürmekte olan sesli komutun aşama süreleri (yavaş cevabın nedeni)
        self.beyin_kilit = threading.Lock()
        self.konusuyor = False
        self.sustu = 0.0                      # son sesin bittiği an (yankıyı duymamak için)
        self.takip_bitis = 0.0
        self.soz_q = queue.Queue()            # (ifade, metin) | None = cevap bitti
        self.cal_q = queue.Queue()
        self.komut_q = queue.Queue()
        # sadece "Sakura" denince: tatlı, her seferinde farklı bir cevap (balon metni, ifade, ses)
        self.cagri = [(m, f, self.hazir_ses(m)) for m, f in
                      [("Hıı? Buyur tatlım~", "nese"), ("Efendim canım?", "mutlu"), ("Dinliyorum balım~", "sevgi"),
                       ("Buradayım yavrum!", "nese"), ("Söyle bir tanem~", "sevgi"), ("Efendim şekerim?", "mutlu")]]
        # Dino değilse (ses tanıma): hitapsız
        self.cagri_yabanci = [(m, f, self.hazir_ses(m)) for m, f in [("Efendim?", "mutlu"), ("Buyur, dinliyorum.", "mutlu")]]
        self.bakiyor = [(m, self.hazir_ses(m)) for m in
                        ["Hemen bakıyorum balım~", "Bir saniye tatlım, bakıyorum~", "Hemen bakıyorum canım~", "Hmm, bakıyorum yavrum~"]]
        # komutu duyduğu an çalan kısa, yumuşak iki notalı "bip" (cevap birkaç sn sonra gelse de duyduğu belli olsun)
        t_ = np.arange(int(24000 * 0.07)) / 24000
        nota = lambda f: np.sin(2 * np.pi * f * t_) * np.hanning(len(t_))
        self.bip = (0.22 * np.concatenate([nota(880), nota(1320)])).astype(np.float32)
        # gülme kayıtları: ses yüksekliği Sakura'nın konuşmasına eşitlenir
        hedef = float(np.median([np.sqrt(np.mean(w ** 2)) for _, _, w in self.cagri]))
        self.sozsuz, self.son_sozsuz = {}, {}
        for k in SOZSUZ_BALON:
            for yol in sorted(glob.glob(os.path.join(SOZSUZ_KLASOR, k + "_*.wav"))):
                y, r = sf.read(yol, dtype="float32")
                if r != 24000:
                    y = resample_poly(y, 24000, r).astype(np.float32)
                y = y * hedef / max(np.sqrt(np.mean(y ** 2)), 1e-6)
                self.sozsuz.setdefault(k, []).append((y / max(1.0, np.abs(y).max() / 0.95)).astype(np.float32))
        log.info("sözsüz sesler: %s", {k: len(v) for k, v in self.sozsuz.items()})
        threading.Thread(target=self._sentez_dongu, daemon=True).start()
        threading.Thread(target=self._cal_dongu, daemon=True).start()
        threading.Thread(target=self._komut_dongu, daemon=True).start()
        threading.Thread(target=self._isit, daemon=True).start()
        log.info("hazır (%.0f sn)", time.time() - t)

    # ---------- ses ----------
    def sentez(self, metin, duygu="A"):
        metin = telaffuz.duzelt(metin).strip()   # sayılar ve sözlük: yalnız ses, balon metni değişmez
        # kilit: XTTS'in CUDA Graph tamponları ortak; sesli cevap ile Telegram sesli mesajı aynı anda üretmesin
        with self.sentez_kilit, torch.inference_mode():
            return np.asarray(self.xtts.inference(metin, "tr", *self.lat.get(duygu, self.lat["A"]), **B_AYAR)["wav"], dtype=np.float32)

    def dogruluk(self, y, metin, beam=5):
        """Whisper sesi ne kadar doğru duyuyor: kelime dizilerinin benzerliği (1 = birebir)."""
        kelime = lambda s: re.sub(r"[^\wçğıöşü ]", " ", telaffuz.sayilar(s).replace("I", "ı").replace("İ", "i").lower()).split()
        seg, _ = self.asr.transcribe(resample_poly(y, 2, 3).astype(np.float32), language="tr", beam_size=beam,
                                     condition_on_previous_text=False, without_timestamps=True)
        return difflib.SequenceMatcher(None, kelime(metin), kelime(" ".join(s.text for s in seg))).ratio()

    def dogru_ses(self, metin, duygu="A", kontrol=True, en_cok=None):
        """Kendini dinleyerek konuşur: cümle Whisper'da yanlış çıkarsa yeniden üretilir; duygulu ses tutmazsa normal ses
        denenir. Önceki cümle çalarken yapıldığı için çoğu zaman gecikme olmaz. En doğru deneme verilir.
        Kontrol ~0,5 sn sürüyor: cevabın ilk parçasında yapılmaz (Dino anında cevap istiyor)."""
        if not kontrol:
            return self.sentez(metin, duygu)
        sira = ([duygu] * DENEME + (["A"] if duygu != "A" else []))[:en_cok]   # en_cok: telefonda hız için az deneme
        en, en_oran = None, -1
        for i, d in enumerate(sira):
            y = self.sentez(metin, d)
            oran = self.dogruluk(y, metin, beam=1)
            if oran > en_oran:
                en, en_oran = y, oran
            if oran >= YETER:
                break
        if i:
            log.info("kendini düzeltti (%d deneme, %s, doğruluk %.2f): %s", i + 1, d, en_oran, metin)
        return en

    def hazir_ses(self, metin, deneme=8):
        """Hazır cümle: birkaç kez okunur, Whisper'ın tam doğru duyduğu kayıt hazir_ses\\ içine saklanır (ses/ayar değişince yenilenir)."""
        anahtar = hashlib.md5(repr((telaffuz.duzelt(metin), REF, B_AYAR)).encode()).hexdigest()[:12]
        yol = os.path.join(KOK, "hazir_ses", anahtar + ".npy")
        if os.path.exists(yol):
            return np.load(yol)
        en, en_oran = None, -1
        for _ in range(deneme):
            y = self.sentez(metin)
            oran = self.dogruluk(y, metin)
            if oran > en_oran:
                en, en_oran = y, oran
            if oran == 1:
                break
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        np.save(yol, en)
        log.info("hazır ses: %s (doğruluk %.2f)", metin, en_oran)
        return en

    def _sentez_dongu(self):
        ilk = True
        while True:
            is_ = self.soz_q.get()
            if is_ is None:
                self.cal_q.put(None)
                ilk = True
                continue
            ifade, sozsuz, metin = is_
            if sozsuz in self.sozsuz:
                # bir öncekiyle aynı kayıt üst üste çalmasın
                adaylar = [i for i in range(len(self.sozsuz[sozsuz])) if i != self.son_sozsuz.get(sozsuz)] or [0]
                i = self.son_sozsuz[sozsuz] = random.choice(adaylar)
                self.cal_q.put(("nese", SOZSUZ_BALON[sozsuz], self.sozsuz[sozsuz][i]))
            if not metin:
                continue
            parcalar = bol(metin)
            if ilk:   # cevabın ilk parçası kısa: daha çabuk üretilir, Sakura daha erken konuşmaya başlar
                parcalar[:1] = ilk_bol(parcalar[0])
            for j, p in enumerate(parcalar):
                try:
                    t0 = time.monotonic()
                    wav = self.dogru_ses(p, SES_DUYGU.get(ifade, "A"), kontrol=not (ilk and j == 0))
                    o = self.olcum
                    if ilk and j == 0 and o is not None and "tts" not in o:
                        o["tts"] = time.monotonic() - t0
                    self.cal_q.put((ifade, p, wav))
                except Exception as e:
                    log.info("sentez hatası: %s", e)
            ilk = False   # cevabın yalnız ilk parçası kontrolsüz çalar

    def _cal_dongu(self):
        son = ""
        while True:
            is_ = self.cal_q.get()
            if is_ is None:
                # yalnızca son cümle soruysa cevabı beklenir; yoksa yeniden "Sakura" demek gerekir
                # (aksi halde odadaki her konuşma bir sonraki komut sanılıp zincirleme dinleme açık kalıyordu)
                self.takip_bitis = time.time() + TAKIP if son.rstrip(" ~").endswith("?") else 0
                self.gulme_bitis = time.time() + GULME_PENCERE
                continue
            ifade, metin, wav = is_
            son = metin
            if self.soz_bitti:
                log.info("cevap gecikmesi %.1f sn (sözün bitişinden sesin başlamasına)", time.time() - self.soz_bitti)
                self.soz_bitti = None
                self._yavas_mi()
            self.cal(wav, metin, ifade)

    def cal(self, wav, metin, ifade="mutlu"):
        self.konusuyor = True
        try:
            sakura_ui.gonder("konusuyor", metin, ifade, len(wav) / 24000)
            sd.play(wav * gorevler.GECE_SES if gorevler.gece() else wav, 24000)   # 5 Kas: gece modu kısık ses
            sd.wait()
        finally:
            self.konusuyor = False
            self.sustu = time.time()

    # ---------- düşünme ----------
    def _isit(self):
        # önceki açılıştan özetlenmemiş konuşma kaldıysa önce hafızaya işlenir, sonra beyin ısınırken onu okur
        hafiza.isle()
        # beyin ilk açılışta ~10 sn sürüyor: önceden ısıt, hafızayı okusun
        with self.beyin_kilit:
            hafiza.kacirilan("ses")   # bundan sonra Telegram'da konuşulanlar ses beynine not olarak gider
            for _ in self.beyin.sor("(Sistem: Sakura asistanı yeni açıldı. HAFIZA.md'yi ve GUNLUK.md'yi oku. Cevap olarak sadece 'hazır' yaz.)"):
                pass
        threading.Thread(target=hafiza.dongu, daemon=True).start()

    def _komut_dongu(self):
        while True:
            komut, kim = self.komut_q.get()
            t = time.time()
            sakura_ui.gonder("dusunuyor", "💭 …", "dusunce")
            ilk, dolgu = True, False
            soylenen, dino_dedi, son_ifade = [], komut, "mutlu"
            kim_ad = "Tanımadığım biri" if kim == "?" else (kim or "Dino")
            if kim == "sistem":
                kim_ad = "Sistem"   # kamera olayı: "(Kamera: ...)" notu, kimse konuşmadı
            elif kim_ad != "Dino":
                komut = f"[konuşan: {kim_ad}] {komut}"   # ses tanıma: Dino değil (beyin\CLAUDE.md "Kim konuşuyor")
            # kamera: "bana bak" → kameradan kare; ekranla ilgili soru → ekran görüntüsü (beyin araç çalıştırmadan bakar)
            resim = None
            kam = getattr(self, "kamera", None)
            if kim != "sistem" and kam and KAMERA_SORUSU.search(tr_kucuk(komut)):
                resim = kam.foto()
                komut += (" (Kameradan şu an çekilen kare ekte: Dino'yu (ya da konuşanı) görüyorsun, buna bakarak cevap ver.)"
                          if resim else " (Kamera şu an kapalı, göremiyorsun; söyle.)")
            elif kim != "sistem" and EKRAN_SORUSU.search(tr_kucuk(komut)):
                resim = ekran_goruntusu()
                komut += " (Ekran görüntüsü ekte; araç kullanmadan buna bakarak cevap ver.)"
            o = self.olcum if kim != "sistem" else None
            with self.beyin_kilit:
                if gorevler.gece() and kim != "sistem":
                    komut = f"(Gece {time.strftime('%H:%M')}: kısık sesle konuşuyorsun, kısa ve sakin cevap ver.) " + komut
                komut = hafiza.kacirilan("ses") + komut   # Telegram'da (sonnet beyin) konuşulanlar
                if o is not None:
                    o["bekleme"] = time.monotonic() - o["kuyruk"]   # kuyruk + beyin kilidi + ekran/kamera karesi
                    b = self.beyin
                    o["tazelendi"] = b.p is None or b.p.poll() is not None or b.tur == 0   # yeni süreç (tazeleme/çökme)
                    o["soru"] = b.tur
                    o["sor"] = time.monotonic()
                for tur, x in self.beyin.sor(komut, resim):
                    if o is not None and "beyin" not in o and (tur == "arac" or (tur == "cumle" and x.strip())):
                        o["beyin"] = time.monotonic() - o["sor"]
                        o["arac"] = tur == "arac"
                    if tur == "cumle":
                        ifade, sozsuz, metin = temizle(x)
                        ifade = son_ifade = ifade or son_ifade
                        if dolgu and re.match(r"(hemen |bir saniye\S* |hmm\S* )?bak(ıyorum|ayım)", tr_kucuk(metin)):
                            continue  # "Hemen bakıyorum" zaten hazır sesle söylendi
                        if metin or sozsuz:
                            if ilk:
                                log.info("ilk cümle %.1f sn", time.time() - t)
                                ilk = False
                            log.info("sakura: %s%s", f"[{sozsuz}] " if sozsuz else "", metin)
                            soylenen.append((f"({'kıkırdadı' if sozsuz == 'kikir' else 'güldü'}) " if sozsuz else "") + metin)
                            self.soz_q.put((ifade, sozsuz, metin))
                    elif tur == "arac":
                        log.info("araç: %s", x)
                        if ilk and not dolgu:
                            # beyin bir şeye bakmaya gitti ama henüz konuşmadı: bekletmeden hazır cümleyi söyle
                            m, wav = random.choice(self.bakiyor)
                            self.cal_q.put(("dusunce", m, wav))
                            dolgu = True
                        elif not self.konusuyor and self.soz_q.empty() and self.cal_q.empty():
                            sakura_ui.gonder("dusunuyor", "🔎 Bakıyorum…", "dusunce")
            self.soz_q.put(None)
            hafiza.kaydet(dino_dedi, " ".join(soylenen), kim_ad)

    # ---------- dinleme ----------
    def yazi(self, y):
        seg, _ = self.asr.transcribe(y, language="tr", beam_size=1, condition_on_previous_text=False, without_timestamps=True,
                                     initial_prompt=WHISPER_IPUCU)
        seg = list(seg)
        if not seg or all(s.no_speech_prob > 0.6 for s in seg):
            return ""
        metin = " ".join(s.text.strip() for s in seg).strip()
        k = tr_kucuk(metin)
        if k.startswith(UYDURMA) or sum(w in k for w in IPUCU_KELIME) >= 4:   # ipucu metnini aynen geri okuduysa uydurma
            return ""
        return sakura_duzelt(metin)

    def konusma_geldi(self, y, basladi):
        if len(y) < SR * 0.35:
            return
        t, tm = time.time(), time.monotonic()
        if self.ogrenme:
            self._ogrenme_parca(y)   # ses öğretme sürüyor: söylenen her şey toplanır
            return
        metin = self.yazi(y)
        t_whisper = time.monotonic() - tm
        # Sakura'nın cevabından hemen sonra gülme: "Sakura" demeden de duyulur, beyne gitmez
        if basladi < self.gulme_bitis and (not metin or uyanma(metin) is None) and gulme_mi(y, metin):
            self.gulme_bitis = 0
            self.guldu(metin)
            return
        if not metin:
            return
        takipte = basladi < self.takip_bitis  # konuşma takip süresi içinde BAŞLADIYSA
        komut = uyanma(metin)
        if komut is None and not takipte:
            return  # Sakura'ya söylenmedi: hiçbir şey kaydedilmez
        if komut is None:
            komut = metin
        t_ = time.monotonic()
        kim, skor = self.izi.kim(y)
        t_tanima = time.monotonic() - t_
        log.info("duydum (%.2f sn): %s | konuşan: %s %s", time.time() - t, metin, kim,
                 {k: round(v, 2) for k, v in skor.items()})
        self._sakla(y, kim, skor)
        if kim:
            self.son_kim = kim
        k = tr_kucuk(komut)
        m = SESIMI.search(k) or SESINI.search(k)
        if m:
            self._ogrenme_basla(m.group(1).capitalize() if m.re is SESINI else "Dino", kim)
            return
        kam = getattr(self, "kamera", None)
        m = YUZUMU.search(k) or YUZUNU.search(k)
        if m and kam:
            ad = m.group(1).capitalize() if m.re is YUZUNU else "Dino"
            if "Dino" in kam.kisiler and kim not in ("Dino", None):
                self._soyle("Sen Dino değilsin ki! Yüz öğretmeyi sadece Dino yapabilir~", "sinirli")
                return
            # 8 Kas: açılı öğretme (~25 sn, Sakura yönlendirir), kareler galeriye ayrı ayrı eklenir
            self._soyle("Tamam! Seni her açıdan ezberleyeceğim, dediklerimi yap~" if ad == "Dino" else
                        f"Tamam {ad}! Seni her açıdan ezberleyeceğim, dediklerimi yap~")
            def bekle():
                time.sleep(0.3)
                while self.konusuyor or not self.soz_q.empty() or not self.cal_q.empty():
                    time.sleep(0.1)
            def soyle(metin):
                self._soyle(metin, "nese")
                bekle()
            def ogret():
                bekle()
                n = kam.ogren_aci(ad, soyle)
                self._soyle(("Yüzünü ezberledim! Artık seni görünce tanırım~" if ad == "Dino" else
                             f"Tamamdır, {ad}'in yüzünü ezberledim~") if n else
                            "Yüzünü tam göremedim, kamera açık mı? Sonra tekrar deneyelim~", "nese" if n else "uzgun")
            threading.Thread(target=ogret, daemon=True).start()
            return
        if kam and YUZ_UNUT.search(k):
            if kim not in ("Dino", None):
                self._soyle("Bunu sadece Dino yapabilir~", "sinirli")
                return
            n = kam.unut_son("Dino")
            self._soyle(f"Tamam, son bir günde kendi kendime öğrendiğim {n} yüz karesini unuttum~" if n else
                        "Son bir günde kendi kendime yeni bir şey öğrenmemiştim zaten~")
            return
        m = KAMERA_AC.search(k)
        if m and kam:
            ac = m.group(1).startswith("aç")
            kam.ayarla(ac)
            self._soyle("Kamera açık, seni görüyorum~" if ac else "Kamerayı kapattım, artık görmüyorum~")
            return
        # 5 Kas: ses tek başına emin değilse kameraya bak: Dino'nun yanında/yerinde başka bir yüz varsa ve ses kesin Dino
        # değilse konuşan o kişi sayılır (Dino'nun arkadaşına "canım" demesin). Kamera kimseyi görmüyorsa ses kararı kalır.
        # 16:17 dersi: kamera tek bir tanınmayan yüz görünce (Dino'nun kendi yüzü yandan/karanlıkta "?" çıkabiliyor) Dino'nun
        # 0,77'lik sesi yabancı sayıldı. Artık: tanıdık başka biri (Ali) ya da Dino'nun YANINDA ikinci bir yüz → KESIN;
        # yalnız tek tanınmayan yüz → ses ancak çok zayıfsa (ZAYIF) yabancı.
        goren = kam.su_an() if kam else None
        # 6 Kas 17:42 dersi: Dino başını çevirince yüzü "?" (0,29-0,35) çıkıyor, kısa "Sakura!" sesi de 0,6 → yabancı sanıldı.
        # Kamera Dino'yu son DINO_YAKIN sn içinde gördüyse tek "?" yüz büyük ihtimalle yine Dino'dur.
        dino_s = skor.get("Dino", 0)
        tanidik = [g for g in goren or [] if g not in ("Dino", "?", None)]
        if kim == "Dino" and goren and ((tanidik and dino_s < ses_izi.KESIN) or
                                        ("Dino" in goren and "?" in goren and dino_s < ses_izi.KESIN) or
                                        (goren == ["?"] and dino_s < ses_izi.ZAYIF and
                                         time.time() - kam.son_dino > DINO_YAKIN)):
            kim = tanidik[0] if tanidik else "?"
            log.info("kamera başka birini görüyor %s, ses kesin değil → konuşan: %s", goren, kim)
            self.son_kim = kim
        # 6 Kas (Dino sabahtan beri "yalancı, kalk lan" yedi): kamera ofiste/loşta Dino'yu "?" sanıp beyne "tanımadığın biri var"
        # dedi, haiku da sonra Dino'nun sesine inanmadı. Artık: (1) kamera yalnız Dino'yu görüyorsa zayıf ses de Dino;
        # (2) ses net Dino ise kamera bir süre tek tanınmayan yüzü Dino sayar; (3) yakında "yabancı" kamera notu gittiyse
        # beyne bir kez "o not yanlıştı" düzeltmesi eklenir.
        if kim == "?" and goren == ["Dino"]:
            kim = "Dino"
            log.info("ses zayıf ama kamera yalnız Dino'yu görüyor → konuşan: Dino")
            self.son_kim = kim
        if kam and kim == "Dino" and (dino_s >= ses_izi.ZAYIF or goren == ["Dino"]):
            kam.ses_dino(kesin=dino_s >= ses_izi.KESIN and goren is not None and len(goren) <= 1)
            y_t = kam.son_olay.get("yabanci", 0)
            if y_t and time.time() - y_t < 60 * 60 and getattr(kam, "yabanci_duzeldi", 0) != y_t:
                kam.yabanci_duzeldi = y_t
                komut = ("(Sistem: ses tanıma şu an konuşanın DİNO olduğunu doğruladı. Az önceki 'başında tanımadığın biri var' "
                         "kamera notu YANLIŞTI, kamera ışık yüzünden Dino'yu tanıyamadı; o kişi de Dino'ydu. Dino'ya inan, "
                         "sevgilin gibi normal konuş.) " + komut)
                log.info("kamera yabancı notu düzeltildi (ses Dino %.2f)", dino_s)
        gor = getattr(self, "gorevler", None)
        if gor and kim in ("Dino", None):
            komut = gor.odak_komut(k) + komut   # "çalışıyorum" → odak modu
        if not komut.strip(" .,!?"):
            m, f, wav = random.choice(self.cagri if kim in (None, "Dino") else self.cagri_yabanci)
            self.cal(wav, m, f)
            self.takip_bitis = time.time() + TAKIP
            return
        self.takip_bitis = 0
        self.soz_bitti = t - SESSIZLIK_SONU
        self.olcum = {"bitis": tm - SESSIZLIK_SONU, "whisper": t_whisper, "tanima": t_tanima,
                      "diger": time.monotonic() - tm - t_whisper - t_tanima, "kuyruk": time.monotonic()}
        sd.play(self.bip, 24000)
        self.sustu = time.time() + 0.2  # kendi bip'ini duymasın
        self.komut_q.put((komut, kim))

    def _yavas_mi(self):
        """8 Kas (Dino onayladı): sözün bitişinden ilk sese YAVAS_ESIK sn'yi geçtiyse hangi aşamanın uzadığı tek satır günlüğe
        yazılır (davranış değişmez). "kalan" = sessizlik bekleme (SESSIZLIK_SONU) + ölçülmeyen aralar."""
        o, self.olcum = self.olcum, None
        if not o:
            return
        top = time.monotonic() - o["bitis"]
        if top <= YAVAS_ESIK:
            return
        parca = ["whisper", "tanima", "diger", "bekleme", "beyin", "tts"]
        kalan = top - sum(o.get(k, 0) for k in parca)
        log.info("yavaş (%.1f sn): %s kalan %.1f (beyin tazelendi mi: %s, soru %s%s)", top,
                 " ".join(f"{k.replace('tanima', 'tanıma').replace('diger', 'diğer')} {o[k]:.1f}" for k in parca if k in o),
                 kalan, "evet" if o.get("tazelendi") else "hayır", o.get("soru", "?"),
                 ", önce araç → hazır ses" if o.get("arac") else "")

    # ---------- gülme ve ses tanıma ----------
    def guldu(self, metin):
        """Dino Sakura'nın esprisine güldü: günlüğe yazılır (hafıza 'tutan espriler'i öğrenir), Sakura da kıkırdar."""
        log.info("Dino güldü: %s", metin or "(sesten)")
        hafiza.olay(self.son_kim if self.son_kim != "?" else "Dino", "(güldü)")
        if self.sozsuz.get("kikir") and random.random() < 0.7 and self.soz_q.empty() and self.cal_q.empty():
            self.cal(random.choice(self.sozsuz["kikir"]), "Hehe~", "nese")

    def _sakla(self, y, kim, skor):
        try:
            os.makedirs(DUYULAN, exist_ok=True)
            en = max(skor.values()) if skor else 0
            sf.write(os.path.join(DUYULAN, f"{time.strftime('%m%d_%H%M%S')}_{ {'?': 'bilinmeyen', None: 'yok'}.get(kim, kim) }_{en:.2f}.wav"), y, SR)
            for eski in sorted(glob.glob(os.path.join(DUYULAN, "*.wav")))[:-60]:
                os.remove(eski)
        except Exception as e:
            log.info("duyulan kaydı: %s", e)

    def _soyle(self, metin, ifade="nese"):
        """Beyne sormadan kısa bir cümle söyler."""
        self.soz_q.put((ifade, None, metin))
        self.soz_q.put(None)

    def _ogrenme_basla(self, ad, kim):
        if "Dino" in self.izi.kisiler and kim not in ("Dino", None):
            self._soyle("Sen Dino değilsin ki! Ses öğretmeyi sadece Dino yapabilir~", "sinirli")
            return
        self.ogrenme = dict(ad=ad, parca=[], bitis=time.time() + 60)
        log.info("ses öğrenme başladı: %s", ad)
        if ad == "Dino":
            self._soyle("Tamam! Şimdi yirmi saniye kadar bana bir şeyler anlat, ne istersen~")
        else:
            self._soyle(f"Tamam! {ad}, şimdi yirmi saniye kadar konuş bakalım, sesini öğreneyim~")
        threading.Timer(65, self._ogrenme_bitir, args=(self.ogrenme,)).start()

    def _ogrenme_parca(self, y):
        o = self.ogrenme
        o["parca"].append(y)
        sure = sum(map(len, o["parca"])) / SR
        sakura_ui.gonder("dusunuyor", f"🎙️ Sesini öğreniyorum… %{min(100, round(100 * sure / OGRENME_SURE))}", "dusunce")
        if sure >= OGRENME_SURE or time.time() > o["bitis"]:
            self._ogrenme_bitir(o)

    def _ogrenme_bitir(self, o):
        if self.ogrenme is not o:
            return   # zaten bitti
        self.ogrenme = None
        sure = sum(map(len, o["parca"])) / SR
        if sure < 8:
            log.info("ses öğrenme: yetersiz (%.0f sn)", sure)
            self._soyle("Yeterince duyamadım, sonra tekrar deneyelim~", "uzgun")
            return
        self.izi.ogret(o["ad"], o["parca"])
        self._soyle("Tamamdır, sesini ezberledim! Artık seni her yerde tanırım~" if o["ad"] == "Dino"
                    else f"Tamamdır, {o['ad']}, sesini ezberledim! Artık seni tanırım~")

    def dinle(self, kaynak):
        """kaynak: 512 örneklik float32 parçalar üreten bir yineleyici."""
        once = collections.deque(maxlen=10)  # konuşma başlamadan önceki 0,3 sn
        cur, ses_yok, aktif = [], 0, False
        for p in kaynak:
            if self.konusuyor or time.time() - self.sustu < 0.4:
                # Sakura konuşurken kendi sesini duymasın
                if aktif or cur:
                    cur, aktif = [], False
                self.vad.reset_states()
                once.clear()
                continue
            olas = self.vad(torch.from_numpy(p), SR).item()
            if not aktif:
                once.append(p)
                if olas > 0.5:
                    aktif, cur, ses_yok = True, list(once), 0
                    basladi = time.time() - len(cur) * PARCA / SR
                continue
            cur.append(p)
            ses_yok = ses_yok + 1 if olas < 0.35 else 0
            if ses_yok * PARCA / SR >= SESSIZLIK_SONU or len(cur) * PARCA / SR > 25:
                y = np.concatenate(cur)
                aktif, cur = False, []
                once.clear()
                self.vad.reset_states()
                try:
                    self.konusma_geldi(y, basladi)
                except Exception as e:
                    log.exception("dinleme hatası: %s", e)


def _wts_kilitli():
    """8 Kas: Windows oturum bilgisi (WTSSessionInfoEx → SessionFlags: 0 kilitli, 1 açık). Okunamazsa None.
    Eski yöntem (girdi masaüstü) Win11 kilit ekranında 1-5 sn sonra yine "Default" görüyordu → kilit açıldı sanılıyordu."""
    from ctypes import wintypes
    w = ctypes.windll.wtsapi32
    buf, n = ctypes.c_void_p(), wintypes.DWORD()
    if not w.WTSQuerySessionInformationW(None, -1, 25, ctypes.byref(buf), ctypes.byref(n)):
        return None
    try:
        d = ctypes.cast(buf, ctypes.POINTER(ctypes.c_int32 * 6)).contents   # Level, (hizalama), SessionId, State, Flags
        return {0: True, 1: False}.get(d[4])
    finally:
        w.WTSFreeMemory(buf)


def kilitli():
    """Windows kilit ekranındaysa True. Önce oturum bilgisi (_wts_kilitli), okunamazsa eski yol:
    girdi masaüstü "Default" değildir (Winlogon) ya da hiç açılamaz."""
    try:
        k = _wts_kilitli()
        if k is not None:
            return k
    except Exception:
        pass
    u = ctypes.windll.user32
    h = u.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
    if not h:
        return True
    try:
        ad = ctypes.create_unicode_buffer(64)
        u.GetUserObjectInformationW(h, 2, ad, ctypes.sizeof(ad), None)  # UOI_NAME
        return ad.value.lower() != "default"
    finally:
        u.CloseDesktop(h)


def mikrofon():
    """Dino bilgisayarı kilitleyince (dışarı çıkınca) mikrofon tamamen kapanır, kilit açılınca yeniden açılır."""
    q = queue.Queue()
    def cb(indata, frames, t, status):
        q.put(indata[:, 0].copy())
    while True:
        if kilitli():
            log.info("kilit ekranı: mikrofon kapandı")
            while kilitli():
                time.sleep(1)
            log.info("kilit açıldı: mikrofon açıldı")
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=PARCA, callback=cb):
            son = time.time()
            while True:
                yield q.get()
                if time.time() - son > 0.5:
                    son = time.time()
                    if kilitli():
                        break
        while not q.empty():
            q.get_nowait()


def dosyadan(yol, bekle=0.0):
    """Test: dosyayı gerçek zamanlı hızda mikrofon gibi verir (önce `bekle` sn sessizlik)."""
    import librosa
    y, _ = librosa.load(yol, sr=SR)
    y = np.concatenate([np.zeros(int(SR * (0.5 + bekle)), np.float32), y, np.zeros(SR * 2, np.float32)])
    for i in range(0, len(y) - PARCA, PARCA):
        time.sleep(PARCA / SR)
        yield y[i:i + PARCA]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dosya", nargs="*")
    a = ap.parse_args()
    try:
        # aynı anda iki asistan çalışmasın; dinlemesi de masaüstü Sakura'nın bekçisine "çalışıyorum" demek
        tek = socket.socket(); tek.bind(("127.0.0.1", 47621)); tek.listen(4)
    except OSError:
        sys.exit("zaten çalışıyor")
    # 5 Kas: bekçinin yoklamaları kabul edilip kapatılır. Eskiden hiç kabul edilmiyordu: sıra (4) dolunca bekçi asistanı
    # kapalı sanıp 3 dk'da bir yeni kopya açıyordu (kopya hemen çıkıyordu ama asistan.out'u siliyor, tünel bırakıyordu).
    def _yoklama():
        while True:
            try:
                tek.accept()[0].close()
            except OSError:
                time.sleep(1)
    threading.Thread(target=_yoklama, daemon=True).start()
    hizli.hizlandir()
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # ekran görüntüsü ölçekli ekranda da tam çıksın
    asistan = Asistan()
    if a.dosya:
        bosta = lambda: asistan.komut_q.empty() and asistan.soz_q.empty() and asistan.cal_q.empty() and not asistan.konusuyor and not asistan.beyin_kilit.locked()
        for yol in a.dosya:
            bekle = 0.0
            if yol.startswith("+"):  # "+10:dosya.wav" → önce 10 sn sessizlik
                bekle, yol = float(yol[1:].split(":", 1)[0]), yol.split(":", 1)[1]
            time.sleep(1)
            while not bosta():
                time.sleep(0.2)
            log.info("--- test dosyası: %s", os.path.basename(yol))
            asistan.dinle(dosyadan(yol, bekle))
        time.sleep(1)
        while not bosta():
            time.sleep(0.5)
        time.sleep(1)
    else:
        import telegram_kopru   # 5 Kas: Dino dışarıdayken Telegram'dan (anahtar yoksa bekler, hiçbir şey yapmaz)
        asistan.telegram = telegram_kopru.Kopru(asistan, temizle, ekran_goruntusu, kilitli, bol, SES_DUYGU, TELEGRAM_MODEL)
        asistan.ilk_bol = ilk_bol
        try:   # "Sakura'yı Ara": Telegram içinde arama ekranı (cloudflared tüneli)
            import arama
            asistan.arama = arama.Arama(asistan, asistan.telegram, temizle, bol, SES_DUYGU)
        except Exception as e:
            log.exception("arama başlatılamadı: %s", e)
        try:   # 5 Kas: gece modu + odak koçu (gorevler.py), iş avcısı (is_avcisi.py)
            asistan.gorevler = gorevler.Gorevler(asistan, kilitli)
            threading.Thread(target=asistan.gorevler.dongu, daemon=True).start()
            import is_avcisi
            threading.Thread(target=is_avcisi.dongu, args=(asistan,), daemon=True).start()
            import gelisim   # 8 Kas: haftalık onaylı gelişim önerileri (Pazar 20:00, Telegram ✅/❌)
            threading.Thread(target=gelisim.dongu, args=(asistan,), daemon=True).start()
        except Exception as e:
            log.exception("görevler başlatılamadı: %s", e)
        try:   # 5 Kas: kamera (yüz tanıma, telefon, "bana bak")
            import kamera
            asistan.kamera = kamera.Kamera(asistan, kilitli)
        except Exception as e:
            log.exception("kamera başlatılamadı: %s", e)
        try:   # 8 Kas: sağlık bekçisi (bozulunca Telegram'a "🔧 Düzelt" düğmesiyle haber)
            import saglik
            asistan.saglik = saglik.Saglik(asistan)
        except Exception as e:
            log.info("sağlık bekçisi başlatılamadı: %s", e)
        sakura_ui.gonder("konusuyor", "Kulağım açık tatlım~ \"Sakura\" demen yeter!", "nese", 2.5)
        while True:
            try:
                asistan.dinle(mikrofon())
            except Exception as e:
                log.exception("mikrofon hatası: %s", e)
                time.sleep(3)
