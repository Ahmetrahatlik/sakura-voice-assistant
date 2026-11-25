"""Mini (chibi) Sakura kareleri: src/mini/*.png (Gemini, yeşil saçlı, 4 yüz) → frames/mini (m0..m3 + groups + hairw).

Kullanım: python mini.py
- Kaynaklar aynı çizimin yalnız yüzü değişmiş hâlleri (birebir hizalı): normal, goz-kapali, kahkaha, saskin.
- Sakura ekranın sağ altında oturup sola baktığı için hepsi aynalanır.
- Saydamlık (silüet) yalnız normal yüzden çıkarılır, dördüne aynı maske uygulanır: göz kırparken kenar titremez.
- Renk grupları chibi için ayrıca bulunur (büstün yüz kuralları bu orana uymaz): 1 saç (yeşil oranı), 2 göz (mavi iris),
  3 kıyafet (koyu giysi: hırka, papyon, etek, çorap, ayakkabı), 4 kurdele (başın üstündeki koyu fiyonklar).
  Patlamış mısır kovası hiçbir gruba girmez ve saç sayılmaz (sarı mısır yeşil karışımı gibi görünüyordu).
- Saç smooth.green_finalize ile aynı biçimde yazılır (G = saç oranı, B = gölge), Sakura.cs HairShift boyar.
Sakura.cs: Sprites("mini", "m", null) → [normal, göz kapalı, kahkaha, şaşkın].
"""
import os
import sys

import numpy as np
from PIL import Image, ImageOps

import smooth
from poses import box_count, hsv_of, label

HERE = smooth.HERE
SRC = os.path.join(HERE, "src", "mini")
OUT = os.path.join(HERE, "frames", "mini")
NAMES = ["mini-normal", "mini-goz-kapali", "mini-kahkaha", "mini-saskin"]
MINI_H = int(os.environ.get("MINI_H", "150"))  # ekrandaki boy (px); küçük boyda yarısı


def load(n):
    im = Image.open(os.path.join(SRC, n + ".png")).convert("RGB")
    return ImageOps.mirror(im)


def shift_of(a, b):
    """b'nin a'ya göre kayması (faz korelasyonu, tam piksel)."""
    fa = np.fft.fft2(a.mean(-1)); fb = np.fft.fft2(b.mean(-1))
    r = np.fft.ifft2(fa * np.conj(fb) / np.maximum(np.abs(fa * np.conj(fb)), 1e-9)).real
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    h, w = r.shape
    return (dy if dy <= h // 2 else dy - h), (dx if dx <= w // 2 else dx - w)


def cutout(rgb):
    """Chibi için sade arka plan silme: kenardan taşan beyaz + saçla çevrili büyük beyaz cepler (saç kuyruğu ile kol
    arası). smooth.cutout'un büst kuralları burada gömleği (koyu hırkayla çevrili beyaz) ve saç parlamalarını
    (saçla çevrili açık lekeler) siliyordu."""
    import pixelize
    from PIL import ImageFilter
    from poses import neighbors4
    a = rgb.astype(int)
    h, w, _ = a.shape
    mn, mx = a.min(axis=2), a.max(axis=2)
    near = (mn >= 236) & (mx - mn <= 20)
    seeds = [(0, x) for x in range(w)] + [(h - 1, x) for x in range(w)] + [(y, 0) for y in range(h)] + [(y, w - 1) for y in range(h)]
    bg = pixelize.flood(near, seeds)
    rgba = np.dstack([rgb, np.full((h, w), 255, np.uint8)])
    hair = smooth.green_tint(rgba)
    lab, n = label(near & ~bg)
    for i in range(1, n + 1):
        m = lab == i
        k = int(m.sum())
        if k < 400:  # parlama, göz beyazı, düğme
            continue
        ring = (box_count(m, 8) > 0) & ~m & ~near  # konturu aşıp saça ulaşsın
        if ring.sum() and (ring & hair).sum() >= 0.3 * ring.sum():
            bg |= m
    fg = ~bg
    for _ in range(2):
        fg &= ~(neighbors4(~fg) > 0)  # beyaz zeminle karışmış kenar
    soft = np.array(Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)))
    return np.where(fg, soft, 0).astype(np.uint8)


def popcorn_box(rgb):
    """Kırmızı-beyaz çizgili kova + üstündeki mısır: kutu (x0, y0, x1, y1)."""
    a = np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)])
    hh, ss, vv = hsv_of(a)
    red = ((hh <= 12) | (hh >= 345)) & (ss >= 0.55) & (vv >= 0.45)
    lab, n = label(red)
    if not n:
        return None
    sizes = np.bincount(lab.ravel()); sizes[0] = 0
    keep = np.isin(lab, np.nonzero(sizes >= 0.2 * sizes.max())[0])
    ys, xs = np.nonzero(keep)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    bw = x1 - x0
    # mısır kovanın üstüne taşar; eller kovayı tutar (el teni korunur: kutu yalnız mısır/kova renklerine uygulanır)
    return int(x0 - 0.12 * bw), int(y0 - 0.45 * bw), int(x1 + 0.12 * bw), int(y1 + 0.06 * bw)


