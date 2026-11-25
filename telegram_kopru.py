# Telegram köprüsü (5 Kas 2026, 2. aşama): Dino dışarıdayken Sakura'yla Telegram'dan yazışır / sesli mesajlaşır.
# Asistanın içinde ayrı bir iş parçacığı olarak çalışır; aynı beyni (kişilik, hafıza) [uzaktan] etiketiyle kullanır.
# - Anahtar: SAKURA_TELEGRAM_TOKEN ortam değişkeni (Dino setx ile koydu; çalışan süreçlere geçmediği için kayıt
#   defterinden de okunur, anahtar gelene kadar 30 sn'de bir bakılır). Anahtar hiçbir dosyaya yazılmaz.
# - Sahip: bota ilk yazan sohbet (telegram.json "sahip"). Başkasının mesajı yok sayılır.
# - Yazı → yazı; sesli mesaj → Whisper → beyin → Sakura'nın sesiyle sesli mesaj (+ yazısı). Fotoğraf → beyin görür.
# - Beyin cevabına [ss] yazarsa ekran görüntüsü gönderilir. PC'den ses çıkmaz, balonda yalnız "📱 Dino'yla konuşuyorum~".
# - Arka plan işi (is_ver.py) bitince: PC kilitliyse ya da son 1 saatte Telegram'dan konuşulduysa Telegram'a haber.
import os, re, io, json, time, uuid, glob, logging, threading, subprocess, urllib.request, urllib.parse
import numpy as np

KOK = os.path.dirname(os.path.abspath(__file__))
import shutil, ssl, certifi
# Windows sertifika deposuyla api.telegram.org doğrulanamıyor ("self-signed certificate in chain", 5 Kas); certifi listesi çalışıyor
SSL = ssl.create_default_context(cafile=certifi.where())
FFMPEG = shutil.which("ffmpeg") or next(iter(glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
                                                                    "Packages", "Gyan.FFmpeg*", "*", "bin", "ffmpeg.exe"))), "ffmpeg")
AYAR = os.path.join(KOK, "telegram.json")
# 5 Kas: Telegram'dan gelen dosya ve fotoğraflar buraya kaydedilir (Dino istedi). Bot en çok 20 MB indirebilir.
def _masaustu():
    try:
        import ctypes.wintypes
        b = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, b)   # CSIDL_DESKTOPDIRECTORY (OneDrive'a taşınmış olabilir)
        if b.value:
            return b.value
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")
GELEN = os.path.join(_masaustu(), "Sakura'ya gelenler")
EN_BUYUK = 20 * 1024 * 1024
ISLER = os.path.join(KOK, "isler")
log = logging.getLogger()


def anahtar():
    t = os.environ.get("SAKURA_TELEGRAM_TOKEN")
    if t:
        return t.strip()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, "SAKURA_TELEGRAM_TOKEN")[0].strip()
    except OSError:
        return None


