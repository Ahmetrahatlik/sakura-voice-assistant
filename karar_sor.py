# Claude Code kancası (8 Kas 2026, Dino istedi: "telefonda Claude yok, Sakura benim yerime seçsin"):
#  - PreToolUse (yalnız AskUserQuestion): soru + seçenekler Telegram'a düğmeli gider; Dino seçince kanca soruyu "reddedip"
#    cevabı gerekçe olarak Claude'a verir, Claude cevabı kullanıp devam eder.
#  - PermissionRequest (Dino: "Telegram'ımda şifre var, komut izinlerini de dahil et"): "şu komutu çalıştırayım mı" izni
#    Telegram'a "✅ İzin ver / ❌ Reddet / ✍️ Başka" diye gider; seçime göre izin verilir ya da reddedilir (Başka = yazdığı
#    talimatla reddedilir, Claude talimata göre devam eder).
# PC kilitliyken de çalışır. Dino başındaysa, asistan kapalıysa, SURE dolarsa ya da Dino PC'ye dönerse hiçbir şey
# yazmadan çıkar: soru/izin ekranda normal görünür. Kanca zaman aşımı (settings.json) SURE'den uzun olmalı.
import os, sys, json, time, urllib.request

KOK = os.path.dirname(os.path.abspath(__file__))
SURE = 10 * 60
ADRES = "http://127.0.0.1:47622/karar-sor"
IZIN_VER, REDDET = "✅ İzin ver", "❌ Reddet"


def iste(yol, govde=None, gizli=""):
    istek = urllib.request.Request(ADRES + yol, json.dumps(govde).encode() if govde is not None else None,
                                   {"Content-Type": "application/json", "X-Gizli": gizli})
    with urllib.request.urlopen(istek, timeout=60) as y:
        return json.loads(y.read())


def izin_sorusu(arac, girdi):
    """İzin isteğini Dino'nun okuyacağı tek soruya çevirir."""
    if arac == "Bash" or arac == "PowerShell":
        ayrinti = (girdi.get("description") or "") + "\n\n" + (girdi.get("command") or "")[:1500]
    elif girdi.get("file_path"):
        ayrinti = girdi["file_path"]
    elif girdi.get("url"):
        ayrinti = girdi["url"]
    else:
        ayrinti = json.dumps(girdi, ensure_ascii=False)[:800]
    return {"question": f"🔐 Claude izin istiyor: {arac}\n{ayrinti.strip()}",
            "options": [{"label": IZIN_VER, "description": "çalıştırsın / yapsın"},
                        {"label": REDDET, "description": "yapmasın"}]}


def yaz(cikti):
    # 8 Kas dersi: print() Windows'ta cp1254 ile yazıyor, "→" basılamayınca kanca sessizce çıkıyordu → ASCII JSON
    sys.stdout.write(json.dumps({"hookSpecificOutput": cikti}, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def main():
    veri = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    olay, arac, girdi = veri.get("hook_event_name"), veri.get("tool_name"), veri.get("tool_input") or {}
    if olay == "PermissionRequest":
        if arac == "AskUserQuestion":
            return   # soruları PreToolUse tarafı yapar
        sorular = [izin_sorusu(arac, girdi)]
    elif arac == "AskUserQuestion":
        sorular = girdi.get("questions") or []
    else:
        return
    if not sorular:
        return
    gizli = open(os.path.join(KOK, "arama_gizli.txt")).read().strip()
    c = iste("", {"session_id": veri.get("session_id"), "cwd": veri.get("cwd"), "questions": sorular}, gizli)
    if not c.get("bekle"):
        return
    kid, bitis = c["id"], time.time() + SURE
    while time.time() < bitis:
        time.sleep(2)
        try:
            d = iste("/" + kid, gizli=gizli)
        except Exception:
            continue
        if d.get("yok"):
            return
        if d.get("bitti"):
            if olay == "PermissionRequest":
                secim = d["cevaplar"][0]["cevap"]
                if secim == IZIN_VER:
                    yaz({"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}})
                elif secim == REDDET:
                    yaz({"hookEventName": "PermissionRequest", "decision": {
                        "behavior": "deny", "message": "Dino Telegram'dan bu izni REDDETTİ. Bunu yapma; başka bir yol düşün "
                                                       "ya da Dino PC'ye dönene kadar bu adımı bekletip başka işlere geç."}})
                else:
                    yaz({"hookEventName": "PermissionRequest", "decision": {
                        "behavior": "deny", "message": "Dino bu izin isteğine Telegram'dan şunu yazdı (talimatı olarak uygula): "
                                                       + secim}})
                return
            cevap = "; ".join(f'"{x["soru"]}" → "{x["cevap"]}"' for x in d["cevaplar"])
            yaz({"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": (
                "Dino PC başında değildi; bu soruyu Sakura üzerinden Telegram'dan KENDİSİ cevapladı. Cevapları: "
                + cevap + ". Bunu Dino'nun kendi cevabı olarak kabul et, soruyu tekrar sorma ve işe bu cevapla devam et.")})
            return
        if d.get("dino_dondu"):
            iste("/" + kid + "?kapat=dondu", gizli=gizli)
            return
    try:
        iste("/" + kid + "?kapat=sure", gizli=gizli)
    except Exception:
        pass


try:
    main()
except Exception:
    pass
sys.exit(0)
