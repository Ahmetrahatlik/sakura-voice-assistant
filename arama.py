# "Sakura'yı Ara" (5 Kas 2026): Telegram'daki bot menüsünde bir düğme; basınca Telegram içinde bir arama ekranı (Mini App)
# açılır, Dino konuşur, Sakura evdeki gibi sesle cevap verir. Telegram botları gerçek arama alamadığı için bu yol seçildi.
# - Sunucu: aiohttp, 127.0.0.1:47622 (asistanın içinde ayrı iş parçacığı). Sayfa arama.html, ses WebSocket /ws.
# - Dışarıya açma: cloudflared "quick tunnel" (ücretsiz, hesapsız, adres her açılışta değişir) → bot menü düğmesi
#   (setChatMenuButton) her açılışta yeni adrese güncellenir.
# - Güvenlik: sayfa Telegram'ın imzalı initData'sını gönderir; bot anahtarıyla HMAC doğrulanır ve kullanıcı = sahip olmalı.
# - Akış (yarı çift yönlü, evdeki gibi): telefon 16 kHz PCM16 gönderir → silero VAD konuşmayı keser → Whisper → beyin
#   ([uzaktan] (telefonda)) → XTTS 24 kHz PCM16 parça parça telefona. Sakura konuşurken telefon mikrofonu göndermez.
import os, re, json, time, hmac, hashlib, asyncio, threading, subprocess, logging, urllib.parse
import numpy as np, torch

