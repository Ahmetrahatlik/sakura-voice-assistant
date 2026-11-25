# Dino'ya Telegram'dan kısa mesaj (8 Kas 2026): arka plan işleri (tamir, gelişim) asistanı yeniden başlatmadan önce
# haber vermek için. Asistandan bağımsız çalışır (anahtar ortam değişkeninden/kayıt defterinden okunur).
#   python tg_yaz.py "mesaj"
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from is_avcisi import telegram_gonder

if len(sys.argv) < 2:
    sys.exit('python tg_yaz.py "mesaj"')
print("gönderildi" if telegram_gonder(" ".join(sys.argv[1:])) else "gönderilemedi (Telegram hazır değil)")
