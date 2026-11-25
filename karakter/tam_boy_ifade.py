"""Büst ifadelerini (src/poses/sd/ifade_<ad>.png) tam boy pozların (stand, sit) yüzüne taşır.

İfade dosyası büstün yalnız kaşı/gözü/ağzı/yanağı değişmiş hâli: nötr büstten farkı (yumuşak maske) alınır,
büstün göz çifti tam boy pozun göz çiftine oturacak şekilde küçültülüp döndürülür ve pozun yüzüne yapıştırılır.
Ten farkı (iki çizimde yüz tonu biraz farklı) maskenin içindeki ortak ten piksellerinden düzeltilir; pozun kendi
kâkülü yüzün önünde kalır. Çıktı: src/poses/sd/<poz>_ifade_<ad>.png (sayfanın o çeyreği, smooth.sd_variant okur).

Kullanım: sd\\Scripts\\python değil, PIL'li python: python tam_boy_ifade.py [ad ...]
Önizleme: out/tam_boy_ifade_onizleme.png (saç #2e2a3a, yüzler ×4).
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DENEME = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme")
sys.path.insert(0, DENEME)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smooth  # noqa: E402
from onizle_renk import recolor  # noqa: E402

SD = os.path.join(DENEME, "src", "poses", "sd")
EMOTES = ["mutlu", "nese", "goz_kirp", "sevgi", "gurur", "utangac", "saskin", "uzgun", "uykulu", "sinirli", "dusunce"]
POSES = {"stand": (1, 0), "sit": (1, 1)}  # sayfadaki çeyrek (sütun, satır)


def iris(rgb, top_frac=1.0):
    """Göz merkezleri (en büyük iki parlak mavi bölge, soldan sağa); arama yalnız üst top_frac kısmında."""
    hh, ss, vv = smooth.hsv_of(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))
    m = (hh >= 185) & (hh <= 270) & (ss >= 0.35) & (vv >= 0.45)
    m[int(rgb.shape[0] * top_frac):] = False
    lab, n = smooth.label(m)
    sizes = np.bincount(lab.ravel())[1:]
    top2 = np.argsort(-sizes)[:2] + 1
    pts = sorted((np.nonzero(lab == i)[1].mean(), np.nonzero(lab == i)[0].mean()) for i in top2)
    return np.array(pts, float)


def soft(mask, grow, blur):
    im = Image.fromarray((mask * 255).astype(np.uint8))
    if grow:
        im = im.filter(ImageFilter.MaxFilter(2 * grow + 1))
    return np.array(im.filter(ImageFilter.GaussianBlur(blur))) / 255.0


def warp(img, s, ang, p0, q0, size, resample=Image.BICUBIC):
    """img'i s ile küçültüp ang (radyan) döndürür; img'deki p0 noktası çıktıda q0'a gelir."""
    small = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    c, sn = math.cos(-ang), math.sin(-ang)
    px, py = p0[0] * s, p0[1] * s
    # çıktı (x, y) → kaynak: R(-ang)·(x - q0) + p0·s
    a, b = c, -sn
    d, e = sn, c
    cx = px - a * q0[0] - b * q0[1]
    cy = py - d * q0[0] - e * q0[1]
    return small.transform(size, Image.AFFINE, (a, b, cx, d, e, cy), resample)


def skin(a):
    hh, ss, vv = smooth.hsv_of(a)
    return (hh >= 5) & (hh <= 45) & (ss >= 0.08) & (vv >= 0.55)