KOK = os.path.dirname(os.path.abspath(__file__))
PORT = 47622
KESME_SURE = 0.5      # sn: Sakura konuşurken bu kadar kesintisiz konuşma duyulursa söz kesme denetlenir
KESME_FARK = 0.05     # ses izi Dino'ya Sakura'dan en az bu kadar daha çok benzemeli (hoparlör yankısı kesmesin)
KESME_DINO = 0.45     # ve Dino'ya en az bu kadar benzemeli (telefonda Dino ~0,6)
CLOUDFLARED = next((p for p in [r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe"]
                    if os.path.exists(p)), "cloudflared")
SR = 16000
log = logging.getLogger()


def init_dogrula(init_data, token, sahip):
    """Telegram WebApp initData imzası (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)."""
    try:
        alan = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        imza = alan.pop("hash")
        veri = "\n".join(f"{k}={v}" for k, v in sorted(alan.items()))
        gizli = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(hmac.new(gizli, veri.encode(), hashlib.sha256).hexdigest(), imza):
            return False
        if time.time() - int(alan.get("auth_date", 0)) > 86400:
            return False
        return json.loads(alan["user"])["id"] == sahip
    except Exception:
        return False


class Arama:
    def __init__(self, asistan, kopru, temizle, bol, ses_duygu):
        self.a, self.k, self.temizle, self.bol, self.ses_duygu = asistan, kopru, temizle, bol, ses_duygu
        self.adres = None
        self._p = None          # cloudflared süreci
        self.acik_cagri = 0     # şu an süren arama sayısı (tünel bekçisi arama sırasında tüneli yenilemez)
        self.bekleyen = None   # Sakura Dino'yu aradıysa: {"sebep", "zaman"} (Dino "Aç"a basınca ilk o konuşur)
        self.gizli = os.urandom(16).hex()   # ara_dino.py'nin anahtarı: tünelden gelen istek bilemez
        open(os.path.join(KOK, "arama_gizli.txt"), "w").write(self.gizli)
        threading.Thread(target=self._sunucu, daemon=True).start()
        threading.Thread(target=self._tunel, daemon=True).start()
        threading.Thread(target=self._tunel_bekci, daemon=True).start()

    def sakura_izi(self):
        """Sakura'nın kendi sesinin izi (hazır cümle kayıtlarından, 24→16 kHz). Söz kesmede yankıyı Dino'dan ayırmak için."""
        if getattr(self, "_sakura_izi", None) is None:
            try:
                import glob
                from scipy.signal import resample_poly
                y = np.concatenate([np.load(f) for f in sorted(glob.glob(os.path.join(KOK, "hazir_ses", "*.npy")))[:12]])
                v = self.a.izi.iz(resample_poly(y, 2, 3).astype(np.float32))
                self._sakura_izi = v / np.linalg.norm(v)
                log.info("arama: Sakura'nın ses izi hazır (Dino'ya benzerlik %.2f)",
                         float(self._sakura_izi @ self.a.izi.kisiler["Dino"]) if "Dino" in self.a.izi.kisiler else -1)
            except Exception as e:
                log.info("arama: Sakura ses izi yok: %s", e)
                self._sakura_izi = None
        return self._sakura_izi

    # ---------- tünel ve bot düğmesi ----------
    def _tunel(self):
        # 5 Kas: asistan zorla kapatılınca (durdur.ps1) tüneli açık kalıyordu; 8 tane birikmişti. Açılışta eskileri kapat.
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | Where-Object { $_.CommandLine -like "
                            f"'*127.0.0.1:{PORT}*' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"],
                           capture_output=True, timeout=30, creationflags=0x08000000)
        except Exception as e:
            log.info("arama: eski tüneller kapatılamadı: %s", e)
        while True:
            try:
                p = subprocess.Popen([CLOUDFLARED, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=0x08000000)
                self._p = p
                for satir in iter(p.stderr.readline, b""):
                    m = re.search(rb"https://[a-z0-9-]+\.trycloudflare\.com", satir)
                    if m and not self.adres:
                        self.adres = m.group(0).decode()
                        log.info("arama: tünel açık %s", self.adres)
                        threading.Thread(target=self._dugme, daemon=True).start()
                p.wait()
                log.info("arama: tünel kapandı (%s), yeniden açılıyor", p.returncode)
            except Exception as e:
                log.info("arama tünel: %s", e)
            self.adres = None
            time.sleep(15)

    def _tunel_bekci(self):
        """8 Kas: PC uykudan dönünce cloudflared süreci yaşıyor ama quick tunnel adresi ölüyordu (DNS: adres yok); Sakura
        fark etmediği için 'Sakura'yı Ara' ölü adrese gidiyordu. Tünel 2 dk'da bir dışarıdan (Cloudflare üzerinden) yoklanır;
        3 kez üst üste ulaşılamazsa cloudflared kapatılır, _tunel yenisini açar ve bot düğmesini günceller."""
        import ssl, certifi, urllib.request
        bag = ssl.create_default_context(cafile=certifi.where())
        hata, son = 0, time.time()
        while True:
            time.sleep(30 if hata else 120)
            simdi = time.time()
            if simdi - son > 300:
                log.info("arama: uyku/uzun duraklama sonrası (%d dk), tünel yoklanıyor", (simdi - son) / 60)
                time.sleep(20)   # ağ otursun
            son = time.time()
            adres = self.adres
            if not adres or self.acik_cagri:
                hata = 0
                continue
            try:
                with urllib.request.urlopen(urllib.request.Request(adres + "/", headers={"User-Agent": "sakura-tunel-bekci"}),
                                            timeout=20, context=bag) as y:
                    ok = y.status == 200
            except Exception as e:
                ok, neden = False, e
                # 8 Kas 09:43: evdeki DNS (modem/ISS) bazen yeni adresi çözemiyor ("getaddrinfo failed") ama tünel sağlam.
                # Yalnız DNS hatasıysa Cloudflare DNS'ine (1.1.1.1, DoH) sor: adres orada varsa tünel yaşıyor sayılır.
                # Gerçek ölüm 8 Kas'ta tam buydu: adres Cloudflare DNS'inde de yoktu (NXDOMAIN).
                if "getaddrinfo" in str(e) or "11001" in str(e) or "11002" in str(e):
                    try:
                        host = urllib.parse.urlparse(adres).hostname
                        with urllib.request.urlopen(urllib.request.Request(
                                "https://1.1.1.1/dns-query?name=" + host + "&type=A",
                                headers={"accept": "application/dns-json"}), timeout=15, context=bag) as y:
                            cvp = json.loads(y.read())
                        if cvp.get("Status") == 0 and cvp.get("Answer"):
                            ok = True
                            log.info("arama: yerel DNS tüneli çözemedi ama Cloudflare DNS'te var, tünel sağlam sayıldı")
                        else:
                            neden = f"Cloudflare DNS: adres yok (Status {cvp.get('Status')})"
                    except Exception as e2:
                        neden = f"{e} / DoH: {e2}"
            if ok:
                if hata:
                    log.info("arama: tünel yeniden ulaşılabilir")
                hata = 0
                continue
            hata += 1
            log.info("arama: tünele ulaşılamadı (%d/3): %s", hata, str(neden)[:120])
            if hata >= 3 and self.adres == adres and self._p:
                log.info("arama: tünel ölmüş, yenisi açılıyor")
                self.tunel_yenileme = getattr(self, "tunel_yenileme", []) + [time.time()]   # sağlık bekçisi sayar
                hata = 0
                try:
                    self._p.kill()
                except Exception as e:
                    log.info("arama: cloudflared kapatılamadı: %s", e)

    def _dugme(self):
        """Bot sohbetindeki menü düğmesi yeni tünel adresine güncellenir (anahtar ve sahip gelene kadar bekler)."""
        while not (self.k.token and self.k.ayar.get("sahip")):
            time.sleep(5)
        for _ in range(10):
            try:
                self.k._api("setChatMenuButton", {"chat_id": self.k.ayar["sahip"], "menu_button": json.dumps(
                    {"type": "web_app", "text": "📞 Sakura'yı Ara", "web_app": {"url": self.adres + "/"}})})
                log.info("arama: bot düğmesi güncellendi")
                return
            except Exception as e:
                log.info("arama düğme: %s", e)
                time.sleep(10)

    # ---------- web sunucusu ----------
    def _sunucu(self):
        from aiohttp import web
        app = web.Application()
        app.router.add_get("/", lambda r: web.FileResponse(os.path.join(KOK, "arama.html"), headers={"Cache-Control": "no-store"}))
        app.router.add_get("/ws", self._ws)
        app.router.add_static("/resim/", os.path.join(KOK, "arama_resim"))   # Sakura'nın kareleri (Sakura.exe export)
        app.router.add_post("/ara-dino", self._ara_istek)                   # ara_dino.py (yalnız bu bilgisayardan)
        app.router.add_post("/karar", self._karar_istek)                    # karar_haber.py (Claude kancası, yalnız yerel)
        app.router.add_post("/karar-sor", self._karar_sor)                  # karar_sor.py (soru kancası, yalnız yerel)
        app.router.add_get("/karar-sor/{kid}", self._karar_sor_durum)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        self.loop_is = threading.current_thread()
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        loop.run_until_complete(web.TCPSite(runner, "127.0.0.1", PORT).start())
        log.info("arama: sunucu 127.0.0.1:%d", PORT)
        loop.run_forever()

    # ---------- Sakura Dino'yu arar ----------
    async def _ara_istek(self, istek):
        from aiohttp import web
        # tünelden (internetten) gelen istek Cloudflare başlıkları taşır: reddedilir; yerel istek gizli anahtarı bilmeli
        if istek.headers.get("Cf-Ray") or istek.headers.get("Cf-Connecting-Ip") or istek.headers.get("X-Gizli") != self.gizli:
            return web.Response(status=403)
        d = await istek.json()
        sonra = float(d.get("sonra_dk", 0) or 0)
        threading.Timer(sonra * 60, self.dino_ara, args=(d.get("sebep", ""),)).start()
        return web.json_response({"tamam": True, "dakika_sonra": sonra})

    # ---------- Claude karar bekliyor (8 Kas, Dino istedi) ----------
    # Bir Claude Code oturumu soru sorunca / izin isteyince Notification kancası (karar_haber.py) buraya yazar. Dino PC
    # başında değilse (kilitli ya da kamera onu KARAR_YOK sn'dir görmüyor) Telegram'a haber gider; kilit açıksa ekran
    # görüntüsü de. Dino cevabı telefondaki Claude uygulamasından (Remote Control) verir. Aynı oturum için KARAR_ARA'da bir.
    async def _karar_istek(self, istek):
        from aiohttp import web
        if istek.headers.get("Cf-Ray") or istek.headers.get("Cf-Connecting-Ip") or istek.headers.get("X-Gizli") != self.gizli:
            return web.Response(status=403)
        d = await istek.json()
        threading.Thread(target=self.karar_haber, args=(d,), daemon=True).start()
        return web.json_response({"tamam": True})

    def dino_yok(self, sure=180):
        """Dino PC başında değil mi: kilitli ya da kamera açıkken onu `sure` sn'dir görmüyor."""
        if self.k.kilitli():
            return True
        kam = getattr(self.a, "kamera", None)
        return kam is not None and kam.acik() and time.time() - kam.son_dino > sure

    def _yerel_mi(self, istek):
        return not (istek.headers.get("Cf-Ray") or istek.headers.get("Cf-Connecting-Ip")) and \
            istek.headers.get("X-Gizli") == self.gizli

    async def _karar_sor(self, istek):
        """8 Kas: soru kancası. Dino başındaysa {"bekle": false} (soru PC'de normal görünür); değilse Telegram düğmeleri."""
        from aiohttp import web
        if not self._yerel_mi(istek):
            return web.Response(status=403)
        d = await istek.json()
        sorular = d.get("questions") or []
        if not sorular or not self.dino_yok() or not (self.k.token and self.k.ayar.get("sahip")):
            return web.json_response({"bekle": False})
        kid = os.urandom(3).hex()
        yer = os.path.basename((d.get("cwd") or "").rstrip("\\/")) or "?"
        log.info("karar: soru Telegram'a soruluyor (%s, %s, %d soru)", kid, yer, len(sorular))
        def gonder():
            try:
                if not self.k.kilitli():
                    self.k._api("sendPhoto", {"chat_id": self.k.ayar["sahip"], "caption": "Ekran şu an böyle~"},
                                ("photo", "ekran.jpg", self.k.ekran(), "image/jpeg"))
                self.k.karar_baslat(kid, sorular, yer)
            except Exception as e:
                log.info("karar: Telegram'a sorulamadı: %s", e)
                self.k.kararlar.pop(kid, None)
        await asyncio.get_running_loop().run_in_executor(None, gonder)
        if kid not in self.k.kararlar:
            return web.json_response({"bekle": False})
        return web.json_response({"bekle": True, "id": kid})

    async def _karar_sor_durum(self, istek):
        from aiohttp import web
        if not self._yerel_mi(istek):
            return web.Response(status=403)
        kid = istek.match_info["kid"]
        if istek.query.get("kapat"):
            neden = {"sure": "⏰ Süre doldu, soruyu PC'de bekletiyorum; dönünce oradan seçersin~",
                     "dondu": "PC başına döndün, soruyu ekranda görürsün~"}.get(istek.query["kapat"], "")
            await asyncio.get_running_loop().run_in_executor(None, self.k.karar_kapat, kid, neden)
            return web.json_response({"tamam": True})
        durum = self.k.karar_durum(kid) or {"bitti": False, "yok": True}
        durum["dino_dondu"] = not self.dino_yok(sure=60) and not durum.get("bitti")
        if durum.get("bitti"):
            self.k.kararlar.pop(kid, None)
        return web.json_response(durum)

    def karar_haber(self, d):
        KARAR_YOK, KARAR_ARA = 180, 10 * 60
        tur = d.get("notification_type") or ""
        mesaj = (d.get("message") or "").strip()
        oturum = d.get("session_id") or ""
        yer = os.path.basename((d.get("cwd") or "").rstrip("\\/")) or "?"
        log.info("karar: kanca geldi (%s, %s): %s", tur or "-", yer, mesaj[:120])
        if tur == "idle_prompt" or "waiting for your input" in mesaj.lower():
            return   # iş bitti/boşta: zaten Stop kancası var
        kilitli = self.k.kilitli()
        kam = getattr(self.a, "kamera", None)
        gormuyor = kam is not None and kam.acik() and time.time() - kam.son_dino > KARAR_YOK
        if not (kilitli or gormuyor):
            return   # Dino başında: masaüstündeki Sakura zaten tepki veriyor
        if not (self.k.token and self.k.ayar.get("sahip")):
            return
        son = getattr(self, "_karar_son", {})
        self._karar_son = son
        anahtar = (oturum, mesaj)
        if time.time() - son.get(anahtar, 0) < KARAR_ARA:
            return
        son[anahtar] = time.time()
        metin = (f"🤔 Claude senden karar bekliyor~\n📁 {yer}\n💬 {mesaj or 'bir soru soruyor'}\n\n"
                 "Telefondaki Claude uygulamasını aç → Code → oturuma gir, oradan seç ✨")
        try:
            if not kilitli:
                self.k._api("sendPhoto", {"chat_id": self.k.ayar["sahip"], "caption": metin[:1000]},
                            ("photo", "ekran.jpg", self.k.ekran(), "image/jpeg"))
            else:
                self.k.yaz(metin + "\n(PC kilitli, ekran görüntüsü alamadım)")
            log.info("karar: Dino'ya Telegram'dan haber verildi (%s)", "kilitli" if kilitli else "ekran görüntülü")
        except Exception as e:
            log.info("karar: Telegram'a gönderilemedi: %s", e)

    def dino_ara(self, sebep):
        """Telegram'a "Sakura arıyor" mesajı + "Aç" düğmesi (botlar gerçek arama yapamıyor)."""
        if not (self.adres and self.k.token and self.k.ayar.get("sahip")):
            log.info("arama: Dino aranamadı (tünel/Telegram hazır değil)")
            return
        self.bekleyen = {"sebep": sebep, "zaman": time.time()}
        log.info("arama: Sakura Dino'yu arıyor (%s)", sebep)
        self.k._api("sendMessage", {"chat_id": self.k.ayar["sahip"], "text": "📞 Sakura seni arıyor~",
                                    "reply_markup": json.dumps({"inline_keyboard": [[{"text": "📞 Aç",
                                                               "web_app": {"url": self.adres + "/?arayan=1"}}]]})})

    async def _ws(self, istek):
        from aiohttp import web, WSMsgType
        ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4 << 20)
        await ws.prepare(istek)
        cagri = None
        async for m in ws:
            if m.type == WSMsgType.TEXT:
                d = json.loads(m.data)
                if d.get("tip") == "giris":
                    if not init_dogrula(d.get("initData", ""), self.k.token or "", self.k.ayar.get("sahip")):
                        log.info("arama: imza doğrulanamadı, bağlantı kapatıldı")
                        await ws.send_json({"tip": "hata", "metin": "Bu arama sadece Dino için~"})
                        await ws.close()
                        return ws
                    cagri = Cagri(self, ws, asyncio.get_running_loop())
                    self.acik_cagri += 1
                    log.info("arama: Dino aradı")
                    import sakura_ui
                    sakura_ui.gonder("konusuyor", "📞 Dino'yla telefondayım~", "nese", 3)
                    b = self.bekleyen
                    if d.get("arayan") and b and time.time() - b["zaman"] < 3600:
                        # Sakura aradı, Dino açtı: önce Sakura konuşur
                        self.bekleyen = None
                        cagri.mesgul = True
                        await ws.send_json({"tip": "durum", "durum": "dusunuyor"})
                        threading.Thread(target=cagri.konus, args=(None, "[uzaktan] (Sen Dino'yu Telegram'dan aradın, o da "
                                         "açtı. Selam ver ve neden aradığını kısaca söyle. Arama sebebi: " + (b["sebep"] or
                                         "onu özledin") + ")"), daemon=True).start()
                    else:
                        await ws.send_json({"tip": "durum", "durum": "dinliyor"})
                elif cagri and d.get("tip") == "dinliyorum":
                    cagri.dinlemeye_don()
            elif m.type == WSMsgType.BINARY and cagri:
                cagri.ses(np.frombuffer(m.data, np.int16).astype(np.float32) / 32768)
        if cagri:
            cagri.bitti = True
            self.acik_cagri = max(0, self.acik_cagri - 1)
            log.info("arama: kapandı")
        return ws


