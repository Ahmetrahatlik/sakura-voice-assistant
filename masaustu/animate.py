"""Pixel art sprite'tan kukla animasyon kareleri üretir.

Kullanım: python animate.py out/k4.png out/k4_groups.png frames/klasik
Her görünümün el ve göz koordinatları RIG içinde tanımlıdır (sprite pikseli cinsinden).
"""
import math
import os
import sys

import numpy as np
from PIL import Image

import emotes

DARK = np.array([43, 29, 46, 255], np.uint8)

RIG = {
    "klasik": {
        "hand_box": (0, 86, 62, 151),   # x0, y0, x1, y1 (dahil değil)
        "wrist": (37, 150),
        "eyes": [  # (merkez x, merkez y, yarıçap x, yarıçap y, kapalı göz çizgisi y'leri sol/orta/sağ)
            (85, 78, 12, 8, (79, 81, 78)),
            (122, 70, 12, 8, (72, 74, 70)),
        ],
        "breath_cut": 200,  # bu satırın üstü nefes alırken 1 px kalkar
    }
}


# rig.py'nin otomatik bulduğu yeni görünümler
_rigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rigs.json")
if os.path.exists(_rigs):
    import json
    for _name, _r in json.load(open(_rigs, encoding="utf-8")).items():
        RIG[_name] = _r["rig"]


def is_skin(p):
    r, g, b = int(p[0]), int(p[1]), int(p[2])
    return r > 215 and g > 165 and b > 130 and r - b > 25


def hand_mask(img, box):
    x0, y0, x1, y1 = box
    h, w, _ = img.shape
    m = np.zeros((h, w), bool)
    for y in range(y0, y1):
        for x in range(x0, x1):
            if img[y, x, 3] and is_skin(img[y, x]):
                m[y, x] = True
    # Konturu ekle: ele komşu koyu pikseller (iç kontur + dış silüet konturu için 2 tur).
    d = m.copy()
    for _ in range(2):
        nd = d.copy()
        for y in range(y0, y1):
            for x in range(x0, x1):
                if d[y, x] or not img[y, x, 3]:
                    continue
                if int(img[y, x, :3].sum()) < 330 and d[max(y - 1, 0):y + 2, max(x - 1, 0):x + 2].any():
                    nd[y, x] = True
        d = nd
    # Avuç içi çizgileri gibi 1 px'lik boşlukları kapat: iki yanı (yatay ya da dikey) else elin parçasıdır.
    c = d.copy()
    for y in range(y0 + 1, y1 - 1):
        for x in range(x0 + 1, x1 - 1):
            if not d[y, x] and img[y, x, 3] and ((d[y, x - 1] and d[y, x + 1]) or (d[y - 1, x] and d[y + 1, x])):
                c[y, x] = True
    return c


def inpaint(img, hole):
    """Delikleri komşu piksellerle (şeffaflık dahil) doldurur."""
    out = img.copy()
    known = ~hole
    h, w = hole.shape
    while not known.all():
        nk = known.copy()
        for y, x in zip(*np.nonzero(~known)):
            votes = {}
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and known[ny, nx]:
                    key = tuple(out[ny, nx]) if out[ny, nx, 3] else (0, 0, 0, 0)
                    votes[key] = votes.get(key, 0) + 1
            if votes:
                out[y, x] = max(votes, key=votes.get)
                nk[y, x] = True
        known = nk
    return out


def rotate_layer(layer, mask, pivot, deg):
    h, w = mask.shape
    out = np.zeros_like(layer)
    om = np.zeros_like(mask)
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    px, py = pivot
    ys, xs = np.nonzero(mask)
    pad = 12
    for y in range(max(ys.min() - pad, 0), min(ys.max() + pad, h)):
        for x in range(max(xs.min() - pad, 0), min(xs.max() + pad, w)):
            # Ters dönüşüm: hedef pikselin kaynağını bul (en yakın komşu).
            dx, dy = x + 0.5 - px, y + 0.5 - py
            sx = ca * dx + sa * dy + px
            sy = -sa * dx + ca * dy + py
            ix, iy = int(math.floor(sx)), int(math.floor(sy))
            if 0 <= ix < w and 0 <= iy < h and mask[iy, ix]:
                out[y, x] = layer[iy, ix]
                om[y, x] = True
    return out, om


