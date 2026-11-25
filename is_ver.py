# Sakura'nın arka plana iş vermesi: ayrı bir Claude Code oturumu başlatır, Sakura'nın bekleme sürecinden bağımsız yaşar.
# Kullanım:
#   python is_ver.py "<görev>" [klasör]           yeni iş
#   python is_ver.py --devam <iş adı|son> "<talimat>"  aynı oturumda kaldığı yerden devam (Claude öncekileri hatırlar)
#   python is_ver.py --liste                       son işler: ad, durum, görev, son özet
# Her işin kaydı isler\<ad>.txt (çıktı) ve isler\<ad>.json (görev, klasör, oturum kimliği). Biten işin sonunda ===BITTI=== olur.
# İş bitince Claude'un Stop kancası Sakura'ya "İşim bitti" der.
import os, sys, time, json, uuid, glob, subprocess

KOK = os.path.dirname(os.path.abspath(__file__))
ISLER = os.path.join(KOK, "isler")
EXE = os.path.join(os.environ["APPDATA"], "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
VARSAYILAN = os.environ.get("SAKURA_IS_KLASORU", KOK)   # uzun işlerin varsayılan çalışma klasörü
BITTI = "===BITTI==="
os.makedirs(ISLER, exist_ok=True)


def calistir(arglar, istem, kayit, klasor):
    # görev metni komut satırına değil dosyaya yazılır (tırnak, &, | gibi karakterler cmd'yi bozmasın), stdin'den okunur
    istem_dosya = kayit[:-4] + ".istem.txt"
    open(istem_dosya, "w", encoding="utf-8").write(istem)
    komut = 'cmd /c ""%s" -p %s --permission-mode auto < "%s" >> "%s" 2>&1 & echo. >> "%s" & echo %s >> "%s""' % (
        EXE, arglar, istem_dosya, kayit, kayit, BITTI, kayit)
    # Uzun yaşasın diye WMI ile başlatılır (Claude'un iş nesnesine bağlı kalmaz)
    ps = "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=%s; CurrentDirectory=%s} | Out-Null" % (
        "'" + komut.replace("'", "''") + "'", "'" + klasor.replace("'", "''") + "'")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)


def isler():
    out = []
    for j in sorted(glob.glob(os.path.join(ISLER, "*.json")), reverse=True):
        m = json.load(open(j, encoding="utf-8"))
        txt = open(j[:-5] + ".txt", encoding="utf-8", errors="replace").read()
        m["ad"] = os.path.basename(j)[:-5]
        m["durum"] = "bitti" if txt.rstrip().endswith(BITTI) else "sürüyor"
        parca = [p.strip() for p in txt.split(BITTI) if p.strip()]
        m["ozet"] = parca[-1].splitlines()[-1][:300] if m["durum"] == "bitti" and parca else ""
        out.append(m)
    return out


if sys.argv[1] == "--liste":
    for m in isler()[:8]:
        print("%s | %s | %s%s" % (m["ad"], m["durum"], m["gorev"][:120], (" | son: " + m["ozet"]) if m["ozet"] else ""))
elif sys.argv[1] == "--devam":
    hepsi = isler()
    m = hepsi[0] if sys.argv[2] == "son" else next(x for x in hepsi if x["ad"] == sys.argv[2])
    if m["durum"] != "bitti":
        sys.exit("bu iş hâlâ sürüyor, bitmesini bekle: " + m["ad"])
    kayit = os.path.join(ISLER, m["ad"] + ".txt")
    with open(kayit, "a", encoding="utf-8") as f:
        f.write("\n\nDEVAM (" + time.strftime("%H:%M") + "): " + sys.argv[3] + "\n\n")
    istem = sys.argv[3] + "\n\n(Dino bu işe Sakura üzerinden devam etmeni istedi. Bitince ne yaptığını iki üç cümleyle Türkçe özetle.)"
    calistir("--resume " + m["oturum"], istem, kayit, m["klasor"])  # oturum aynı klasörden sürdürülmeli
    print("devam ediyor:", kayit)
else:
    gorev = sys.argv[1]
    klasor = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].strip() else VARSAYILAN
    ad = time.strftime("%Y%m%d-%H%M%S")
    oturum = str(uuid.uuid4())
    kayit = os.path.join(ISLER, ad + ".txt")
    with open(kayit, "w", encoding="utf-8") as f:
        f.write("GÖREV: " + gorev + "\nKLASÖR: " + klasor + "\n\n")
    json.dump({"gorev": gorev, "klasor": klasor, "oturum": oturum, "baslangic": ad}, open(kayit[:-4] + ".json", "w", encoding="utf-8"), ensure_ascii=False)
    istem = gorev + "\n\n(Bu görev Dino'nun Sakura asistanına verdiği bir iş. Bitince ne yaptığını iki üç cümleyle Türkçe özetle.)"
    calistir("--session-id " + oturum, istem, kayit, klasor)
    print("başladı:", ad)
