"""Gemini sonuçlarından yalnız göz/ağız(/kaş) bölgesini yeşil büst paneline (384×512) yumuşak maskeyle yapıştırır."""
import os, sys
import numpy as np
from PIL import Image, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_parca
D = os.environ.get('SAKURA_CIZIM_KLASORU', 'cizimler').rstrip('/\\') + '/'   # karakter çizimlerinin klasörü
OUT = sys.argv[1]
base = Image.open(os.path.expanduser('~/.claude/sakura-deneme/src/poses/yesil/sheet.png')).convert('RGB').crop((0, 0, 384, 512))
eyes, d, mouth = sd_parca.find_parts(np.array(base))
mouth = (mouth[0], mouth[1], mouth[2] * 1.3 + 4, mouth[3] * 1.3 + 4)
JOBS = {"goz_kapali": ("1-goz-kapali", "goz"), "agiz_kapali": ("2-agiz-kapali", "agiz"), "ifade_dusunce": ("3-dusunce", "kas+agiz"),
        "ifade_nese": ("4-nese", "goz+agiz"), "ifade_mutlu": ("5-mutlu", "kas+agiz"), "ifade_gurur": ("6-gurur", "goz+kas+agiz"),
        "ifade_sevgi": ("7-sevgi", "goz+yanak+agiz"), "ifade_goz_kirp": ("8-goz-kirp", "goz_sag+agiz"),
        "ifade_utangac": ("9-utangac", "kas+yanak+agiz"), "ifade_uzgun": ("10-uzgun", "kas+agiz"),
        "ifade_uykulu": ("11-uykulu", "goz+agiz"), "ifade_sinirli": ("12-sinirli", "kas+agiz"),
        "ifade_saskin": ("13-saskin", "kas+agiz"), "agiz_o": ("13-saskin", "agiz"), "agiz_genis": ("15-agiz-genis", "agiz"),
        "ifade_agla": ("16-agla", "goz+kas+yanak+yas+agiz")}
ONLY = sys.argv[2:]  # verilirse yalnız bu adlar
B = np.asarray(base, float)
LINE = float(os.environ.get('LINE', '1.0'))
MINF = int(os.environ.get('MINF', '9'))
for name, (src, parts) in JOBS.items():
    if (ONLY and name not in ONLY) or not os.path.exists(D + 'geri-koy/' + src + '.png'):
        continue
    gi = Image.open(D + 'geri-koy/' + src + '.png').convert('RGB')
    g = np.asarray(gi.resize((200, 200), Image.LANCZOS), float)
    # çizgiler 5 kat küçülünce 1 piksele inip soluyordu: koyu çizgide blok minimumuna doğru karıştır
    mn = np.asarray(gi.filter(ImageFilter.MinFilter(MINF if 'goz' in parts else 5)).resize((200, 200), Image.BILINEAR), float)
    lum = mn.mean(-1)
    t_ = np.clip((140 - lum) / 80, 0, 1)[..., None] * LINE
    g = g * (1 - t_) + np.minimum(g, mn) * t_
    layer = base.copy(); layer.paste(Image.fromarray(g.round().astype(np.uint8)), (96, 50))
    mask = sd_parca.part_mask(base.size, parts.split('+'), eyes, d, mouth)
    if 'goz' in parts:  # kirpik uçları ve açık gözün kalıntısı da kalsın diye biraz geniş
        mask = mask.filter(ImageFilter.MaxFilter(5))
    soft = np.asarray(mask.filter(ImageFilter.GaussianBlur(max(d * 0.05, 1.2))), float) / 255
    L = np.asarray(layer, float)
    # ten rengi: yalnız iki görüntüde de ten olan piksellerdeki farkın düşük frekansı aktarılır (Gemini göz
    # çevresini daha pembe çizmiş; saç kenarı ölçüme girince ofset tersine dönüyordu)
    def skin(X):
        mx, mnn = X.max(-1), X.min(-1)
        return (X.mean(-1) > 150) & (X[..., 0] - X[..., 2] > 25) & (X[..., 1] >= X[..., 2] - 10) & (mx - mnn < 90)
    # göz akı (R≈B) ten sayılmasın; iki görüntüde içerik değişmişse (eski açık ağız/göz) ölçüme girmesin
    sk = (skin(B) & skin(L) & (np.abs(B - L).max(-1) < 30)).astype(float)
    def gblur(X, r=6):
        k = np.exp(-np.arange(-3 * r, 3 * r + 1) ** 2 / (2 * r * r)); k /= k.sum()
        X = np.apply_along_axis(lambda v: np.convolve(v, k, 'same'), 0, X)
        return np.apply_along_axis(lambda v: np.convolve(v, k, 'same'), 1, X)
    den = gblur(sk)
    Dlt = np.stack([gblur((B[..., c] - L[..., c]) * sk) for c in range(3)], -1) / np.maximum(den, 1e-3)[..., None]
    Dlt *= np.clip(den / 0.2, 0, 1)[..., None]
    off = Dlt[soft > 0.5].mean(0)
    L = np.clip(L + Dlt, 0, 255)
    if 'goz' in parts:
        # Gemini kapalı gözün üstüne açık renkli kapak çizgisi koymuş; küçük boyda leke gibi duruyor: tenden açık
        # pikseller yerel ten rengine çekilir
        skL = skin(L).astype(float)
        loc = np.stack([gblur(L[..., c] * skL, 4) for c in range(3)], -1) / np.maximum(gblur(skL, 4), 1e-3)[..., None]
        light = (L.mean(-1) > loc.mean(-1) + 6) & (gblur(skL, 4) > 0.3)
        L[light] = loc[light]
    res = Image.fromarray((B * (1 - soft[..., None]) + L * soft[..., None]).round().astype(np.uint8))
    hard = mask.filter(ImageFilter.MaxFilter(3))
    nh = [p for p in parts.split('+') if p == 'agiz']
    if nh:
        res = sd_parca.degreen(res, sd_parca.part_mask(base.size, nh, eyes, d, mouth))
    gz = [p for p in parts.split("+") if p.startswith("goz") or p == "kas"]
    if gz:
        res = sd_parca.keep_hair(res, base, sd_parca.part_mask(base.size, gz, eyes, d, mouth))
    res.save(os.path.join(OUT, name + '.png'))
    print(name, 'ten ofseti', np.round(off, 1))
