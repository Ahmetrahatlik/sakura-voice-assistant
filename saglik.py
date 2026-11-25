# Sakura'nın sağlık bekçisi (8 Kas 2026, Dino istedi: "dışarıdayken bozulursa Sakura ile Claude'a düzelttireyim").
# Asistanın içinde çalışır; bir şey bozulduğunu kendisi fark edince Telegram'dan Dino'ya yazar, altında
# "🔧 Düzelt" / "Boş ver" düğmeleri olur. Düzelt'e basılırsa is_ver.py ile ayrı bir Claude Code oturumuna tamir işi verilir
# (iş bitince Telegram'a "işim bitti" gelir). Dino onaylamadan hiçbir şeyi değiştirmez.
# İzlenenler:
#  - günlüğe düşen her HATA (log.exception / ERROR) ve yakalanmamış iş parçacığı hatası
#  - Telegram bağlantısı TG_KOPUK sn'den uzun koptuysa (haber bağlantı gelince gider)
#  - arama tüneli: TUNEL_SAYI kez / TUNEL_PENCERE içinde yenilendiyse ya da TUNEL_YOK sn'dir adres yoksa
# Aynı sorun en sık AYNI_ARA'da bir, herhangi bir haber en sık GENEL_ARA'da bir. Açılıştan sonraki ISINMA sn sayılmaz.
# Deneme: jarvis\saglik_deneme.flag dosyası oluşturulursa zararsız bir "DENEME" arızası haber verilir.
import os, sys, json, time, logging, threading, traceback, subprocess, collections

KOK = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable.replace("pythonw.exe", "python.exe")
DENEME = os.path.join(KOK, "saglik_deneme.flag")
TG_KOPUK = 10 * 60
TUNEL_SAYI, TUNEL_PENCERE, TUNEL_YOK = 3, 30 * 60, 5 * 60
AYNI_ARA, GENEL_ARA, ISINMA = 30 * 60, 10 * 60, 3 * 60
log = logging.getLogger()


class _Yakala(logging.Handler):
    def __init__(self, s):
        super().__init__(logging.ERROR)
        self.s = s

    def emit(self, kayit):
        try:
            ayrinti = kayit.getMessage()
            if kayit.exc_info:
                ayrinti += "\n" + "".join(traceback.format_exception(*kayit.exc_info))[-1500:]
            self.s.sorun(f"hata: {kayit.getMessage()[:80]}", ayrinti)
        except Exception:
            pass


