# Claude Code Notification kancası (8 Kas 2026, Dino istedi): bir Claude oturumu soru sorunca / izin isteyince kancanın
# JSON'unu asistanın yerel sunucusuna (arama.py /karar) iletir. Dino PC başında değilse Sakura Telegram'dan haber verir.
# Kilitli PC'de ekran görüntüsü alınamadığı için soru ve seçenekler (ya da izin istenen komut) konuşma kaydından
# (transcript_path, JSONL) okunup mesaja yazılır. Asistan kapalıysa sessizce çıkar (kancayı asla bekletmez/bozmaz).
import os, sys, json, urllib.request

KOK = os.path.dirname(os.path.abspath(__file__))


def son_arac(yol, ad=None):
    """Kayıttaki en son tool_use (ad verilirse o adlı) → (ad, input). Dosyanın yalnız son ~400 KB'ı okunur."""
    with open(yol, "rb") as f:
        f.seek(0, 2)
        f.seek(max(0, f.tell() - 400_000))
        satirlar = f.read().decode("utf-8", "replace").splitlines()
    for s in reversed(satirlar):
        try:
            d = json.loads(s)
        except Exception:
            continue
        icerik = (d.get("message") or {}).get("content")
        if not isinstance(icerik, list):
            continue
        for p in reversed(icerik):
            if isinstance(p, dict) and p.get("type") == "tool_use" and (ad is None or p.get("name") == ad):
                return p.get("name"), p.get("input") or {}
    return None, {}


def ozet(veri):
    """Telegram'a yazılacak kısa açıklama; bulunamazsa kancanın kendi mesajı."""
    mesaj = veri.get("message") or ""
    yol = veri.get("transcript_path")
    if not yol or not os.path.exists(yol):
        return mesaj
    istenen = mesaj.rsplit(" use ", 1)[-1].strip() if " use " in mesaj else None
    ad, girdi = son_arac(yol, istenen)
    if ad == "AskUserQuestion":
        parca = []
        for q in girdi.get("questions") or []:
            secenek = [o.get("label", "") for o in q.get("options") or []]
            parca.append("❓ " + (q.get("question") or "").strip() + "\n" +
                         "\n".join(f"  {i}) {s}" for i, s in enumerate(secenek, 1)))
        return "\n".join(parca)[:900] or mesaj
    if ad:
        ayrinti = girdi.get("description") or girdi.get("command") or girdi.get("file_path") or girdi.get("url") or ""
        return f"{ad} izni istiyor: {str(ayrinti).strip()[:300]}" if ayrinti else mesaj
    return mesaj


try:
    veri = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    try:
        metin = ozet(veri)
    except Exception:
        metin = veri.get("message")
    gizli = open(os.path.join(KOK, "arama_gizli.txt")).read().strip()
    gonder = {k: veri.get(k) for k in ("session_id", "cwd", "notification_type", "title")}
    gonder["message"] = metin
    istek = urllib.request.Request("http://127.0.0.1:47622/karar", json.dumps(gonder).encode(),
                                   {"Content-Type": "application/json", "X-Gizli": gizli})
    urllib.request.urlopen(istek, timeout=3).read()
except Exception:
    pass
