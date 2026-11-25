# Sakura'nın arka plan görevleri (5 Kas 2026, Dino istedi):
#  - GECE MODU: 00:00-07:00 arası ses kısılır, cevaplar kısa; 01:00-05:00 arası Dino hâlâ bilgisayardaysa gecede bir kez
#    "yat artık" tribi.
#  - ODAK KOÇU: "Sakura çalışıyorum" → odak modu (en çok 4 saat, "çalışmayı bıraktım" ile biter). Bu sürede öndeki pencere
#    10 dakikayı aşkın oyalanma sitesindeyse (YouTube, Instagram, oyun...) laf sokar. Kamera telefon lafı da odak lafı olur.
# Ekran görüntüsü alınmaz: yalnız öndeki pencerenin başlığına bakılır.
import re, time, ctypes, datetime, logging

log = logging.getLogger()

GECE_BAS, GECE_BIT = 0, 7          # saat: bu aralıkta gece modu
GECE_SES = 0.45                    # gece ses yüksekliği çarpanı
TRIP_BAS, TRIP_BIT = 1, 5          # bu saatlerde Dino bilgisayardaysa gecede bir kez trip
ODAK_EN_COK = 4 * 3600             # odak modu kendiliğinden kapanır
ODAK_SINIR = 10 * 60               # bu kadar oyalanınca laf
ODAK_ARA = 10 * 60                 # iki laf arası en az
ARALIK = 30
TAZELE_TUR = 15                    # beyin bu kadar sorudan sonra...
TAZELE_BOS = 10 * 60               # ...bu kadar sn kimse konuşmadıysa tazelenir (5 Kas: sohbet uzadıkça ilk söz yavaşlıyordu)

ODAK_AC = re.compile(r"çalışmaya başlıyorum|çalışmaya başlayacağım|çalışacağım|odak modu(?:nu)? aç|odaklanmam lazım|"
                     r"(?:şimdi|artık|ders) çalışıyorum|^\W*(?:ben )?çalışıyorum\W*$")
ODAK_KAPAT = re.compile(r"çalışmayı bıraktım|çalışma(?:m)? bitti|mola veriyorum|odak modu(?:nu)? kapat|bugünlük bu kadar")
# Odak sırasında oyalanma sayılan pencere başlıkları (YouTube Studio / Meta Business iş sayılır: Dino video yapıyor)
OYALANMA = re.compile(r"youtube|instagram|tiktok|netflix|roblox|twitch|reddit|facebook|steam|valorant|minecraft|"
                      r"9gag|ekşi|eksisozluk|dizi izle|film izle|prime video|disney\+|exxen|blutv", re.I)
ISTISNA = re.compile(r"studio|creator|business suite|meta business|reklam yöneticisi|ads manager", re.I)


def gece():
    return GECE_BAS <= datetime.datetime.now().hour < GECE_BIT


def bosta_sure():
    """Son klavye/fare hareketinden beri geçen sn."""
    class L(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
    l = L(cbSize=ctypes.sizeof(L))
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(l))
    return ((ctypes.windll.kernel32.GetTickCount() - l.dwTime) & 0xFFFFFFFF) / 1000


def on_pencere():
    u = ctypes.windll.user32
    h = u.GetForegroundWindow()
    n = u.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, b, n + 1)
    return b.value


def olay(a, not_):
    """Sakura boştaysa beyne sistem notu gönderir (sesle tepki verir); meşgulse False."""
    if a.konusuyor or a.beyin_kilit.locked() or not a.komut_q.empty() or a.ogrenme:
        return False
    log.info("görev olayı: %s", not_)
    a.komut_q.put((not_, "sistem"))
    return True