def close_eyes(img, eyes, skin):
    out = img.copy()
    for cx, cy, rx, ry, (yl, ym, yr) in eyes:
        emotes.clear_eye(out, cx, cy, rx, ry, tuple(int(v) for v in skin))
        # Kapalı göz: hafif aşağı kıvrık kirpik çizgisi, ortası 2 px kalın.
        for x in range(cx - rx + 1, cx + rx):
            t = (x - (cx - rx)) / (2 * rx)
            yy = round(yl + (ym - yl) * min(t * 2, 1)) if t < 0.5 else round(ym + (yr - ym) * (t - 0.5) * 2)
            if emotes.is_hair(out[yy, x]):
                continue  # çizgi saç tutamının üstüne taşmasın
            out[yy, x] = DARK
            if abs(x - cx) < rx * 0.5 and not emotes.is_hair(out[yy - 1, x]):
                out[yy - 1, x] = DARK
    return out


def outline(img):
    a = img[..., 3] > 0
    ring = np.zeros_like(a)
    ring[1:] |= a[:-1]
    ring[:-1] |= a[1:]
    ring[:, 1:] |= a[:, :-1]
    ring[:, :-1] |= a[:, 1:]
    out = img.copy()
    out[ring & ~a] = DARK
    return out


def breathe(img, cut, up):
    if not up:
        return img
    out = img.copy()
    out[0:cut - 1] = img[1:cut]
    return out


def build(src, dst, rig, groups_src):
    img = np.array(Image.open(src).convert("RGBA"))
    # Renk grubu haritası (0 = sabit, 1 saç, 2 göz, 3 kıyafet, 4 kurdele) karelerle aynı
    # dönüşümlerden geçsin diye RGBA biçiminde taşınır: R = grup, A = görünürlük.
    gimg = np.zeros_like(img)
    gimg[..., 0] = np.array(Image.open(groups_src))
    gimg[..., 3] = img[..., 3]
    hm = hand_mask(img, rig["hand_box"])
    hand = np.where(hm[..., None], img, 0).astype(np.uint8)
    ghand = np.where(hm[..., None], gimg, 0).astype(np.uint8)
    plate = inpaint(img, hm)
    gplate = inpaint(gimg, hm)
    cx, cy, *_ = rig["eyes"][0]
    skin = img[cy + 9, cx].copy()
    look = os.path.basename(dst.rstrip("/\\"))

    def save(out_dir, name, frame, gframe):
        gframe = gframe.copy()
        gframe[frame[..., 3] == 0, 0] = 0
        Image.fromarray(frame, "RGBA").save(os.path.join(out_dir, name))
        g = gframe[..., 0]
        Image.fromarray(np.stack([g, g, g], -1), "RGB").save(os.path.join(out_dir, "groups", name))

    def blink(frame, gframe):
        closed = close_eyes(frame, rig["eyes"], skin)
        gframe = gframe.copy()
        gframe[(closed != frame).any(axis=2), 0] = 0
        return closed, gframe

    # Ham kareler: (dosya adı, kare no, kare, grup karesi, göz kırpma karesi mi, nefes yukarıda mı)
    base = []
    angles = [0, 7, 13, 16, 13, 7, 0, -5, -8, -5, 0, 7, 13, 16, 13, 7, 0, -5, -8, -5]
    for i, ang in enumerate(angles):
        layer, lm = rotate_layer(hand, hm, rig["wrist"], ang)
        glayer, _ = rotate_layer(ghand, hm, rig["wrist"], ang)
        frame = plate.copy()
        frame[lm] = layer[lm]
        gframe = gplate.copy()
        gframe[lm] = glayer[lm]
        base.append((f"wave_{i:02d}.png", i, outline(frame), gframe, i in (14, 15), (i // 5) % 2 == 1))
    # Bekleme (izin isteme) döngüsü: el sabit, nefes + göz kırpma.
    for i in range(12):
        base.append((f"idle_{i:02d}.png", i, img.copy(), gimg.copy(), i in (8, 9), (i // 3) % 2 == 1))

    def emit(out_dir, emote):
        os.makedirs(os.path.join(out_dir, "groups"), exist_ok=True)
        for name, i, frame, gframe, blinks, up in base:
            if emote:
                e = emotes.apply(frame, look, emote, i)
                gframe = gframe.copy()
                gframe[(e != frame).any(axis=2), 0] = 0  # yeniden çizilen yüz/efekt pikselleri boyanmaz
                frame = e
            if blinks and (not emote or emotes.EMOTES[emote][5]):
                frame, gframe = blink(frame, gframe)
            save(out_dir, name, breathe(frame, rig["breath_cut"], up), breathe(gframe, rig["breath_cut"], up))

    emit(dst, None)
    for e in emotes.EMOTES:
        emit(os.path.join(dst, "emotes", e), e)
    print("kareler:", dst)


if __name__ == "__main__":
    src, groups_src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    name = os.path.basename(dst.rstrip("/\\"))
    build(src, dst, RIG[name], groups_src)
