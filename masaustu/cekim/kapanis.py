"""Luna kapanış kartı (1080×1920): yıldızlı gece, hilal ayın üstünde oturan Luna, altta çağrı.

python kapanis.py onizle            → kapanis_ig.png, kapanis_yt.png (son kare)
python kapanis.py kare <ig|yt> <dir> → <dir>/k_000.png ... (SURE sn, 30 fps)
"""
import math
import os
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS, SURE = 1080, 1920, 30, 3.5
FONTS = r"C:\Windows\Fonts"
FIGUR = os.path.join(HERE, "sit_buyuk.png")  # yeşil sayfanın oturma çeyreği, kesilmiş, saç #2e2a3a
METIN = {
    "ig": ("Luna'nın maceralarını", "kaçırmayın", "@luna.ekranda", "TAKİP ET"),
    "yt": ("Luna'nın maceralarını", "kaçırmayın", "bildirimleri de açın~", "ABONE OL"),
}

rnd = random.Random(7)


def gece():
    """Koyu laciverden mora dikey geçiş + hafif samanyolu pusu."""
    y = np.linspace(0, 1, H)[:, None, None]
    top, mid, bot = np.array([8, 10, 32]), np.array([30, 22, 70]), np.array([74, 40, 104])
    c = np.where(y < 0.6, top + (mid - top) * (y / 0.6), mid + (bot - mid) * ((y - 0.6) / 0.4))
    a = np.broadcast_to(c, (H, W, 3)).astype(float).copy()
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.abs((yy - 0.9 * xx) - 300) / 260.0
    a += (np.exp(-d * d) * 22)[..., None] * np.array([0.8, 0.75, 1.0])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


BG = None
YILDIZ = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.choice([1, 1, 1, 1.5, 2]), rnd.uniform(0, 6.28), rnd.uniform(1.5, 4))
          for _ in range(330)]
# büyük parıltılar Luna'nın ve yazıların üstüne düşmesin
PARILTI = [p for p in ((rnd.uniform(40, W - 40), rnd.uniform(40, H - 40), rnd.uniform(9, 20), rnd.uniform(0, 6.28)) for _ in range(60))
           if not (250 < p[1] < 1620 and 150 < p[0] < W - 150)][:16]