class Saglik:
    def __init__(self, asistan):
        self.a = asistan
        self.basla = time.time()
        self.son = {}                 # imza → son haber zamanı
        self.son_genel = 0.0
        self.bekleyen = {}            # id → {ozet, ayrinti}
        self.kuyruk = collections.deque(maxlen=20)
        self.tg_koptu = None
        log.addHandler(_Yakala(self))
        eski = threading.excepthook
        def kanca(args):
            self.sorun(f"çöken iş parçacığı: {args.exc_type.__name__}",
                       "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))[-1500:])
            eski(args)
        threading.excepthook = kanca
        tg = getattr(asistan, "telegram", None)
        if tg:
            tg.fx_isleyici = self.dugme
        threading.Thread(target=self._dongu, daemon=True).start()

    # ---------- algılama ----------
    def sorun(self, imza, ayrinti):
        """Bir sorun bildir (her iş parçacığından çağrılabilir; gönderim ayrı iş parçacığında)."""
        if time.time() - self.basla < ISINMA and not imza.startswith("DENEME"):
            return
        self.kuyruk.append((imza, ayrinti))

    def _dongu(self):
        while True:
            time.sleep(15)
            try:
                self._kontrol()
                while self.kuyruk:
                    self._haber(*self.kuyruk.popleft())
            except Exception as e:
                log.info("sağlık: %s", e)

    def _kontrol(self):
        simdi = time.time()
        if os.path.exists(DENEME):
            os.remove(DENEME)
            self.kuyruk.append(("DENEME arızası", "Bu Dino'nun istediği bir deneme; gerçek bir sorun yok."))
        tg = getattr(self.a, "telegram", None)
        if tg and getattr(tg, "son_ok", 0):
            kopuk = simdi - tg.son_ok
            if kopuk > TG_KOPUK and self.tg_koptu is None:
                self.tg_koptu = tg.son_ok
            elif kopuk < 120 and self.tg_koptu is not None:   # bağlantı geri geldi: şimdi haber verilebilir
                dk = (simdi - self.tg_koptu) / 60
                self.tg_koptu = None
                self.kuyruk.append(("Telegram koptu", f"Telegram bağlantısı yaklaşık {dk:.0f} dakika koptu, şimdi geri geldi. "
                                    "Son 'telegram bağlantı' satırları günlükte."))
        ar = getattr(self.a, "arama", None)
        if ar:
            yeni = [t for t in getattr(ar, "tunel_yenileme", []) if simdi - t < TUNEL_PENCERE]
            if len(yeni) >= TUNEL_SAYI:
                self.kuyruk.append(("arama tüneli sürekli düşüyor",
                                    f"Son {TUNEL_PENCERE // 60} dakikada tünel {len(yeni)} kez yenilendi."))
                ar.tunel_yenileme = []
            if ar.adres is None:
                ar._adres_yok = getattr(ar, "_adres_yok", None) or simdi
                if simdi - ar._adres_yok > TUNEL_YOK:
                    self.kuyruk.append(("arama tüneli açılamıyor", f"{TUNEL_YOK // 60} dakikadır tünel adresi yok."))
                    ar._adres_yok = simdi
            else:
                ar._adres_yok = None

    # ---------- haber ve tamir ----------
    def _haber(self, imza, ayrinti):
        simdi = time.time()
        deneme = imza.startswith("DENEME")
        if not deneme and (simdi - self.son.get(imza, 0) < AYNI_ARA or simdi - self.son_genel < GENEL_ARA):
            return
        tg = getattr(self.a, "telegram", None)
        if not (tg and tg.token and tg.ayar.get("sahip")):
            return
        self.son[imza], self.son_genel = simdi, simdi
        sid = os.urandom(3).hex()
        self.bekleyen[sid] = {"ozet": imza, "ayrinti": ayrinti, "zaman": simdi}
        log.info("sağlık: sorun bulundu, Dino'ya soruluyor (%s): %s", sid, imza)
        tg._api("sendMessage", {"chat_id": tg.ayar["sahip"],
                                "text": f"⚠️ Bende bir sorun var tatlım~\n🩺 {imza}\n\n{ayrinti[-1200:]}\n\nClaude'a düzelttireyim mi?",
                                "reply_markup": json.dumps({"inline_keyboard": [[
                                    {"text": "🔧 Düzelt", "callback_data": f"fx:{sid}:d"},
                                    {"text": "Boş ver", "callback_data": f"fx:{sid}:b"}]]})})

    def dugme(self, sid, secim):
        """telegram_kopru 'fx:' düğmesinden çağırır. Telegram'a gösterilecek kısa yazıyı döndürür."""
        b = self.bekleyen.pop(sid, None)
        if not b:
            return "Bu haber kapandı~"
        if secim != "d":
            log.info("sağlık: Dino boş ver dedi (%s)", b["ozet"])
            return "Tamam, boş verdim~"
        if b["ozet"].startswith("DENEME"):
            gorev = ("Bu bir DENEME (Dino Sakura'nın tamir düğmesini sınıyor). Hiçbir dosyayı DEĞİŞTİRME. Sadece "
                     + os.path.join(KOK, "asistan.log") + r" dosyasının son 5 satırını oku ve tek cümleyle "
                     "'Deneme tamam, tamir düğmesi çalışıyor' diye özetle.")
        else:
            gorev = (
                "Sakura'nın sesli asistanında (" + KOK + ") bir sorun var ve Dino PC başında değil; "
                "Telegram'dan 'Düzelt' dedi. Önce BENI-OKU.txt'yi oku, sonra asistan.log'un son 300 satırına bak.\n"
                f"Sorun: {b['ozet']}\nAyrıntı:\n{b['ayrinti'][-2000:]}\n\n"
                "Nedeni bul ve düzelt. Kurallar: değiştireceğin her dosyanın önce yedeğini al (yedek-tamir-<saat>\\ klasörü); "
                "yalnız bu sorunla ilgili değişiklik yap; asistanı yeniden başlatman gerekirse ÖNCE "
                f"\"{PY}\" \"{os.path.join(KOK, 'tg_yaz.py')}\" \"Düzelttim, şimdi kendimi yeniden başlatıyorum (~2 dk)~\" ile "
                "Dino'ya haber ver, sonra durdur.ps1 ve baslat.ps1, açıldığını günlükten doğrula; ne yaptığını BENI-OKU.txt'nin "
                "sonuna kısaca yaz. "
                "Emin olamadığın, büyük ya da geri alınamaz bir şey gerekiyorsa YAPMA, bitirirken Dino'ya ne gerektiğini yaz. "
                "Sonunda Türkçe, kısa ve samimi bir özet ver: ne bozuktu, ne yaptın, şimdi çalışıyor mu.")
        try:
            subprocess.Popen([PY, os.path.join(KOK, "is_ver.py"), gorev, KOK], cwd=KOK, creationflags=0x08000000,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log.info("sağlık: tamir işi Claude'a verildi (%s)", b["ozet"])
            return "🔧 Claude'a verdim, bitince haber veririm~"
        except Exception as e:
            log.info("sağlık: tamir işi verilemedi: %s", e)
            return f"Ayy, Claude'a veremedim: {e}"
