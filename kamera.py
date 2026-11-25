# Sakura'nın gözü (5 Kas 2026, Dino istedi): bilgisayarın kamerası (ACER HD) ile
#  - yüz tanıma: Dino mu, Ali mi, tanımadığı biri mi (OpenCV YuNet yüz bulma + SFace yüz izi, Apache-2.0, kamera_model\)
#  - telefon: Dino elinde telefonla oynarsa (NanoDet, COCO "cell phone") arada bir kıskanç bir laf atar
#  - "Sakura bana bak": kameradan bir kare beyne gider (Claude'a; başka hiçbir yere kaydedilmez)
#  - "Sakura yüzümü öğren" / "Sakura Ali'nin yüzünü öğren": ~6 sn kameraya bak → yuz_izi\<ad>.npy
# Kamera yalnız açıkken çalışır: kamera_kapali.flag varsa ya da Windows kilitliyse kamera bırakılır (ışığı söner).
# Hiçbir görüntü diske yazılmaz. Olaylar beyne "(Kamera: ...)" notu olarak gider, Sakura sesle tepki verir.
import os, re, json, time, glob, logging, threading
import numpy as np, cv2

KOK = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(KOK, "kamera_model")
YUZ_IZI = os.path.join(KOK, "yuz_izi")
KAPALI = os.path.join(KOK, "kamera_kapali.flag")
ARALIK = 2.0            # sn: kaç saniyede bir bakılır
YUZ_ESIK = 0.40         # SFace kosinüs (OpenCV önerisi 0,363); üstü = o kişi
TELEFON = 67            # COCO sınıfı: cell phone
TELEFON_ESIK = 0.40
TELEFON_SURE = 4        # son 5 bakışın en az bu kadarında telefon varsa "telefonla oynuyor"
TELEFON_ARA = 15 * 60   # sn: telefon lafı en sık bu kadar arayla
DONUS = 5 * 60          # sn: bu kadar yokken gelirse karşılar
DONUS_ARA = 30 * 60
YABANCI_ARA = 30 * 60
# 5 Kas bekçi (Dino istedi): Dino en az BEKCI_YOK sn görünmezken başkası art arda 3 bakışta (~6 sn) görülürse
# Telegram'a haber + o anki kare (diske yazılmaz). En sık BEKCI_ARA'da bir.
BEKCI_YOK = 120
BEKCI_ARA = 10 * 60


def yokluk_suresi(sn):
    """8 Kas gelişim: '819 dakikadır' yerine 'yaklaşık 14 saattir' (kimse dakikayla konuşmaz); <60 dk aynen.
    (süre metni, notun sonuna eklenecek ipucu)"""
    dk = int(sn / 60)
    ipucu = " (Sayıyı dakika olarak okuma, doğal söyle.)"
    if dk >= 90:
        return f"yaklaşık {int(dk / 60 + 0.5)} saattir", ipucu
    if dk >= 60:
        return "yaklaşık 1 saattir", ipucu
    return f"yaklaşık {dk} dakikadır", ""