def transfer(sheet, pose, emote):
    W, H = sheet.width // 2, sheet.height // 2
    bust = np.array(sheet.crop((0, 0, W, H)))
    expr = np.array(Image.open(os.path.join(SD, f"ifade_{emote}.png")).convert("RGB"))
    col, row = POSES[pose]
    base = np.array(sheet.crop((col * W, row * H, (col + 1) * W, (row + 1) * H)))
    pp = iris(base, 0.35)
    # pozun kendi ağzı (açık gülüş) ifadenin ağzından başka yerde kalıp yanakta leke gibi görünüyordu: ağzı kapalı
    # hâlinin üstüne yapıştırılır
    closed = os.path.join(SD, f"{pose}_agiz_kapali.png")
    if os.path.exists(closed):
        base = np.array(Image.open(closed).convert("RGB"))
    pb = iris(bust, 0.6)
    db, dp = np.hypot(*(pb[1] - pb[0])), np.hypot(*(pp[1] - pp[0]))
    s = dp / db
    ang = math.atan2(*(pp[1] - pp[0])[::-1]) - math.atan2(*(pb[1] - pb[0])[::-1])
    mb, mp = pb.mean(0), pp.mean(0)
    # değişen yer: yüz bölgesinde (kaşların üstünden çenenin altına), iki görüntüde de saç olmayan pikseller
    diff = np.abs(expr.astype(int) - bust.astype(int)).max(-1) > 14
    yy, xx = np.mgrid[0:H, 0:W]
    # göz/kaş bandı geniş, ağız bandı dar: büstün çene konturu (yüzü pozdakinden geniş) pozun yanağına kara leke düşürüyordu
    eyes = (np.abs(xx - mb[0]) < 1.05 * db) & (yy > mb[1] - 0.9 * db) & (yy < mb[1] + 0.4 * db)
    mouth = (np.abs(xx - mb[0]) < 0.5 * db) & (yy >= mb[1] + 0.4 * db) & (yy < mb[1] + 1.2 * db)
    face = eyes | mouth
    hair = smooth.green_dom(expr) > 0.25  # ifadenin saçı taşınmaz (pozun saçı farklı yerde)
    m = soft(diff & face & ~hair, 3, 1.5)
    patch = np.array(warp(Image.fromarray(expr), s, ang, mb, mp, (W, H))).astype(float)
    mask = np.array(warp(Image.fromarray((m * 255).astype(np.uint8)), s, ang, mb, mp, (W, H))) / 255.0
    # pozun kendi kâkülü yüzün önünde kalır
    mask *= 1 - np.clip(smooth.green_dom(base), 0, 1)
    # ten tonu: maskenin içinde iki çizimde de ten olan piksellerin ortalama farkı yamaya eklenir
    both = (mask > 0.3) & skin(base) & skin(patch.astype(np.uint8))
    if both.sum() > 10:
        patch += (base[both].astype(float) - patch[both]).mean(0)
    out = base * (1 - mask[..., None]) + patch * mask[..., None]
    return np.clip(out, 0, 255).astype(np.uint8), mp, dp


def main():
    names = sys.argv[1:] or EMOTES
    sheet = Image.open(smooth.source("sheet")).convert("RGB")
    W, H = sheet.width // 2, sheet.height // 2
    tiles = []
    for pose, (col, row) in POSES.items():
        base = np.array(sheet.crop((col * W, row * H, (col + 1) * W, (row + 1) * H)))
        row_t = [("nötr", base, None)]
        for e in names:
            out, mp, dp = transfer(sheet, pose, e)
            Image.fromarray(out).save(os.path.join(SD, f"{pose}_ifade_{e}.png"))
            row_t.append((e, out, (mp, dp)))
        mp, dp = row_t[1][2]
        r = 1.6 * dp
        box = (int(mp[0] - r), int(mp[1] - 1.3 * r), int(mp[0] + r), int(mp[1] + 1.1 * r))
        tiles.append((pose, [(t, a, box) for t, a, _ in row_t]))
        print(pose, "göz arası", round(dp, 1), "px")
    z = 4
    bw, bh = (tiles[0][1][0][2][2] - tiles[0][1][0][2][0]) * z, (tiles[0][1][0][2][3] - tiles[0][1][0][2][1]) * z
    cols = len(tiles[0][1])
    G = Image.new("RGB", (cols * (bw + 6), len(tiles) * (bh + 30)), (30, 30, 30))
    dr = ImageDraw.Draw(G)
    font = ImageFont.truetype("arial.ttf", 18)
    for j, (pose, row_t) in enumerate(tiles):
        for i, (t, a, box) in enumerate(row_t):
            rgba = np.dstack([a, np.full(a.shape[:2], 255, np.uint8)])
            im = Image.fromarray(recolor(rgba, "#2e2a3a")).crop(box).resize((bw, bh), Image.LANCZOS)
            x, y = i * (bw + 6), j * (bh + 30)
            G.paste(im, (x, y + 30))
            dr.text((x + 4, y + 5), f"{pose} {t}", font=font, fill=(255, 230, 80))
    out = os.path.join(DENEME, "out", "tam_boy_ifade_onizleme.png")
    G.save(out)
    print("önizleme", out)


if __name__ == "__main__":
    main()
