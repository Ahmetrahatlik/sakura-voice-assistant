"""YouTube kanal kapağı (2560×1440): yıldızlı gece, hilalde oturan Luna, "Luna" yazısı.
Her cihazda görünen güvenli alan ortadaki 1546×423; her şey onun içinde.
python kapak.py → kanal_kapagi.png (+ kanal_kapagi_onizleme.png: güvenli alan çizgili, küçük)
"""
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 2560, 1440
SAFE = (507, 508, 2053, 931)
FONTS = r"C:\Windows\Fonts"
rnd = random.Random(11)


def gece():
    y = np.linspace(0, 1, H)[:, None, None]
    x = np.linspace(0, 1, W)[None, :, None]
    top, bot = np.array([10, 12, 36]), np.array([58, 34, 96])
    a = top + (bot - top) * (0.55 * y + 0.45 * x)
    a = np.broadcast_to(a, (H, W, 3)).astype(float).copy()
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.abs((yy - 0.35 * xx) - 150) / 220.0
    a += (np.exp(-d * d) * 26)[..., None] * np.array([0.8, 0.75, 1.0])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


def parilti(d, x, y, r, a):
    d.polygon([(x, y - r), (x + r * 0.18, y - r * 0.18), (x + r, y), (x + r * 0.18, y + r * 0.18), (x, y + r),
               (x - r * 0.18, y + r * 0.18), (x - r, y), (x - r * 0.18, y - r * 0.18)], fill=(255, 240, 250, int(255 * a)))


def main():
    im = gece()
    st = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(st)
    for _ in range(700):
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.choice([1, 1, 1.5, 2, 2.5])
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 250, 255, int(rnd.uniform(110, 240))))
    im.alpha_composite(st.filter(ImageFilter.GaussianBlur(3)))
    im.alpha_composite(st)
    sp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sp)
    for _ in range(40):
        x, y = rnd.uniform(30, W - 30), rnd.uniform(30, H - 30)
        if 900 < x < 2000 and 520 < y < 920:
            continue  # yazının üstüne düşmesin
        parilti(ds, x, y, rnd.uniform(10, 26), rnd.uniform(0.5, 1))
    im.alpha_composite(sp.filter(ImageFilter.GaussianBlur(2)))
    im.alpha_composite(sp)

    # hilal + oturan Luna (güvenli alanın solunda)
    fig = Image.open(os.path.join(HERE, "sit_buyuk.png")).convert("RGBA")
    s = 0.78
    fig = fig.resize((round(fig.width * s), round(fig.height * s)), Image.LANCZOS)
    fx, fb = 790, 900  # figürün alt ortası
    cx, cy, r, off = fx, fb - 330 * s * 1.0 + 10, 250, 52
    m = Image.new("L", (W * 2, H * 2), 0)
    md = ImageDraw.Draw(m)
    md.ellipse(((cx - r) * 2, (cy - r) * 2, (cx + r) * 2, (cy + r) * 2), fill=255)
    md.ellipse(((cx - r - 5) * 2, (cy - r - off) * 2, (cx + r + 5) * 2, (cy + r - off) * 2), fill=0)
    m = m.resize((W, H), Image.LANCZOS)
    glow = Image.new("RGBA", (W, H), (255, 214, 150, 0))
    glow.putalpha(Image.fromarray((np.array(m.filter(ImageFilter.GaussianBlur(24))) * 0.8).astype(np.uint8)))
    moon = Image.new("RGBA", (W, H), (255, 236, 178, 0))
    moon.putalpha(m)
    im.alpha_composite(glow)
    im.alpha_composite(moon)
    im.alpha_composite(fig, (fx - fig.width // 2, fb - fig.height))

    # yazı
    tx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dt = ImageDraw.Draw(tx)
    f1 = ImageFont.truetype(os.path.join(FONTS, "segoeuiz.ttf"), 200)
    f2 = ImageFont.truetype(os.path.join(FONTS, "segoeuib.ttf"), 56)
    fe = ImageFont.truetype(os.path.join(FONTS, "seguiemj.ttf"), 120)
    x0 = 1080
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((x0, 520), "Luna", font=f1, fill=(255, 120, 190, 255))
    tx.alpha_composite(g.filter(ImageFilter.GaussianBlur(18)))
    dt.text((x0, 520), "Luna", font=f1, fill=(255, 238, 248, 255))
    dt.text((x0 + dt.textlength("Luna", font=f1) + 30, 590), "🌸", font=fe, embedded_color=True)
    dt.text((x0 + 8, 790), "Masaüstünde yaşayan sanal kız~", font=f2, fill=(226, 212, 255, 255))
    im.alpha_composite(tx)
    out = im.convert("RGB")
    out.save(os.path.join(HERE, "kanal_kapagi.png"))
    pv = out.copy()
    ImageDraw.Draw(pv).rectangle(SAFE, outline=(0, 255, 140), width=6)
    pv.resize((W // 2, H // 2), Image.LANCZOS).save(os.path.join(HERE, "kanal_kapagi_onizleme.png"))
    print("tamam")


if __name__ == "__main__":
    main()