class Gorevler:
    def __init__(self, asistan, kilitli):
        self.a, self.kilitli = asistan, kilitli
        self.odak_bitis = 0.0
        self.oyalanma = 0.0
        self.son_uyari = 0.0
        self.son_trip = None      # tarih: o gecenin tribi atıldı

    # ---------- odak ----------
    def odak_acik(self):
        return time.time() < self.odak_bitis

    def odak_komut(self, k):
        """Dino'nun sözü odak modunu açıyor/kapatıyorsa beyne gidecek notu döndürür (yoksa "")."""
        if ODAK_KAPAT.search(k) and self.odak_acik():
            dk = int((time.time() - (self.odak_bitis - ODAK_EN_COK)) / 60)
            self.odak_bitis = 0.0
            log.info("odak modu kapandı (%d dk)", dk)
            return f"(Sistem: odak modu kapandı, Dino yaklaşık {dk} dakika çalıştı. Kısaca tebrik et.) "
        if ODAK_AC.search(k):
            self.odak_bitis, self.oyalanma, self.son_uyari = time.time() + ODAK_EN_COK, 0.0, 0.0
            log.info("odak modu açıldı")
            return ("(Sistem: odak modu açıldı. Dino çalışırken 10 dakikadan fazla YouTube/Instagram/oyunda oyalanırsa ya da "
                    "telefona dalarsa sen uyaracaksın. Şimdi kısa bir destek cümlesi söyle.) ")
        return ""

    # ---------- döngü ----------
    def dongu(self):
        while True:
            time.sleep(ARALIK)
            try:
                self._bak()
            except Exception as e:
                log.info("görevler: %s", e)

    def _tazele(self):
        """Ses beyni ve Telegram beyni: çok soru birikti ve uzun süredir boştaysa yeni süreçle değiştirilir."""
        import hafiza
        a = self.a
        tg = getattr(a, "telegram", None)
        for ad, beyin, kilit in [("ses", a.beyin, a.beyin_kilit)] + ([("telegram", tg.beyin, tg.beyin_kilit)] if tg else []):
            if beyin.tur < TAZELE_TUR or time.time() - beyin.son < TAZELE_BOS or a.konusuyor:
                continue
            if not kilit.acquire(blocking=False):
                continue
            try:
                t, n = time.time(), beyin.tur
                son = "\n".join(hafiza.son_satirlar(30)) or "(bugün henüz konuşma yok)"
                beyin.tazele("(Sistem: beynin tazelendi — eski süreç uzamıştı, yenisi açıldı; hiçbir şey kaybolmadı. HAFIZA.md'yi ve "
                             "GUNLUK.md'yi oku. Bugünkü son konuşmalar (en yenisi en altta; Telegram satırları '(Telegram)' "
                             "etiketli):\n" + son + "\nSohbete buradan devam edeceksin. Cevap olarak sadece 'hazır' yaz.)")
                log.info("beyin tazelendi: %s (%d sorudan sonra, %.0f sn)", ad, n, time.time() - t)
            except Exception as e:
                log.info("beyin tazeleme (%s): %s", ad, e)
            finally:
                kilit.release()

    def _bak(self):
        self._tazele()          # kilitliyken de (Dino yokken tazelemenin en iyi zamanı)
        if self.kilitli():
            return
        simdi = time.time()
        # odak koçu
        if self.odak_acik():
            baslik = on_pencere()
            if OYALANMA.search(baslik) and not ISTISNA.search(baslik) and bosta_sure() < 300:
                self.oyalanma += ARALIK
            else:
                self.oyalanma = max(0.0, self.oyalanma - ARALIK / 2)
            if self.oyalanma >= ODAK_SINIR and simdi - self.son_uyari > ODAK_ARA:
                if olay(self.a, f"(Odak: Dino çalışacağını söylemişti ama yaklaşık {int(self.oyalanma / 60)} dakikadır "
                                f"oyalanıyor; öndeki pencere: \"{baslik[:80]}\". Şakacı, laf sokan tek-iki cümleyle işine "
                                "döndür. Ne izlediğine/oynadığına göre laf sok.)"):
                    self.son_uyari, self.oyalanma = simdi, 0.0
        elif self.odak_bitis:
            self.odak_bitis = 0.0
            log.info("odak modu süresi doldu")
        # gece tribi: gecede bir kez, Dino son 2 dakikada bilgisayarı kullandıysa
        now = datetime.datetime.now()
        if TRIP_BAS <= now.hour < TRIP_BIT and self.son_trip != now.date() and bosta_sure() < 120:
            if olay(self.a, f"(Sistem: saat {now:%H:%M}, gece oldu ve Dino hâlâ bilgisayarda. Yatması için tatlı, kıskanç, "
                            "trip atan tek-iki cümle söyle; kısık sesle konuşuyorsun.)"):
                self.son_trip = now.date()