# 6 Kas (Dino'yu sabahtan beri tanımıyordu: tek seferde, tek ışıkta öğrenilmiş iz ofiste/loşta tutmadı):
#  - bir kişinin birden çok izi olur: yuz_izi\Dino.npy, Dino_2.npy, Dino_3.npy... "yüzümü öğren" yenisini EKLER, eskiyi silmez;
#    karar her kişinin en benzer izine göre.
#  - ses Dino'yu net tanıdıysa (ses_dino) SES_GUVEN sn boyunca tek tanınmayan yüz Dino sayılır: yabancı/bekçi uyarısı çıkmaz.
#  - yüz skorları değişince günlüğe "kamera: yüz ..." yazılır (eşik ayarı için).
SES_GUVEN = 10 * 60
# 8 Kas (Dino: "her gün bir daha tanıtıyoruz, saçım değişse bile tanısın"): GALERİ — yuz_izi\<ad>_galeri.npy (n,128) +
# <ad>_galeri.json [{"t", "kaynak": "aci"|"oto"}]. Ortalama yok, her kare ayrı; karar en benzer kareye göre.
#  - "yüzümü öğren" = açılı öğretme (ACI_ADIMLAR): Sakura yönlendirir, her adımda ~3 sn kare toplanır.
#  - kendi kendine öğrenme (_oto_ogren): yalnız tek yüz, kilit açık, yüz yeterince büyük ve ya ses az önce KESİN Dino dedi
#    (OTO_SES_PENCERE) ya da yüz zaten açıkça Dino (OTO_YUZ). Galeride buna çok benzeyen kare varsa eklenmez (OTO_BENZER).
#    En sık OTO_ARA'da bir. Galeri GALERI_EN çok; dolunca en gereksiz (en benzeri olan) oto kare atılır.
#  - "Sakura son öğrendiğin yüzleri unut" → son 24 saatin oto kareleri silinir.
ACI_ADIMLAR = [("Kameraya düz bak~", 3.0), ("Şimdi başını biraz sola çevir~", 3.0), ("Biraz da sağa~", 3.0),
               ("Hafif yukarı bak~", 2.5), ("Hafif aşağı bak~", 2.5), ("Gülümse bakayım~", 2.5),
               ("Konuşur gibi ağzını oynat~", 2.5), ("Son olarak biraz geri yaslan~", 2.5)]
ACI_BENZER = 0.88       # açılı öğretmede bundan benzer kare zaten varsa atla
OTO_BENZER = 0.72       # kendi kendine öğrenmede galeride bundan benzer kare varsa yeni sayılmaz
OTO_YUZ = 0.60          # yüz skoru bunun üstündeyse (tek yüz) açıkça Dino
OTO_SES_PENCERE = 8     # sn: ses KESİN Dino dedikten sonra bu kadar içinde görülen tek yüz Dino'dur
OTO_ARA = 60            # sn
GALERI_EN = 300
EN_KUCUK_YUZ = 70       # px: daha küçük (uzaktaki) yüz öğrenilmez
log = logging.getLogger()


class NanoDet:
    """OpenCV zoo NanoDet-Plus (object_detection_nanodet, Apache-2.0) ön/son işlemesinin sadeleştirilmiş hâli."""
    def __init__(self, yol, esik=0.35):
        self.net = cv2.dnn.readNet(yol)
        self.esik, self.reg = esik, 7
        self.strides, self.boy = (8, 16, 32, 64), 416
        self.mean = np.array([103.53, 116.28, 123.675], np.float32).reshape(1, 1, 3)
        self.std = np.array([57.375, 57.12, 58.395], np.float32).reshape(1, 1, 3)
        self.anchors = []
        for s in self.strides:
            n = self.boy // s
            xv, yv = np.meshgrid(np.arange(n) * s, np.arange(n) * s)
            self.anchors.append(np.column_stack((xv.flatten() + 0.5 * (s - 1), yv.flatten() + 0.5 * (s - 1))))

    def bul(self, bgr):
        """[(sınıf, güven, (x1,y1,x2,y2) 0-1 arası)]"""
        h, w = bgr.shape[:2]
        o = self.boy / max(h, w)
        kare = np.zeros((self.boy, self.boy, 3), np.uint8)
        kare[:int(h * o), :int(w * o)] = cv2.resize(bgr, (int(w * o), int(h * o)))
        self.net.setInput(cv2.dnn.blobFromImage((kare.astype(np.float32) - self.mean) / self.std))
        cikti = self.net.forward(self.net.getUnconnectedOutLayersNames())
        kutu, puan = [], []
        for s, cls, reg, anc in zip(self.strides, cikti[::2], cikti[1::2], self.anchors):
            cls, reg = cls.reshape(-1, cls.shape[-1]), reg.reshape(-1, 4 * (self.reg + 1))
            e = np.exp(reg.reshape(-1, self.reg + 1))
            d = ((e / e.sum(1, keepdims=True)) @ np.arange(self.reg + 1)).reshape(-1, 4) * s
            kutu.append(np.column_stack([anc[:, 0] - d[:, 0], anc[:, 1] - d[:, 1], anc[:, 0] + d[:, 2], anc[:, 1] + d[:, 3]]))
            puan.append(cls)
        kutu, puan = np.concatenate(kutu), np.concatenate(puan)
        sinif, guven = puan.argmax(1), puan.max(1)
        wh = kutu.copy(); wh[:, 2:] -= wh[:, :2]
        sec = cv2.dnn.NMSBoxes(wh.tolist(), guven.tolist(), self.esik, 0.6)
        return [(int(sinif[i]), float(guven[i]), tuple(kutu[i] / np.array([w * o, h * o, w * o, h * o]))) for i in np.array(sec).flatten()]


