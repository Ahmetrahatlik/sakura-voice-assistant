"""Yeni bir görünüm için animasyon/ifade koordinatlarını otomatik bulur ve rigs.json'a yazar.

Kullanım: python rig.py out/gamer.png gamer
- El: sol yarıdaki en büyük ten bölgesi (el sallayan el), bilek = alt kenarın ortası.
- Yüz: ortadaki en büyük ten bölgesi.
- Gözler: yüzün üst yarısındaki iki büyük koyu/mavi bölge.
- Ağız: gözlerin altındaki koyu kırmızı bölge.
Sonuç preview/rig_<ad>.png'de kutularla gösterilir; gözle kontrol edilmelidir.
"""
import colorsys
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

import emotes


def components(mask):
    h, w = mask.shape
    seen = np.zeros_like(mask)
    out = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        stack, pts = [(y, x)], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            pts.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        ys, xs = zip(*pts)
        out.append({"n": len(pts), "x0": min(xs), "x1": max(xs) + 1, "y0": min(ys), "y1": max(ys) + 1, "pts": pts})
    return out


def hsv(p):
    h, s, v = colorsys.rgb_to_hsv(*(int(c) / 255 for c in p[:3]))
    return h * 360, s, v


def rig(path):
    img = np.array(Image.open(path).convert("RGBA"))
    h, w, _ = img.shape
    skin = np.array([[bool(emotes.is_skin(img[y, x])) for x in range(w)] for y in range(h)])

    comps = components(skin)
    hand = max((c for c in comps if (c["x0"] + c["x1"]) / 2 < w * 0.35 and 60 <= (c["y0"] + c["y1"]) / 2 <= 170), key=lambda c: c["n"])
    face = max((c for c in comps if w * 0.3 < (c["x0"] + c["x1"]) / 2 < w * 0.75 and c["y0"] < 110), key=lambda c: c["n"])
    # Geniş kollu kıyafetlerde ön kol da ten görünür: eli en çok ~60 px yükseklikte kes, bilek orası.
    if hand["y1"] - hand["y0"] > 62:
        hand["y1"] = hand["y0"] + 60
        hand["pts"] = [(y, x) for y, x in hand["pts"] if y < hand["y1"]]
    bottom = [x for y, x in hand["pts"] if y >= hand["y1"] - 3]
    wrist = (int(round(sum(bottom) / len(bottom))), hand["y1"] - 1)

    # Gözler: yüz kutusunun üst %60'ında, ten/saç olmayan koyu ya da mavi pikseller.
    fx0, fx1, fy0, fy1 = face["x0"], face["x1"], face["y0"], face["y1"]
    eye = np.zeros_like(skin)
    for y in range(fy0, fy0 + int((fy1 - fy0) * 0.6)):
        for x in range(fx0, fx1):
            if not img[y, x, 3] or skin[y, x]:
                continue
            hu, s, v = hsv(img[y, x])
            if v < 0.42 or (180 <= hu <= 290 and s > 0.18):
                eye[y, x] = True
    eyes = sorted(components(eye), key=lambda c: -c["n"])[:2]
    eyes = sorted(eyes, key=lambda c: c["x0"])
    E = []
    for c in eyes:
        cx, cy = (c["x0"] + c["x1"]) // 2, (c["y0"] + c["y1"]) // 2
        # Açık renkli iris altı ve beyazlar tespit maskesine girmez: elipsi aşağı kaydır ve büyüt.
        E.append((cx, cy + 1, (c["x1"] - c["x0"]) // 2 + 4, (c["y1"] - c["y0"]) // 2 + 4))

    # Ağız: iki gözün ortasının ~23 px altında (Klasik'teki oran); o pencerede koyu kırmızı/pembe pikseller.
    px = (E[0][0] + E[1][0]) // 2 + 2
    py = (E[0][1] + E[1][1]) // 2 + 23
    xs, ys = [], []
    for y in range(py - 9, py + 9):
        for x in range(px - 13, px + 13):
            hu, sat, v = hsv(img[y, x])
            if img[y, x, 3] and (hu >= 330 or hu <= 20) and sat > 0.35 and v < 0.85:
                xs.append(x); ys.append(y)
    if len(xs) >= 6:
        m = {"x0": min(xs), "x1": max(xs) + 1, "y0": min(ys), "y1": max(ys) + 1}
    else:
        m = {"x0": px - 8, "x1": px + 8, "y0": py - 4, "y1": py + 4}
    mcx, mcy = (m["x0"] + m["x1"]) // 2, (m["y0"] + m["y1"]) // 2

    tilt = round((E[1][1] - E[0][1]) / max(1, E[1][0] - E[0][0]), 2)
    rx = max(e[2] for e in E)
    ry = max(e[3] for e in E)
    return {
        "rig": {
            "hand_box": [max(0, hand["x0"] - 3), max(0, hand["y0"] - 3), hand["x1"] + 3, hand["y1"]],
            "wrist": list(wrist),
            "eyes": [[e[0], e[1], e[2], e[3], [e[1] + 1, e[1] + 2, e[1] + 1]] for e in E],
            "breath_cut": 200,
        },
        "face": {
            "eyes": [[e[0], e[1]] for e in E],
            "eye_r": [rx, ry],
            "mouth": [mcx, mcy],
            "mouth_box": [m["x0"] - 4, m["y0"] - 3, m["x1"] + 4, m["y1"] + 4],
            "cheeks": [[E[0][0] - 4, E[0][1] + ry + 5], [E[1][0] + 4, E[1][1] + ry + 5]],
            "tilt": tilt,
            "fx_left": [6, 14],
            "fx_right": [w - 26, 0],
            "sweat": [min(w - 12, fx1 + 2), max(0, E[1][1] - 22)],
        },
        "regions": {
            "mouth": [m["x0"] - 3, m["y0"] - 3, m["x1"] + 3, m["y1"] + 3],
            "face": [fx0 - 6, fy0 - 4, fx1 + 6, fy1 + 26],
            "neck": [mcx - 16, m["y1"] + 4, mcx + 16, m["y1"] + 30],
        },
    }


if __name__ == "__main__":
    path, name = sys.argv[1], sys.argv[2]
    r = rig(path)
    store = json.load(open("rigs.json", encoding="utf-8")) if os.path.exists("rigs.json") else {}
    store[name] = r
    json.dump(store, open("rigs.json", "w", encoding="utf-8"), indent=1, default=int)
    # Kontrol görüntüsü
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (40, 44, 52, 255))
    bg.alpha_composite(im)
    big = bg.resize((im.width * 3, im.height * 3), Image.NEAREST)
    d = ImageDraw.Draw(big)
    box = lambda b, c: d.rectangle([b[0] * 3, b[1] * 3, b[2] * 3, b[3] * 3], outline=c, width=2)
    box(r["rig"]["hand_box"], (0, 255, 0))
    for cx, cy, rx, ry, _ in r["rig"]["eyes"]:
        box([cx - rx, cy - ry, cx + rx, cy + ry], (0, 200, 255))
    box(r["face"]["mouth_box"], (255, 60, 60))
    box(r["regions"]["neck"], (255, 200, 0))
    wx, wy = r["rig"]["wrist"]
    d.ellipse([wx * 3 - 5, wy * 3 - 5, wx * 3 + 5, wy * 3 + 5], fill=(255, 0, 255))
    big.save(f"preview/rig_{name}.png")
    print(name, json.dumps(r["rig"], default=int), r["face"]["mouth"], "tilt", r["face"]["tilt"])