def groups_of(a, w, pbox, eyes_y):
    """Renk grupları (R kanalı): 1 saç, 2 göz, 3 kıyafet, 4 kurdele."""
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    g = np.zeros(a.shape[:2], np.uint8)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    iris = vis & (hh >= 185) & (hh <= 270) & (ss >= 0.25) & (vv >= 0.3) & (np.abs(yy - eyes_y) < 0.09 * a.shape[0])
    dark = vis & (vv < 0.42) & (ss < 0.45) & (w < 0.5)
    # kontur çizgileri de koyu: saçın içindeki/kenarındaki ince çizgiler kıyafet sayılmasın (saç komşuluğu fazla)
    hairy = box_count(w >= 0.5, 2) / 25.0
    head = yy < eyes_y - 0.02 * a.shape[0]
    bows = dark & head & (box_count(dark, 3) >= 30)  # fiyonklar dolgun koyu leke; tek çizgiler değil
    body = dark & (yy > eyes_y + 0.17 * a.shape[0]) & (hairy < 0.5)
    g[body] = 3
    g[bows] = 4
    g[iris] = 2
    g[w >= 0.5] = 1
    if pbox:
        x0, y0, x1, y1 = pbox
        inb = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)
        # kova/mısır konturları (ince koyu çizgi) kıyafet sayılmaz; kovanın arkasındaki etek (dolgun koyu) sayılır
        thin = dark & (box_count(dark, 2) < 16)
        g[inb & (g == 3) & thin] = 0
    g[~vis] = 0
    return g


def main():
    srcs = [np.array(load(n)) for n in NAMES]
    for n, s in zip(NAMES[1:], srcs[1:]):
        dy, dx = shift_of(srcs[0], s)
        diff = np.abs(srcs[0].astype(int) - s.astype(int)).max(-1)
        print(n, "kayma", (dy, dx), "farklı piksel %.1f%%" % (100 * (diff > 40).mean()))
        if (dy, dx) != (0, 0):
            srcs[NAMES.index(n)] = np.roll(s, (dy, dx), axis=(0, 1))
    alpha = cutout(srcs[0])
    # tek parça silüet: ana gövdeye değmeyen kırıntılar silinir
    lab, n = label(alpha > 0)
    if n > 1:
        sizes = np.bincount(lab.ravel()); sizes[0] = 0
        alpha = np.where(np.isin(lab, np.nonzero(sizes >= 0.002 * sizes.sum())[0]), alpha, 0).astype(np.uint8)
    ys, xs = np.nonzero(alpha)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    scale = MINI_H / (y1 - y0)
    W, H = round((x1 - x0) * scale), MINI_H
    pbox_src = popcorn_box(srcs[0])
    frames = []
    for s in srcs:
        rgba = np.dstack([s, alpha])[y0:y1, x0:x1]
        im = Image.fromarray(rgba, "RGBA").convert("RGBa").resize((W, H), Image.LANCZOS).convert("RGBA")
        f = np.array(im)
        f[f[..., 3] < 8] = 0
        frames.append(f)
    k = W / (x1 - x0)
    pbox = None
    if pbox_src:
        px0, py0, px1, py1 = pbox_src
        pbox = (int((px0 - x0) * k), int((py0 - y0) * scale), int((px1 - x0) * k), int((py1 - y0) * scale))
    e = smooth.blue_eyes(frames[0][..., :3])
    eyes_y = (e[0][1] + e[1][1]) / 2 if e else 0.38 * H
    print("boyut", W, "x", H, "gözler y", round(eyes_y, 1), "mısır", pbox)
    os.makedirs(os.path.join(OUT, "groups"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "out", "mini"), exist_ok=True)
    for i, a in enumerate(frames):
        a = smooth.defringe(a.copy())
        Image.fromarray(a, "RGBA").save(os.path.join(HERE, "out", "mini", "ham_m%d.png" % i))
        w, sh, under = smooth.unmix_hair(a)
        if pbox:
            bx0, by0, bx1, by1 = pbox
            hh0 = hsv_of(a)[0][by0:by1 + 1, bx0:bx1 + 1]
            sub = w[by0:by1 + 1, bx0:bx1 + 1]
            # mısır sarı (≈45-60°), saç yeşil (≈110-125°): kutuda yeşile çalmayan her şey saç değil
            w[by0:by1 + 1, bx0:bx1 + 1] = np.where((sub >= 0.9) & (hh0 >= 75), sub, 0)
        hh, ss, vv = hsv_of(a)
        rim = (w > 0) & (vv > 0.85) & (ss < 0.35) & (box_count(a[..., 3] == 0, 1) > 0)
        a[rim] = 0
        w[rim] = 0
        m = w > 0  # mısır kutusunda saf saç dışındaki oran yukarıda sıfırlandı
        out = a.copy()
        if m.any():
            p = smooth.pink_of(sh[m]).astype(float)
            out[m, :3] = np.clip(w[m, None] * p + (1 - w[m, None]) * under[m], 0, 255).round().astype(np.uint8)
        g = groups_of(a, w, pbox, eyes_y)
        G = np.where(out[..., 3] > 0, np.round(w * 255), 0).astype(np.uint8)
        Bc = np.where(m, np.round(np.clip(sh, 0, 1) * 255), 0).astype(np.uint8)
        name = "m%d.png" % i
        Image.fromarray(out, "RGBA").save(os.path.join(OUT, name))
        Image.fromarray(np.stack([g, G, Bc], -1), "RGB").save(os.path.join(OUT, "groups", name))
        print(name, "saç", int((w >= 0.5).sum()), "göz", int((g == 2).sum()), "kıyafet", int((g == 3).sum()), "kurdele", int((g == 4).sum()))
    with open(os.path.join(OUT, "hairw"), "w") as fh:
        fh.write("G = saç oranı, B = gölge (HLS açıklığı); P(s) = HLS(%.6f, min(1, s*%.3f), %.3f)\n" % (smooth.PINK_H, smooth.PINK_GAIN, smooth.PINK_S))


if __name__ == "__main__":
    main()