class Kamera:
    def __init__(self, asistan, kilitli):
        self.a, self.kilitli = asistan, kilitli
        self.bulucu = cv2.FaceDetectorYN.create(os.path.join(MODEL, "face_detection_yunet_2023mar.onnx"), "", (320, 240), 0.8)
        self.tanici = cv2.FaceRecognizerSF.create(os.path.join(MODEL, "face_recognition_sface_2021dec.onnx"), "")
        self.nesne = NanoDet(os.path.join(MODEL, "object_detection_nanodet_2022nov.onnx"))
        self.kisiler = {}   # ad -> (n, 128) izler
        for y in sorted(glob.glob(os.path.join(YUZ_IZI, "*.npy"))):
            if y.endswith("_galeri.npy"):
                continue   # galeri aşağıda ayrıca yüklenir
            ad = re.sub(r"_\d+$", "", os.path.basename(y)[:-4])
            e = np.load(y).reshape(-1, 128)
            self.kisiler[ad] = np.vstack([self.kisiler[ad], e]) if ad in self.kisiler else e
        self.son_ses_dino = 0.0      # ses Dino'yu en son ne zaman net tanıdı
        self.son_ses_kesin = 0.0     # ses Dino'yu en son ne zaman KESİN (>= KESIN) tanıdı (kendi kendine öğrenme için)
        self.son_oto = 0.0
        self.galeri_kilit = threading.Lock()
        self.galeri = {}             # ad -> [izler (n,128), meta listesi]
        for y in glob.glob(os.path.join(YUZ_IZI, "*_galeri.npy")):
            ad = os.path.basename(y)[:-len("_galeri.npy")]
            try:
                meta = json.load(open(y[:-4] + ".json", encoding="utf-8"))
            except Exception:
                meta = []
            e = np.load(y).reshape(-1, 128)
            self.galeri[ad] = [e, (meta + [{"t": 0, "kaynak": "aci"}] * len(e))[:len(e)]]
        self._son_skor_log = None
        self.kilit = threading.Lock()
        self.cap = None
        self.son_kare = None
        self.gorulen = None          # şu an bilgisayar başındaki: "Dino" | "Ali" | "?" | None
        self.son_dino = time.time()
        self.telefon = []
        self.son_olay = {"telefon": 0.0, "donus": time.time(), "yabanci": 0.0, "bekci": 0.0}
        self.son_kimler = (0.0, [])   # (ne zaman, o bakışta görülen yüzler) — ses tanımaya yardım (su_an)
        self.baska_sayac = 0
        self.ogrenme = None
        self._tek = {a: e for a, e in self.kisiler.items()}   # eski tek izler (Dino.npy, Dino_2.npy)
        self._kisileri_kur()
        log.info("kamera: tanıdığım yüzler %s (galeri %s)", {a: len(e) for a, e in self.kisiler.items()} or "yok",
                 {a: len(g[0]) for a, g in self.galeri.items()})
        threading.Thread(target=self._dongu, daemon=True).start()

    # ---------- kamera ----------
    def acik(self):
        return not os.path.exists(KAPALI)

    def ayarla(self, ac):
        if ac and os.path.exists(KAPALI):
            os.remove(KAPALI)
        elif not ac:
            open(KAPALI, "w").close()

    def _kare(self):
        with self.kilit:
            if self.cap is None:
                self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)   # MSMF bu kamerayı açamıyor (5 Kas)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                for _ in range(5):   # pozlama otursun
                    self.cap.read()
            ok, k = self.cap.read()
            return k if ok else None

    def _birak(self):
        with self.kilit:
            if self.cap is not None:
                self.cap.release()
                self.cap = None
                log.info("kamera: kapatıldı")

    def foto(self):
        """'Bana bak' için JPEG baytları (kamera kapalıysa None)."""
        if not self.acik() or self.kilitli():
            return None
        k = self._kare()
        if k is None:
            return None
        return cv2.imencode(".jpg", k, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()

    # ---------- yüz ----------
    def _yuzler(self, k):
        h, w = k.shape[:2]
        self.bulucu.setInputSize((w, h))
        _, yuz = self.bulucu.detect(k)
        return [] if yuz is None else list(yuz)

    def _iz(self, k, yuz):
        f = self.tanici.feature(self.tanici.alignCrop(k, yuz)).flatten()
        return f / np.linalg.norm(f)

    def _kim(self, k, yuz):
        if not self.kisiler:
            return None
        v = self._iz(k, yuz)
        self._izler.append(v)
        skor = {ad: float((e @ v).max()) for ad, e in self.kisiler.items()}
        en = max(skor, key=skor.get)
        self._skorlar.append({a: round(x, 2) for a, x in skor.items()})
        return en if skor[en] >= YUZ_ESIK else "?"

    def ses_dino(self, kesin=False):
        """Ses tanıma Dino'yu net tanıdı (sakura_asistan çağırır): bir süre tek tanınmayan yüz Dino sayılır.
        kesin: ses >= KESIN → az sonra görülen tek yüz galeriye öğrenilebilir."""
        self.son_ses_dino = time.time()
        if kesin:
            self.son_ses_kesin = time.time()

    # ---------- galeri (8 Kas) ----------
    def _kisileri_kur(self):
        k = dict(self._tek)
        for ad, (e, _) in self.galeri.items():
            if len(e):
                k[ad] = np.vstack([k[ad], e]) if ad in k else e
        self.kisiler = k

    def _galeri_kaydet(self, ad):
        e, meta = self.galeri[ad]
        os.makedirs(YUZ_IZI, exist_ok=True)
        yol = os.path.join(YUZ_IZI, ad + "_galeri")
        np.save(yol + ".tmp.npy", e)
        os.replace(yol + ".tmp.npy", yol + ".npy")
        with open(yol + ".json.tmp", "w", encoding="utf-8") as f:
            json.dump(meta, f)
        os.replace(yol + ".json.tmp", yol + ".json")

    def _galeri_ekle(self, ad, izler, kaynak, esik):
        """Yeni sayılan (galeride esik'ten benzeri olmayan) izleri ekler; kaç tane eklendiğini döndürür."""
        with self.galeri_kilit:
            e, meta = self.galeri.get(ad, [np.zeros((0, 128), np.float32), []])
            eklenen = 0
            for v in izler:
                hepsi = np.vstack([e, self._tek[ad]]) if ad in self._tek else e
                if len(hepsi) and float((hepsi @ v).max()) >= esik:
                    continue
                e = np.vstack([e, v[None].astype(np.float32)])
                meta = meta + [{"t": round(time.time()), "kaynak": kaynak}]
                eklenen += 1
            while len(e) > GALERI_EN:   # dolu: en gereksiz oto kareyi at (yoksa en gereksizini)
                oto = [i for i, m in enumerate(meta) if m.get("kaynak") == "oto"] or list(range(len(e)))
                b = e @ e.T
                np.fill_diagonal(b, -1)
                at = max(oto, key=lambda i: b[i].max())
                e = np.delete(e, at, 0)
                meta = meta[:at] + meta[at + 1:]
            if eklenen:
                self.galeri[ad] = [e, meta]
                self._galeri_kaydet(ad)
                self._kisileri_kur()
            return eklenen

    def unut_son(self, ad="Dino", saat=24):
        """Son `saat` saatte kendi kendine öğrenilen kareleri siler; kaç tane silindiğini döndürür."""
        with self.galeri_kilit:
            if ad not in self.galeri:
                return 0
            e, meta = self.galeri[ad]
            sinir = time.time() - saat * 3600
            kalan = [i for i, m in enumerate(meta) if not (m.get("kaynak") == "oto" and m.get("t", 0) >= sinir)]
            silinen = len(meta) - len(kalan)
            if silinen:
                self.galeri[ad] = [e[kalan], [meta[i] for i in kalan]]
                self._galeri_kaydet(ad)
                self._kisileri_kur()
            log.info("kamera: %s son %d saatte öğrendiği %d yüz karesini unuttu", ad, saat, silinen)
            return silinen

    def _oto_ogren(self, k, yuzler, simdi, kilitli):
        if kilitli or len(yuzler) != 1 or "Dino" not in self.kisiler or simdi - self.son_oto < OTO_ARA:
            return
        y = yuzler[0]
        if y[2] < EN_KUCUK_YUZ:
            return
        v = self._izler[0] if self._izler else self._iz(k, y)
        skor = float((self.kisiler["Dino"] @ v).max())
        baskasi = max((float((e @ v).max()) for a, e in self.kisiler.items() if a != "Dino"), default=-1)
        ses = simdi - self.son_ses_kesin < OTO_SES_PENCERE
        if baskasi >= YUZ_ESIK and baskasi > skor:
            return   # öğretilmiş başka birine (Ali) daha çok benziyor
        if not (ses or skor >= OTO_YUZ):
            return
        self.son_oto = simdi
        if self._galeri_ekle("Dino", [v], "oto", OTO_BENZER):
            log.info("kamera: kendi kendine öğrendi (%s, yüz %.2f) → galeri %d", "ses kesin" if ses else "yüz açık", skor,
                     len(self.galeri["Dino"][0]))

    def ogren_aci(self, ad, soyle):
        """Açılı öğretme: Sakura ACI_ADIMLAR'ı söyler (soyle(metin) söyleyip bitmesini bekler), her adımda tek yüzün
        karelerini toplar. Galeriye eklenen kare sayısını döndürür (0 = başarısız)."""
        if not self.acik() or self.kilitli():
            return 0
        izler, adim_say = [], []
        for metin, sure in ACI_ADIMLAR:
            soyle(metin)
            n0, bitis = len(izler), time.time() + sure
            while time.time() < bitis:
                k = self._kare()
                if k is None:
                    continue
                y = self._yuzler(k)
                if len(y) == 1 and y[0][2] >= EN_KUCUK_YUZ:
                    izler.append(self._iz(k, y[0]))
                time.sleep(0.15)
            adim_say.append(len(izler) - n0)
        if len(izler) < 10:
            log.info("kamera: %s açılı öğretme başarısız (%d kare, adımlar %s)", ad, len(izler), adim_say)
            return 0
        # aynı kişi mi: düz bakış karelerinin ortalamasına hiç benzemeyen (başkası/bozuk) kareler atılır
        duz = izler[:max(1, adim_say[0])]
        m = np.mean(duz, 0); m /= np.linalg.norm(m)
        temiz = [v for v in izler if float(v @ m) >= 0.30]
        eski = self.kisiler.get(ad)
        onceki = round(float((eski @ m).max()), 2) if eski is not None else None
        n = self._galeri_ekle(ad, temiz, "aci", ACI_BENZER)
        log.info("kamera: %s açılı öğretme: %d kare (adımlar %s), %d atıldı, galeriye %d eklendi (toplam %d), "
                 "eski izlere benzerlik %s", ad, len(izler), adim_say, len(izler) - len(temiz), n,
                 len(self.galeri.get(ad, [[]])[0]), onceki)
        return max(n, 1) if temiz else 0

    def ogren(self, ad):
        """Kameraya ~6 sn bakan tek yüzün izini kaydeder. Başarıysa kaç kare kullanıldığını döndürür."""
        if not self.acik() or self.kilitli():
            return 0
        izler, bitis = [], time.time() + 6
        while time.time() < bitis and len(izler) < 20:
            k = self._kare()
            if k is None:
                continue
            y = self._yuzler(k)
            if len(y) == 1:
                izler.append(self._iz(k, y[0]))
            time.sleep(0.25)
        if len(izler) < 5:
            log.info("kamera: %s yüzü öğrenilemedi (%d kare)", ad, len(izler))
            return 0
        e = np.mean(izler, 0); e /= np.linalg.norm(e)
        os.makedirs(YUZ_IZI, exist_ok=True)
        eski = self.kisiler.get(ad)
        onceki = float((eski @ e).max()) if eski is not None else None
        n, dosya = 1, os.path.join(YUZ_IZI, ad + ".npy")
        while os.path.exists(dosya):   # 6 Kas: eskinin üstüne yazma, yeni iz ekle
            n += 1
            dosya = os.path.join(YUZ_IZI, f"{ad}_{n}.npy")
        np.save(dosya, e)
        self.kisiler[ad] = e[None] if eski is None else np.vstack([eski, e])
        log.info("kamera: %s yüzü öğrenildi (%s, %d kare, tutarlılık en düşük %.2f, eski izlere benzerlik %s)", ad,
                 os.path.basename(dosya), len(izler), min(float(v @ e) for v in izler),
                 "yok" if onceki is None else round(onceki, 2))
        return len(izler)

    # ---------- izleme ----------
    def _dongu(self):
        while True:
            time.sleep(ARALIK)
            try:
                # 8 Kas (Dino istedi): kilit ekranında da kamera bakar ama YALNIZ bekçi (Telegram'a foto); Sakura sesle hiçbir
                # şey söylemez (_olay kilitliyken susar). Kamera yalnız "Kamera açık" kutusu kapalıysa bırakılır.
                if not self.acik():
                    self._birak()
                    continue
                k = self._kare()
                if k is None:
                    self._birak()
                    time.sleep(10)
                    continue
                self._bak(k)
            except Exception as e:
                log.exception("kamera: %s", e)
                self._birak()
                time.sleep(10)

    def _bak(self, k):
        simdi = time.time()
        yuzler = self._yuzler(k)
        self._skorlar, self._izler = [], []
        kimler = [self._kim(k, y) for y in yuzler[:3]]
        if kimler != self._son_skor_log:   # yalnız değişince yaz
            self._son_skor_log = list(kimler)
            log.info("kamera: yüz %s %s", kimler, self._skorlar)
        kilitli = self.kilitli()
        try:
            self._oto_ogren(k, yuzler, simdi, kilitli)
        except Exception as e:
            log.info("kamera: kendi kendine öğrenme hatası: %s", e)
        if kimler == ["?"] and not kilitli and (simdi - self.son_ses_dino < SES_GUVEN or simdi - self.son_dino < 60):
            kimler = ["Dino"]   # ses az önce net Dino dedi ya da Dino 1 dk önce görüldü: tek tanınmayan yüz Dino'dur
            # (6 Kas: ofiste başını çevirince yüzü 0,29-0,35 çıkıyor; ışık/ortam değişince yüz tutmuyor)
        dino_var = "Dino" in kimler or (kimler and kimler[0] is None)   # kimse öğretilmediyse yüz = Dino varsay
        # Dino geri geldi
        if dino_var:
            if simdi - self.son_dino > DONUS and simdi - self.son_olay["donus"] > DONUS_ARA:
                self.son_olay["donus"] = simdi
                sure, ipucu = yokluk_suresi(simdi - self.son_dino)
                self._olay(f"(Kamera: Dino bilgisayarın başına geri geldi, {sure} "
                           "yoktu. Tek cümleyle tatlı bir karşılama yap; uzun süre yoksa nerede olduğunu sorabilirsin." + ipucu + ")")
            self.son_dino = simdi
        # Dino yok, başkası var
        elif kimler and simdi - self.son_dino > 20 and simdi - self.son_olay["yabanci"] > YABANCI_ARA:
            self.son_olay["yabanci"] = simdi
            kim = next((x for x in kimler if x not in ("?", None)), "?")
            self._olay("(Kamera: bilgisayarın başında Dino değil, " + ("tanımadığın biri" if kim == "?" else kim) +
                       " var. Ona tek cümleyle seslen; Dino'nun bilgisayarı olduğunu hatırlat.)")
        # telefon
        tel = False
        if dino_var and not kilitli:
            tel = any(s == TELEFON and g >= TELEFON_ESIK for s, g, _ in self.nesne.bul(k))
        self.telefon = (self.telefon + [tel])[-5:]
        if sum(self.telefon) >= TELEFON_SURE and simdi - self.son_olay["telefon"] > TELEFON_ARA:
            self.son_olay["telefon"] = simdi
            self.telefon = []
            gor = getattr(self.a, "gorevler", None)
            if gor and gor.odak_acik():   # 5 Kas odak koçu: çalışacağını söylemişti
                self._olay("(Kamera + odak: Dino çalışacağını söylemişti ama birkaç saniyedir elindeki telefona bakıyor. "
                           "Şakacı, laf sokan tek cümleyle telefonu bırakıp işine dönmesini söyle.)")
            else:
                self._olay("(Kamera: Dino birkaç saniyedir elindeki telefona bakıyor. Kıskanç ve şakacı tek cümle laf at: "
                           "telefonda ne yaptığını, kiminle yazıştığını sor.)")
        self.gorulen = kimler[0] if kimler else None
        self.son_kimler = (simdi, kimler)
        self._bekci(k, kimler, simdi)

    def su_an(self, sure=6):
        """Son birkaç sn içinde kamerada görülen yüzler (["Dino", "?"] gibi); kamera kapalı/eski ise None."""
        t, k = self.son_kimler
        return k if time.time() - t < sure else None

    def _bekci(self, k, kimler, simdi):
        self.baska_sayac = self.baska_sayac + 1 if kimler and "Dino" not in kimler else 0
        if self.baska_sayac < 3 or simdi - self.son_dino < BEKCI_YOK or simdi - self.son_olay["bekci"] < BEKCI_ARA:
            return
        tg = getattr(self.a, "telegram", None)
        if not tg or not "Dino" in self.kisiler:   # Dino'nun yüzü öğretilmeden herkes Dino sayılır, bekçi çalışmaz
            return
        self.son_olay["bekci"] = simdi
        kim = next((x for x in kimler if x not in ("?", None)), "?")
        ok, jpg = cv2.imencode(".jpg", k, [cv2.IMWRITE_JPEG_QUALITY, 80])
        threading.Thread(target=tg.bekci, args=(kim, jpg.tobytes() if ok else None), daemon=True).start()

    def _olay(self, not_):
        """Sakura boştaysa beyne kamera notu gönderir (sesle tepki verir); meşgulse atlar."""
        a = self.a
        if self.kilitli():   # 8 Kas: kilit ekranında Sakura kimseye seslenmez (bekçi fotoğrafı ayrı, Telegram'a gider)
            return
        if a.konusuyor or a.beyin_kilit.locked() or not a.komut_q.empty() or a.ogrenme:
            return
        log.info("kamera olayı: %s", not_)
        a.komut_q.put((not_, "sistem"))
