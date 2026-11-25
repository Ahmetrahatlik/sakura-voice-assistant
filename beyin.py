# Sakura'nın beyni: sürekli açık duran bir Claude Code süreci (Max aboneliği, araçlar açık, izinler "auto").
# Mesajlar stdin'den stream-json ile gider; cevap parça parça gelir, cümle cümle dışarı verilir.
import json, os, re, time, subprocess, threading, queue

EXE = os.path.join(os.environ["APPDATA"], "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
KLASOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "beyin")
# cümle sonu işaretinden sonra BOŞLUK gelmeli: akış "deneme." diye kesilince "deneme.txt" ikiye bölünmesin
# (kalan parça blok bitince verilir). "~" de cümle bitirir (tatlı konuşma).
CUMLE_SONU = re.compile(r"(.+?[.!?…~])\s+", re.S)


class Beyin:
    def __init__(self, model="sonnet"):
        self.model = model
        self.p = None
        self.out = queue.Queue()
        self.tur = 0                # son açılıştan beri kaç soru (tazele() için)
        self.son = time.time()      # son sorunun bittiği an

    def _baslat(self):
        args = [EXE, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                "--include-partial-messages", "--model", self.model, "--permission-mode", "auto",
                # Sakura'nın "işim bitti" kancaları her cevapta çalmasın; sesli sohbette uzun düşünme gecikme yapar
                "--settings", json.dumps({"disableAllHooks": True, "alwaysThinkingEnabled": False})]
        env = dict(os.environ, MAX_THINKING_TOKENS="0")
        self.p = subprocess.Popen(args, cwd=KLASOR, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  creationflags=0x08000000)  # CREATE_NO_WINDOW
        threading.Thread(target=self._oku, args=(self.p,), daemon=True).start()

    def _oku(self, p):
        for satir in p.stdout:
            try:
                self.out.put(json.loads(satir))
            except ValueError:
                pass
        self.out.put({"type": "_kapandi"})

    def sor(self, metin, resim=None):
        """Cevabı olay olarak verir: ("cumle", metin) · ("arac", ad) · ("bitti", None)"""
        if self.p is None or self.p.poll() is not None:
            self._baslat()
        while not self.out.empty():
            self.out.get_nowait()
        icerik = metin
        if resim:  # JPEG baytları: mesaja görüntü olarak eklenir
            import base64
            icerik = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(resim).decode()}},
                      {"type": "text", "text": metin}]
        msg = {"type": "user", "message": {"role": "user", "content": icerik}}
        self.p.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        self.p.stdin.flush()
        tampon = ""
        while True:
            o = self.out.get()
            t = o.get("type")
            if t == "_kapandi":
                self.p = None
                if tampon.strip():
                    yield ("cumle", tampon.strip())
                yield ("bitti", "kapandi")
                return
            if t == "stream_event":
                e = o.get("event", {})
                if e.get("type") == "content_block_start" and e.get("content_block", {}).get("type") == "tool_use":
                    if tampon.strip():
                        yield ("cumle", tampon.strip())
                    tampon = ""
                    yield ("arac", e["content_block"].get("name", ""))
                elif e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                    tampon += e["delta"]["text"]
                    while True:
                        m = CUMLE_SONU.match(tampon)
                        if not m or len(m.group(1).strip()) < 2:
                            break
                        yield ("cumle", m.group(1).strip())
                        tampon = tampon[m.end():]
                elif e.get("type") == "content_block_stop" and tampon.strip():
                    yield ("cumle", tampon.strip())
                    tampon = ""
            elif t == "result":
                if tampon.strip():
                    yield ("cumle", tampon.strip())
                self.tur += 1
                self.son = time.time()
                yield ("bitti", o.get("subtype"))
                return

    def kapat(self):
        if self.p and self.p.poll() is None:
            self.p.kill()

    def tazele(self, isitma):
        """5 Kas (Dino onayladı): süreç açık kaldıkça bütün sohbet (ekran/kamera resimleri dahil) bağlamda birikir ve ilk söz
        yavaşlar. Boş bir anda süreç kapatılıp yenisi açılır, `isitma` mesajıyla (hafıza + bugünün son konuşmaları) ısıtılır.
        Çağıran beynin kilidini tutmalı."""
        p = self.p
        self.kapat()
        if p:
            try:
                p.wait(10)
            except Exception:
                pass
            time.sleep(0.5)          # eski okuyucunun "_kapandi" olayı kuyruğa düşsün, sonra temizlenir
        while not self.out.empty():
            self.out.get_nowait()
        self.p = None
        for _ in self.sor(isitma):
            pass
        self.tur = 0
