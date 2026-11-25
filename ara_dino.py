# Sakura Dino'yu arar (5 Kas): Telegram'a "📞 Sakura seni arıyor~" mesajı ve "Aç" düğmesi gider; Dino açınca arama
# ekranında önce Sakura konuşur. Telegram botları gerçek arama yapamadığı için böyle.
#   python ara_dino.py "<neden arıyorsun>" [kaç dakika sonra]
import os, sys, json, urllib.request

KOK = os.path.dirname(os.path.abspath(__file__))
sebep = sys.argv[1] if len(sys.argv) > 1 else ""
sonra = float(sys.argv[2]) if len(sys.argv) > 2 else 0
gizli = open(os.path.join(KOK, "arama_gizli.txt")).read().strip()
istek = urllib.request.Request("http://127.0.0.1:47622/ara-dino", json.dumps({"sebep": sebep, "sonra_dk": sonra}).encode(),
                               {"Content-Type": "application/json", "X-Gizli": gizli})
try:
    print(urllib.request.urlopen(istek, timeout=10).read().decode())
    print("Arama" + (f" {sonra:g} dakika sonra" if sonra else "") + " gönderilecek.")
except Exception as e:
    sys.exit(f"aranamadı (asistan kapalı olabilir): {e}")
