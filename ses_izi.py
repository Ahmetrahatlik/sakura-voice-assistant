# Ses tanıma (5 Kas, Dino istedi): kim konuşuyor? İndirme yok: Chatterbox'ın küçük ses kodlayıcısı (VoiceEncoder, MIT,
# jarvis\ses_kodlayici\, 5,5 MB, CPU'da çalışır) her konuşmanın "ses parmak izini" çıkarır, öğretilmiş kişilerinkiyle
# karşılaştırır (kosinüs benzerliği). XTTS'in kendi kodlayıcısı denendi, ayırt edemedi (ses\test\ses_izi_olc.py).
# Öğretme: "Sakura sesimi öğren" (Dino) / "Sakura Ali'nin sesini öğren" → ~20 sn konuşma → ses_izi\<ad>.npy (+ <ad>.wav).
# Karar: öğretilmiş kişilerden en benzeri seçilir; hepsi BILINMEYEN'in altındaysa "?" (tanımadığım biri).
# Kısa ya da kararsız sözde Dino varsayılır (Dino'yu kırmamak için). Eşikler gerçek kayıtlarla (duyulan\) ayarlanacak.
import os, glob, logging
import numpy as np, soundfile as sf, torch

KOK = os.path.dirname(os.path.abspath(__file__))
KLASOR = os.path.join(KOK, "ses_izi")
BILINMEYEN = 0.68   # en yüksek benzerlik bunun altındaysa tanımadığım biri (5 Kas: Dino 1,5 sn 0,70-0,91; yabancı FLEURS en çok 0,65;
                    # 5 Kas 15:41 Dino'nun arkadaşı "Nasılsın?" 0,65 ile Dino sanıldı → 0,65'ten 0,68'e)
KESIN = 0.78        # kamera Dino'dan başka bir yüz görürken ses Dino'ya bu kadar benzemiyorsa konuşan o kişi sayılır
ZAYIF = 0.72       # kamera yalnız tek tanınmayan yüz görüyorsa (Dino yandan bakınca da olur) ses bunun altındaysa yabancı
FARK = 0.04         # iki kişi bu kadar yakınsa kararsız → Dino
KISA = 1.0          # sn (sessizlik hariç gerçek konuşma): bundan kısa sözde parmak izi güvenilmez → Dino
SR = 16000
log = logging.getLogger()


def konusma_suresi(y, h=320):
    """Baş/son sessizlik hariç konuşma süresi. Dinleme parçası önde 0,3 sn, sonda 0,65 sn sessizlik taşır:
    5 Kas'ta tek başına "Sakura" (0,5 sn konuşma, 1,6 sn parça) kısa sayılmayıp yabancı sanıldı."""
    n = len(y) // h
    if not n:
        return 0.0
    e = np.sqrt((np.asarray(y[:n * h], np.float32).reshape(n, h) ** 2).mean(1))
    a = np.where(e > 0.1 * e.max())[0]
    return (a[-1] - a[0] + 1) * h / SR if len(a) else 0.0


class SesIzi:
    def __init__(self, _xtts=None):
        from ses_kodlayici import VoiceEncoder
        self.enc = VoiceEncoder()
        self.enc.load_state_dict(torch.load(os.path.join(KOK, "ses_kodlayici", "ve.pt"), map_location="cpu"))
        self.enc.eval()
        self.kisiler = {}
        for yol in glob.glob(os.path.join(KLASOR, "*.npy")):
            self.kisiler[os.path.basename(yol)[:-4]] = np.load(yol)
        log.info("ses tanıma: tanıdığım kişiler %s", list(self.kisiler) or "yok")

    def iz(self, y):
        with torch.inference_mode():
            return self.enc.embeds_from_wavs([np.asarray(y, np.float32)], sample_rate=SR)[0]

    def ogret(self, ad, parcalar):
        """parcalar: 16 kHz konuşma parçaları. Tüm konuşmanın parmak izi saklanır."""
        y = np.concatenate(parcalar).astype(np.float32)
        e = self.iz(y)
        e = e / np.linalg.norm(e)
        os.makedirs(KLASOR, exist_ok=True)
        np.save(os.path.join(KLASOR, ad + ".npy"), e)
        sf.write(os.path.join(KLASOR, ad + ".wav"), y, SR)
        self.kisiler[ad] = e
        # 3 sn'lik dilimler bütüne ne kadar benziyor: kişinin "tutarlılığı" (günlüğe, eşik ayarı için)
        n = 3 * SR
        dilim = [float(self.iz(y[i:i + n]) @ e) for i in range(0, len(y) - n + 1, n)]
        log.info("ses tanıma: %s öğrenildi (%.0f sn, 3 sn dilim benzerliği %s)", ad, len(y) / SR, [round(d, 2) for d in dilim])

    def kim(self, y):
        """(ad, skorlar). Kimse öğretilmemişse ad=None (eski davranış). Tanınmayan = "?"."""
        if not self.kisiler:
            return None, {}
        v = self.iz(y)
        skor = {ad: float(v @ e) for ad, e in self.kisiler.items()}
        sira = sorted(skor, key=skor.get, reverse=True)
        en = sira[0]
        dino_var = "Dino" in self.kisiler
        if dino_var and konusma_suresi(y) < KISA:
            return "Dino", skor   # çok kısa söz ("Sakura" tek başına ~0,5 sn): emin olunamaz
        if skor[en] < BILINMEYEN:
            return "?", skor
        if dino_var and en != "Dino" and skor[en] - skor["Dino"] < FARK:
            return "Dino", skor   # kararsız
        return en, skor