class Kopru:
    def __init__(self, asistan, temizle, ekran_goruntusu, kilitli, bol, ses_duygu, model="sonnet"):
        """Asistanın yardımcıları dışarıdan verilir (sakura_asistan __main__ olarak çalıştığı için içe aktarılmaz)."""
        self.a, self.temizle, self.ekran, self.kilitli = asistan, temizle, ekran_goruntusu, kilitli
        self.bol, self.ses_duygu = bol, ses_duygu
        # 5 Kas ara yol (Dino seçti): Telegram'ın kendi beyni var (sonnet: biraz yavaş ama yazışmada fark edilmez, daha
        # sivri). Sesli sohbet ve arama haiku'da kalır. Öteki kanalda konuşulanlar hafiza.kacirilan() ile not olarak gelir.
        from beyin import Beyin
        self.beyin = Beyin(model)
        self.beyin_kilit = threading.Lock()
        try:
            self.ayar = json.load(open(AYAR, encoding="utf-8"))
        except (OSError, ValueError):
            self.ayar = {}
        self.token = None
        self.son_konusma = 0.0
        self.son_ok = 0.0
        self.fx_isleyici = None       # 8 Kas: saglik.Saglik.dugme ("🔧 Düzelt" düğmesi)
        self.kararlar = {}            # 8 Kas: Claude sorusu → Telegram düğmeleri (id → {sorular, cevaplar, mesajlar, baska})
        self.karar_kilit = threading.Lock()
        threading.Thread(target=self._dongu, daemon=True).start()
        threading.Thread(target=self._is_takip, daemon=True).start()

    # ---------- Telegram API ----------
    def _api(self, yontem, veri=None, dosya=None, zaman=60):
        url = f"https://api.telegram.org/bot{self.token}/{yontem}"
        if dosya:   # çok parçalı yükleme: dosya = (alan, ad, bayt, tür)
            sinir = uuid.uuid4().hex
            govde = io.BytesIO()
            for k, v in (veri or {}).items():
                govde.write(f'--{sinir}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
            alan, ad, bayt, tur = dosya
            govde.write(f'--{sinir}\r\nContent-Disposition: form-data; name="{alan}"; filename="{ad}"\r\n'
                        f'Content-Type: {tur}\r\n\r\n'.encode() + bayt + f"\r\n--{sinir}--\r\n".encode())
            istek = urllib.request.Request(url, govde.getvalue(), {"Content-Type": f"multipart/form-data; boundary={sinir}"})
        else:
            istek = urllib.request.Request(url, urllib.parse.urlencode(veri or {}).encode())
        with urllib.request.urlopen(istek, timeout=zaman, context=SSL) as r:
            return json.loads(r.read())["result"]

    def _indir(self, file_id):
        yol = self._api("getFile", {"file_id": file_id})["file_path"]
        with urllib.request.urlopen(f"https://api.telegram.org/file/bot{self.token}/{yol}", timeout=60, context=SSL) as r:
            return r.read()

    def yaz(self, metin, **ek):
        if self.ayar.get("sahip") and metin.strip():
            self._api("sendMessage", {"chat_id": self.ayar["sahip"], "text": metin[:4000], **ek})

    # ---------- ana döngü ----------
    def _dongu(self):
        while not self.token:
            self.token = anahtar()
            if not self.token:
                time.sleep(30)
        log.info("telegram: bağlandı%s", "" if self.ayar.get("sahip") else " (sahip bekleniyor: bota ilk yazan)")
        threading.Thread(target=self._isit, daemon=True).start()
        ofset = 0
        while True:
            try:
                guncel = self._api("getUpdates", {"offset": ofset, "timeout": 50}, zaman=70)
                self.son_ok = time.time()   # 8 Kas: sağlık bekçisi bağlantının koptuğunu buradan anlar
                for g in guncel:
                    ofset = g["update_id"] + 1
                    m = g.get("message")
                    if m:
                        threading.Thread(target=self._mesaj, args=(m,), daemon=True).start()
                    cq = g.get("callback_query")
                    if cq:
                        threading.Thread(target=self._dugme_cevap, args=(cq,), daemon=True).start()
            except Exception as e:
                log.info("telegram bağlantı: %s", e)
                time.sleep(10)

    # ---------- Claude sorusu → Telegram düğmeleri (8 Kas, Dino istedi) ----------
    # karar_sor.py (PreToolUse kancası, AskUserQuestion) Dino PC başında değilken soruyu buraya verir; Dino düğmeye basar
    # ya da "✍️ Başka" deyip yazar; kanca cevabı Claude'a iletir. Yalnız sahip cevaplayabilir.
    def karar_baslat(self, kid, sorular, yer):
        with self.karar_kilit:
            self.kararlar[kid] = {"sorular": sorular, "cevaplar": {}, "mesajlar": {}, "baska": None, "zaman": time.time()}
        self.yaz(f"🤔 Claude senden karar bekliyor~\n📁 {yer}\nAşağıdan seç, ben ona iletirim ✨")
        for qi, q in enumerate(sorular):
            dugmeler = [[{"text": (o.get("label") or "?")[:60], "callback_data": f"ks:{kid}:{qi}:{oi}"}]
                        for oi, o in enumerate(q.get("options") or [])]
            dugmeler.append([{"text": "✍️ Başka (yazarak)", "callback_data": f"ks:{kid}:{qi}:b"}])
            aciklama = "\n".join(f"• {o.get('label')}: {o.get('description', '')}"[:200] for o in q.get("options") or [])
            metin = f"❓ {q.get('question', '')}" + (" (birden çok seçilebilir: hepsini ✍️ Başka ile yaz)" if q.get("multiSelect") else "")
            sonuc = self._api("sendMessage", {"chat_id": self.ayar["sahip"], "text": (metin + "\n\n" + aciklama)[:4000],
                                               "reply_markup": json.dumps({"inline_keyboard": dugmeler})})
            self.kararlar[kid]["mesajlar"][qi] = sonuc.get("message_id")

    def karar_durum(self, kid):
        k = self.kararlar.get(kid)
        if not k:
            return None
        return {"bitti": len(k["cevaplar"]) >= len(k["sorular"]),
                "cevaplar": [{"soru": q.get("question"), "cevap": k["cevaplar"].get(qi)} for qi, q in enumerate(k["sorular"])]}

    def karar_kapat(self, kid, neden):
        """Kanca vazgeçti (süre doldu / Dino PC'ye döndü): düğmeler kaldırılır."""
        k = self.kararlar.pop(kid, None)
        if not k:
            return
        for qi, mid in k["mesajlar"].items():
            if qi not in k["cevaplar"] and mid:
                try:
                    self._api("editMessageReplyMarkup", {"chat_id": self.ayar["sahip"], "message_id": mid,
                                                         "reply_markup": json.dumps({"inline_keyboard": []})})
                except Exception:
                    pass
        if neden:
            self.yaz(neden)

    def _dugme_cevap(self, cq):
        veri = cq.get("data") or ""
        sahip_mi = (cq.get("message") or {}).get("chat", {}).get("id") == self.ayar.get("sahip")
        if sahip_mi:
            self.son_konusma = time.time()   # 8 Kas: düğmeye basmak da konuşma sayılır ("işim bitti" haberi gelsin)
        try:
            if sahip_mi and veri.startswith("fx:") and self.fx_isleyici:   # 8 Kas: sağlık bekçisi "Düzelt / Boş ver"
                _, sid, secim = veri.split(":")
                self._api("answerCallbackQuery", {"callback_query_id": cq["id"]})
                yazi = self.fx_isleyici(sid, secim)
                self._api("editMessageReplyMarkup", {"chat_id": self.ayar["sahip"], "message_id": cq["message"]["message_id"],
                                                     "reply_markup": json.dumps({"inline_keyboard": []})})
                self.yaz(yazi)
                return
            if sahip_mi and veri.startswith("gl:"):   # 8 Kas: haftalık gelişim önerisi "✅ Yap / ❌ Geç"
                import gelisim
                _, oid, secim = veri.split(":")
                self._api("answerCallbackQuery", {"callback_query_id": cq["id"]})
                yazi = gelisim.dugme(oid, secim)
                self._api("editMessageReplyMarkup", {"chat_id": self.ayar["sahip"], "message_id": cq["message"]["message_id"],
                                                     "reply_markup": json.dumps({"inline_keyboard": []})})
                self.yaz(yazi)
                return
            if not sahip_mi or not veri.startswith("ks:"):
                self._api("answerCallbackQuery", {"callback_query_id": cq["id"]})
                return
            _, kid, qi, oi = veri.split(":")
            qi = int(qi)
            k = self.kararlar.get(kid)
            if not k or qi in k["cevaplar"]:
                self._api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Bu soru kapandı~"})
                return
            q = k["sorular"][qi]
            if oi == "b":
                k["baska"] = qi
                self._api("answerCallbackQuery", {"callback_query_id": cq["id"]})
                self.yaz(f"✍️ Yaz bakalım, \"{q.get('question', '')[:80]}\" için cevabın ne?")
                return
            secim = (q.get("options") or [])[int(oi)].get("label")
            k["cevaplar"][qi] = secim
            self._api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "İlettim~"})
            self._api("editMessageText", {"chat_id": self.ayar["sahip"], "message_id": cq["message"]["message_id"],
                                          "text": f"❓ {q.get('question', '')}\n✅ Seçtin: {secim}"})
            log.info("karar: Dino Telegram'dan seçti: %s", secim)
        except Exception as e:
            log.info("karar düğme: %s", e)

    def _karar_yazi(self, m):
        """'✍️ Başka' dendiyse sıradaki yazı o sorunun cevabıdır."""
        metin = (m.get("text") or "").strip()
        for kid, k in list(self.kararlar.items()):
            qi = k.get("baska")
            if qi is not None and metin and qi not in k["cevaplar"]:
                k["cevaplar"][qi] = metin
                k["baska"] = None
                self.yaz("Tamam, Claude'a ilettim~ ✨")
                log.info("karar: Dino Telegram'dan yazdı: %s", metin[:80])
                return True
        return False

    def _isit(self):
        """Telegram beyni ilk açılışta ~10-20 sn sürer: önceden aç, hafızayı okusun (ilk mesaj beklemesin)."""
        import hafiza
        time.sleep(60)   # önce ses beyni ısınsın ve kalan konuşmalar hafızaya işlensin
        t = time.time()
        with self.beyin_kilit:
            hafiza.kacirilan("telegram")   # bundan sonra evde konuşulanlar Telegram beynine not olarak gider
            for _ in self.beyin.sor("(Sistem: Sakura'nın Telegram beyni yeni açıldı. HAFIZA.md'yi ve GUNLUK.md'yi oku. "
                                    "Cevap olarak sadece 'hazır' yaz.)"):
                pass
        log.info("telegram beyni hazır (%s, %.0f sn)", self.beyin.model, time.time() - t)

    def _mesaj(self, m):
        sohbet = m["chat"]["id"]
        if not self.ayar.get("sahip"):
            if m["chat"].get("type") != "private":
                return
            self.ayar["sahip"] = sohbet
            self.ayar["ad"] = m["from"].get("username") or m["from"].get("first_name")
            json.dump(self.ayar, open(AYAR, "w", encoding="utf-8"))
            log.info("telegram: sahip kaydedildi (%s)", self.ayar["ad"])
            self.yaz("Seni sahibim olarak kaydettim tatlım~ Artık buradan da konuşabiliriz! Sadece sana cevap veririm.")
            if (m.get("text") or "").startswith("/start"):
                return
        if sohbet != self.ayar["sahip"]:
            log.info("telegram: yabancı mesaj yok sayıldı (%s)", m["from"].get("username"))
            return
        self.son_konusma = time.time()
        if self._karar_yazi(m):
            return
        try:
            self._cevapla(m)
        except Exception as e:
            log.exception("telegram mesaj hatası: %s", e)
            self.yaz("Ayy, bir şey ters gitti, tekrar yazar mısın?")

    def _cevapla(self, m):
        sesli, resim = False, None
        metin = (m.get("text") or m.get("caption") or "").strip()
        if metin.startswith("/start"):
            return
        if m.get("voice"):
            sesli = True
            metin = self._sesi_yaziya(self._indir(m["voice"]["file_id"]))
            if not metin:
                self.yaz("Sesini anlayamadım canım, bir daha söyler misin?")
                return
        if m.get("photo"):
            resim = self._indir(m["photo"][-1]["file_id"])   # en büyük boy, JPEG
            yol = self._kaydet(resim, time.strftime("foto_%Y%m%d_%H%M%S.jpg"))
            metin = f"(Dino Telegram'dan bir fotoğraf gönderdi, ekte; bilgisayara kaydedildi: {yol}) " + metin
        # dosya, müzik, video: bilgisayara kaydedilir, beyne yolu söylenir (içini gerekirse kendisi açar)
        for tur in ("document", "audio", "video", "animation", "video_note"):
            d = m.get(tur)
            if not d:
                continue
            ad = d.get("file_name") or time.strftime(f"{tur}_%Y%m%d_%H%M%S") + {"video_note": ".mp4", "video": ".mp4", "animation": ".mp4", "audio": ".mp3"}.get(tur, "")
            if d.get("file_size", 0) > EN_BUYUK:
                log.info("telegram: dosya çok büyük (%s, %.0f MB)", ad, d["file_size"] / 2**20)
                metin = f"(Dino '{ad}' adlı {d['file_size'] / 2**20:.0f} MB'lık bir dosya göndermek istedi ama Telegram botları en çok 20 MB indirebiliyor; alamadın. Bunu söyle.) " + metin
            else:
                yol = self._kaydet(self._indir(d["file_id"]), ad)
                metin = f"(Dino Telegram'dan bir dosya gönderdi, bilgisayara kaydedildi: {yol}) " + metin
        metin = metin.strip()
        if not metin:
            return
        log.info("telegram%s: %s", " (sesli)" if sesli else "", metin)
        self._api("sendChatAction", {"chat_id": self.ayar["sahip"], "action": "record_voice" if sesli else "typing"})
        import sakura_ui, hafiza
        sakura_ui.gonder("konusuyor", "📱 Dino'yla konuşuyorum~", "mutlu", 3)
        istem = "[uzaktan] " + ("(sesli mesaj) " if sesli else "") + metin
        cumleler, ss = [], False
        with self.beyin_kilit:
            istem = hafiza.kacirilan("telegram") + istem
            for tur, x in self.beyin.sor(istem, resim):
                if tur == "cumle":
                    if "[ss]" in x.lower():
                        ss = True
                    ifade, sozsuz, temiz = self.temizle(x)
                    if temiz or sozsuz:
                        cumleler.append((ifade, sozsuz, temiz))
        cevap = " ".join(t for _, _, t in cumleler if t)
        hafiza.kaydet(metin, cevap, "Dino (Telegram)")
        if sesli and cevap:
            try:
                self._sesli_gonder(cumleler, cevap)
            except Exception as e:
                log.exception("telegram ses: %s", e)
                self.yaz(cevap)
        else:
            self.yaz(cevap)
        if ss:
            self._api("sendPhoto", {"chat_id": self.ayar["sahip"], "caption": "Ekranın şu an böyle~"},
                      ("photo", "ekran.jpg", self.ekran(), "image/jpeg"))

    def bekci(self, kim, jpeg):
        """5 Kas bekçi (kamera.py): Dino yokken bilgisayarın başına başkası oturdu → Telegram'a haber + kare."""
        if not (self.token and self.ayar.get("sahip")):
            return
        import hafiza
        ad = "tanımadığım biri" if kim == "?" else kim
        metin = f"🚨 Bilgisayarının başında {ad} var, sen yokken oturdu~"
        try:
            if jpeg:
                self._api("sendPhoto", {"chat_id": self.ayar["sahip"], "caption": metin}, ("photo", "kamera.jpg", jpeg, "image/jpeg"))
            else:
                self.yaz(metin)
            log.info("bekçi: %s → Telegram", ad)
            hafiza.olay("Sistem", f"(Bekçi: Dino yokken bilgisayarın başında {ad} vardı, Dino'ya Telegram'dan fotoğrafla haber verildi)")
        except Exception as e:
            log.info("bekçi: %s", e)

    def _kaydet(self, bayt, ad):
        """GELEN klasörüne kaydeder; aynı ad varsa sonuna (2), (3)... ekler. Tam yolu döndürür."""
        os.makedirs(GELEN, exist_ok=True)
        ad = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", ad).strip() or "dosya"   # Windows'ta yasak karakterler
        kok, uz = os.path.splitext(ad)
        yol, i = os.path.join(GELEN, ad), 2
        while os.path.exists(yol):
            yol, i = os.path.join(GELEN, f"{kok} ({i}){uz}"), i + 1
        with open(yol, "wb") as f:
            f.write(bayt)
        log.info("telegram: kaydedildi %s (%.0f KB)", yol, len(bayt) / 1024)
        return yol

    # ---------- ses ----------
    def _sesi_yaziya(self, bayt):
        p = subprocess.run([FFMPEG, "-v", "quiet", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
                           input=bayt, capture_output=True, creationflags=0x08000000)
        y = np.frombuffer(p.stdout, np.float32)
        if len(y) < 16000 * 0.3:
            return ""
        return self.a.yazi(y)

    def _sesli_gonder(self, cumleler, cevap):
        import random
        parca = []
        for ifade, sozsuz, t in cumleler:
            if sozsuz in self.a.sozsuz:   # [kikir]/[gul]: gerçek gülme kaydı sesli mesaja da girer
                parca += [random.choice(self.a.sozsuz[sozsuz]), np.zeros(int(24000 * 0.15), np.float32)]
            for p in (self.bol(t) if t else []):
                parca += [self.a.dogru_ses(p, self.ses_duygu.get(ifade, "A")), np.zeros(int(24000 * 0.25), np.float32)]
        y = np.concatenate(parca)
        p = subprocess.run([FFMPEG, "-v", "quiet", "-f", "f32le", "-ar", "24000", "-ac", "1", "-i", "pipe:0",
                            "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1"],
                           input=y.tobytes(), capture_output=True, creationflags=0x08000000)
        self._api("sendVoice", {"chat_id": self.ayar["sahip"], "caption": cevap[:1000]},
                  ("voice", "sakura.ogg", p.stdout, "audio/ogg"))

    # ---------- arka plan işleri ----------
    def _is_takip(self):
        """is_ver.py işi bitince Dino dışarıdaysa (PC kilitli) ya da son 1 saatte Telegram'dan konuştuysa haber verir."""
        bilinen = None
        while True:
            try:
                durum = {}
                for j in glob.glob(os.path.join(ISLER, "*.json")):
                    txt = j[:-5] + ".txt"
                    bitti = os.path.exists(txt) and open(txt, encoding="utf-8", errors="replace").read().rstrip().endswith("===BITTI===")
                    durum[j] = bitti
                if bilinen is not None and self.token and self.ayar.get("sahip"):
                    for j, bitti in durum.items():
                        if bitti and not bilinen.get(j, False) and (self.kilitli() or time.time() - self.son_konusma < 3600):
                            g = json.load(open(j, encoding="utf-8"))
                            son = [s.strip() for s in open(j[:-5] + ".txt", encoding="utf-8", errors="replace").read()
                                   .split("===BITTI===") if s.strip()]
                            ozet = son[-1].splitlines()[-1][:600] if son else ""
                            self.yaz(f"İşim bitti tatlım~ ✅\nGörev: {g.get('gorev', '')[:200]}\n{ozet}")
                            log.info("telegram: iş bitti haberi gönderildi (%s)", os.path.basename(j))
                bilinen = durum
            except Exception as e:
                log.info("telegram iş takibi: %s", e)
            time.sleep(30)