FS = 1.45                    # figür ölçeği (384×512 → ~557×742)
FX, FY = W // 2, 1040        # figürün alt ortası (oturduğu yer)
MOON_C, MOON_R = (W // 2, 700), 345   # hilal: büyük daire − yukarı kaydırılmış daire


def figur():
    im = Image.open(FIGUR).convert("RGBA")
    a = np.array(im)
    # kesimden kalan küçük kırıntılar (saç kenarı) silinir
    sys.path.insert(0, os.path.expanduser(r"~\.claude\sakura"))
    from poses import label
    lab, n = label(a[..., 3] > 20)
    sizes = np.bincount(lab.ravel())
    small = (sizes < 150)
    small[0] = False
    a[small[lab]] = 0
    im = Image.fromarray(a, "RGBA")
    return im.resize((round(im.width * FS), round(im.height * FS)), Image.LANCZOS)


FIG = None


def hilal(alpha):
    """Luna'nın oturduğu hilal (alt yay), yumuşak ışıltılı."""
    k = 4
    big = Image.new("L", (W * k // 4, H * k // 4), 0)
    cx, cy, r = MOON_C[0], MOON_C[1], MOON_R
    m = Image.new("L", (W * 2, H * 2), 0)
    d = ImageDraw.Draw(m)
    d.ellipse(((cx - r) * 2, (cy - r) * 2, (cx + r) * 2, (cy + r) * 2), fill=255)
    off = 70
    d.ellipse(((cx - r - 6) * 2, (cy - r - off) * 2, (cx + r + 6) * 2, (cy + r - off) * 2), fill=0)
    m = m.resize((W, H), Image.LANCZOS)
    col = Image.new("RGBA", (W, H), (255, 236, 178, 0))
    col.putalpha(Image.fromarray((np.array(m) * alpha).astype(np.uint8)))
    glow = Image.new("RGBA", (W, H), (255, 214, 150, 0))
    glow.putalpha(Image.fromarray((np.array(m.filter(ImageFilter.GaussianBlur(26))) * 0.8 * alpha).astype(np.uint8)))
    return glow, col


def parilti(d, x, y, r, alpha):
    c = (255, 240, 250, int(255 * alpha))
    d.polygon([(x, y - r), (x + r * 0.18, y - r * 0.18), (x + r, y), (x + r * 0.18, y + r * 0.18), (x, y + r),
               (x - r * 0.18, y + r * 0.18), (x - r, y), (x - r * 0.18, y - r * 0.18)], fill=c)


def metin_ortala(d, y, s, font, fill):
    w = d.textlength(s, font=font)
    d.text(((W - w) / 2, y), s, font=font, fill=fill)


def kare(t, tur):
    global BG, FIG
    if BG is None:
        BG = gece()
        FIG = figur()
    im = BG.convert("RGBA")
    st = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(st)
    for x, y, r, ph, sp in YILDIZ:
        b = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(ph + t * sp))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 250, 255, int(230 * b)))
    im.alpha_composite(st.filter(ImageFilter.GaussianBlur(3)))
    im.alpha_composite(st)
    sp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sp)
    for x, y, r, ph in PARILTI:
        a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(ph + t * 2.2))
        parilti(ds, x, y, r * (0.8 + 0.3 * a), a)
    im.alpha_composite(sp.filter(ImageFilter.GaussianBlur(2)))
    im.alpha_composite(sp)
    # hilal ve Luna: hafifçe yükselip belirir, sonra yavaşça süzülür
    k = min(1.0, t / 0.7)
    ease = 1 - (1 - k) ** 3
    bob = 8 * math.sin(t * 2.0) * ease
    rise = (1 - ease) * 60
    glow, moon = hilal(ease)
    sh = int(rise + bob)
    for layer in (glow, moon):
        im.alpha_composite(layer, (0, sh) if sh >= 0 else (0, 0), (0, 0) if sh >= 0 else (0, -sh))
    f = FIG.copy()
    if ease < 1:
        f.putalpha(Image.fromarray((np.array(f.getchannel("A")) * ease).astype(np.uint8)))
    im.alpha_composite(f, (FX - f.width // 2, FY - f.height + sh))
    # yazılar 0,4 sn sonra belirir
    ta = max(0.0, min(1.0, (t - 0.4) / 0.5))
    tx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dt = ImageDraw.Draw(tx)
    l1, l2, l3, btn = METIN[tur]
    f1 = ImageFont.truetype(os.path.join(FONTS, "segoeuib.ttf"), 66)
    f2 = ImageFont.truetype(os.path.join(FONTS, "segoeuiz.ttf"), 116)
    f3 = ImageFont.truetype(os.path.join(FONTS, "segoeui.ttf"), 50)
    fe = ImageFont.truetype(os.path.join(FONTS, "seguiemj.ttf"), 96)
    metin_ortala(dt, 1150, l1, f1, (240, 232, 255, 255))
    w2 = dt.textlength(l2, font=f2) + 20 + 110
    x2 = (W - w2) / 2
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((x2, 1228), l2, font=f2, fill=(255, 120, 190, 255))
    tx.alpha_composite(g.filter(ImageFilter.GaussianBlur(14)))
    dt.text((x2, 1228), l2, font=f2, fill=(255, 236, 246, 255))
    dt.text((x2 + dt.textlength(l2, font=f2) + 20, 1248), "🌸", font=fe, embedded_color=True)
    metin_ortala(dt, 1395, l3, f3, (220, 205, 255, 255))
    bw, bh, by = 430, 96, 1490
    pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if tur == "yt":
        ImageDraw.Draw(pill).rounded_rectangle(((W - bw) / 2, by, (W + bw) / 2, by + bh), radius=48, fill=(230, 33, 23, 255))
    else:
        ImageDraw.Draw(pill).rounded_rectangle(((W - bw) / 2, by, (W + bw) / 2, by + bh), radius=48, fill=(255, 255, 255, 40), outline=(255, 214, 240, 255), width=4)
    tx.alpha_composite(pill)
    metin_ortala(dt, by + 16, btn, ImageFont.truetype(os.path.join(FONTS, "segoeuib.ttf"), 48), (255, 255, 255, 255))
    if ta < 1:
        tx = Image.fromarray((np.array(tx) * np.array([1, 1, 1, ta])).astype(np.uint8))
    im.alpha_composite(tx)
    return im.convert("RGB")


if __name__ == "__main__":
    if sys.argv[1] == "onizle":
        for tur in ("ig", "yt"):
            kare(SURE, tur).save(os.path.join(HERE, f"kapanis_{tur}.png"))
        print("tamam")
    else:
        tur, d = sys.argv[2], sys.argv[3]
        os.makedirs(d, exist_ok=True)
        for i in range(int(SURE * FPS)):
            kare(i / FPS, tur).save(os.path.join(d, f"k_{i:03d}.png"))
        print("kareler", d)