class Cagri:
    """Tek bir arama: gelen sesi konuşmalara böler, her konuşmayı ayrı iş parçacığında cevaplar."""
    PARCA = 512

    def __init__(self, arama, ws, loop):
        from silero_vad import load_silero_vad
        self.ar, self.ws, self.loop = arama, ws, loop
        self.vad = load_silero_vad()
        self.tampon = np.zeros(0, np.float32)
        self.cur, self.once, self.aktif, self.sessiz = [], [], False, 0
        self.mesgul = False   # Sakura düşünüyor/konuşuyor: gelen ses yalnız söz kesme için dinlenir
        self.bitti = False
        # 5 Kas söz kesme (Dino onayladı): Sakura konuşurken/düşünürken Dino konuşursa susar ve onu dinler. Hoparlörde
        # Sakura'nın kendi sesi de mikrofona girer: kesmek için ses izinin Sakura'dan çok Dino'ya benzemesi gerekir.
        self.nesil = 0        # her söz kesmede artar: eski cevabın kalan sesi gönderilmez
        self.kesildi_not = False
        self._kesme_sifirla()

    def _kesme_sifirla(self):
        self.k_tampon, self.k_once, self.k_say, self.k_son = np.zeros(0, np.float32), [], 0, 0.0

    def gonder(self, veri):
        if self.bitti:
            return
        f = self.ws.send_bytes(veri) if isinstance(veri, bytes) else self.ws.send_json(veri)
        try:
            if threading.current_thread() is self.ar.loop_is:
                # sunucunun kendi döngüsünden çağrıldı (ses() içinde): beklersek kilitlenir (5 Kas: 15 sn gecikme)
                self.loop.create_task(f)
                return
            asyncio.run_coroutine_threadsafe(f, self.loop).result(15)
        except Exception as e:
            log.info("arama gönderme: %s", e)

    def dinlemeye_don(self):
        if self.aktif and not self.mesgul:
            return   # söz kesmeden sonra Dino konuşurken telefonun gecikmiş "dinliyorum"u kaydı bozmasın
        self._kesme_sifirla()
        self.mesgul = False
        self.vad.reset_states()
        self.tampon, self.cur, self.once, self.aktif, self.sessiz = np.zeros(0, np.float32), [], [], False, 0

    def _kesme_dinle(self, y):
        a = self.ar.a
        self.k_tampon = np.concatenate([self.k_tampon, y])
        while len(self.k_tampon) >= self.PARCA:
            p, self.k_tampon = self.k_tampon[:self.PARCA], self.k_tampon[self.PARCA:]
            olas = self.vad(torch.from_numpy(p.copy()), SR).item()
            self.k_once = (self.k_once + [p])[-45:]           # son ~1,4 sn
            self.k_say = self.k_say + 1 if olas > 0.6 else max(0, self.k_say - 1)
            if self.k_say * self.PARCA / SR < KESME_SURE or time.time() - self.k_son < 0.8:
                continue
            self.k_son = time.time()
            sakura = self.ar.sakura_izi()
            dino = a.izi.kisiler.get("Dino")
            if sakura is None or dino is None:
                return
            v = a.izi.iz(np.concatenate(self.k_once[-32:]))      # ~1 sn
            v = v / (np.linalg.norm(v) + 1e-9)
            d, k = float(v @ dino), float(v @ sakura)
            kes = d - k > KESME_FARK and d > KESME_DINO
            log.info("arama: söz kesme? Dino %.2f Sakura %.2f → %s", d, k, "KES" if kes else "hayır")
            if kes:
                self._kes()
                return

    def _kes(self):
        """Dino araya girdi: Sakura susar, duyulan baştaki ses yeni konuşmanın başı olur."""
        self.nesil += 1
        self.kesildi_not = True
        self.gonder({"tip": "sus"})
        self.vad.reset_states()
        self.mesgul, self.aktif, self.cur, self.sessiz = False, True, list(self.k_once), 0
        self.tampon = np.zeros(0, np.float32)
        self._kesme_sifirla()
        log.info("arama: Dino sözünü kesti")

    def ses(self, y):
        if self.mesgul:
            self._kesme_dinle(y)
            return
        self.tampon = np.concatenate([self.tampon, y])
        while len(self.tampon) >= self.PARCA:
            p, self.tampon = self.tampon[:self.PARCA], self.tampon[self.PARCA:]
            olas = self.vad(torch.from_numpy(p.copy()), SR).item()
            if not self.aktif:
                self.once = (self.once + [p])[-10:]
                if olas > 0.5:
                    self.aktif, self.cur, self.sessiz = True, list(self.once), 0
                continue
            self.cur.append(p)
            self.sessiz = self.sessiz + 1 if olas < 0.35 else 0
            if self.sessiz * self.PARCA / SR >= 0.7 or len(self.cur) * self.PARCA / SR > 25:
                konusma = np.concatenate(self.cur)
                self.aktif, self.cur, self.once = False, [], []
                self.vad.reset_states()
                if len(konusma) >= SR * 0.4:
                    self.mesgul = True
                    self.gonder({"tip": "durum", "durum": "dusunuyor"})
                    threading.Thread(target=self._cevapla, args=(konusma,), daemon=True).start()
                    return

    def _cevapla(self, y):
        self.konus(y)

    def konus(self, y, istem=None):
        """y: Dino'nun sesi (yazıya çevrilip beyne gider); istem: doğrudan beyne giden metin (Sakura aradığında)."""
        a, ar = self.ar.a, self.ar
        try:
            metin = ""
            if y is not None:
                metin = a.yazi(y)
                if not metin:
                    self.gonder({"tip": "durum", "durum": "dinliyor"})
                    self.dinlemeye_don()
                    return
                log.info("arama: Dino: %s", metin)
                def _izi_yaz(y=y):   # 5 Kas: telefonda ses tanıma yalnız ölçülüyor (eşikler farklı olabilir)
                    try:
                        kim, skor = a.izi.kim(y)
                        log.info("arama: ses izi %s %s", kim, {k: round(v, 2) for k, v in skor.items()})
                    except Exception:
                        pass
                # 8 Kas: yalnız günlüğe yazıldığı hâlde cevabı bekletiyordu (açılıştan sonraki ilk aramada 24 sn!) → arka planda
                threading.Thread(target=_izi_yaz, daemon=True).start()
                self.gonder({"tip": "dino", "metin": metin})
                istem = "[uzaktan] (telefonda, sesli konuşuyorsunuz; kısa konuş) " + metin
            soylenen, ilk, son_ifade = [], True, "mutlu"
            t0 = time.time()
            benim = self.nesil                       # söz kesilince (nesil artar) bu cevabın kalanı gönderilmez
            susturuldu = lambda: self.bitti or self.nesil != benim
            if self.kesildi_not:
                self.kesildi_not = False
                istem = "(Dino az önce araya girip sözünü kesti; yarım kalan cevabını tekrarlama, ona cevap ver.) " + istem
            import hafiza
            with a.beyin_kilit:
                istem = hafiza.kacirilan("ses") + istem   # arama ses beyniyle (haiku); Telegram'da konuşulanlar not olarak
                for tur, x in a.beyin.sor(istem):
                    if tur != "cumle" or susturuldu():
                        continue
                    ifade, sozsuz, t = ar.temizle(x)
                    ifade = son_ifade = ifade or son_ifade
                    if sozsuz:
                        self.gonder({"tip": "ifade", "ifade": "nese"})
                    if sozsuz in a.sozsuz:
                        import random
                        self._sesi_gonder(random.choice(a.sozsuz[sozsuz]))
                    if not t:
                        continue
                    soylenen.append(t)
                    self.gonder({"tip": "sakura", "metin": t, "ifade": ifade})
                    parcalar = ar.bol(t)
                    if ilk and getattr(a, "ilk_bol", None):
                        parcalar[:1] = a.ilk_bol(parcalar[0])   # ilk parça kısa: ses daha erken başlar
                    for p in parcalar:
                        if susturuldu():
                            break
                        # ilk parça kontrolsüz (çabuk başlasın), sonrakiler Whisper ile kendini dinler
                        # 5 Kas: telefonda en çok 2 deneme (3 deneme 15:40'ta aramayı yavaşlattı)
                        wav = a.dogru_ses(p, ar.ses_duygu.get(ifade, "A"), kontrol=not ilk, en_cok=2)
                        if susturuldu():
                            break
                        self._sesi_gonder(wav)
                        if ilk:
                            log.info("arama: ilk ses %.1f sn", time.time() - t0)
                        ilk = False
            hafiza.kaydet(metin or "(Sakura Dino'yu aradı, Dino açtı)", " ".join(soylenen) +
                          (" (Dino sözünü kesti)" if self.nesil != benim else ""), "Dino (telefon)")
        except Exception as e:
            log.exception("arama cevap: %s", e)
            benim = self.nesil
        if self.nesil == benim:
            self.gonder({"tip": "bitti"})   # telefon sesleri çalınca "dinliyorum" der, dinlemeye döneriz

    def _sesi_gonder(self, wav):
        pcm = (np.clip(wav, -1, 1) * 32767).astype(np.int16).tobytes()
        self.gonder(pcm)
