"""Sprite piksellerini renk gruplarına ayırır: menüden renk değiştirilebilen bölgeler.

Grup kimlikleri: 0 = sabit (ten, bluz, kontur), 1 = saç, 2 = göz, 3 = kıyafet, 4 = kurdele/aksesuar.
Kullanım: python groups.py out/k4.png out/k4_groups.png klasik
Yeni görünümlerin bölgeleri rig.py'nin yazdığı rigs.json'dan gelir; kıyafet/aksesuar renk kuralı STYLES'tadır.
"""
import colorsys
import json
import os
import sys

import numpy as np
from PIL import Image

import animate
import emotes

GROUPS = {"hair": 1, "eyes": 2, "outfit": 3, "ribbon": 4}
OUTLINE = (43, 29, 46)

# Görünüme özel bölge bilgisi (sprite pikseli): renk kuralı yetmeyen yerleri dışlamak için.
REGIONS = {
    "klasik": {
        "mouth": (86, 88, 112, 108),
        "face": (60, 55, 150, 135),
        "neck": (86, 100, 120, 128),  # çene altı gölgesi pembe ama ten
    }
}
_rigs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rigs.json")
if os.path.exists(_rigs):
    for _name, _r in json.load(open(_rigs, encoding="utf-8")).items():
        REGIONS[_name] = {k: tuple(v) for k, v in _r["regions"].items()}


def is_skin_hsv(hu, s, v):
    return 5 <= hu <= 45 and s < 0.4 and v > 0.75


def inside(x, y, box):
    x0, y0, x1, y1 = box
    return x0 <= x < x1 and y0 <= y < y1


# Kıyafet (3) ve aksesuar (4) kuralları: (hu, s, v, y, ust) -> bool. "ust" = boyun hizasının üstü (baş).
dark = lambda hu, s, v: v < 0.36 and s < 0.4
STYLES = {
    "klasik": {
        "outfit": lambda hu, s, v, y, up: 190 <= hu <= 265 and s > 0.25 and v > 0.12,
        "acc": lambda hu, s, v, y, up: (hu >= 300 or hu <= 15) and s >= 0.62 and v > 0.3,
    },
    "gamer": {  # siyah kapüşonlu; kulaklık (siyah + nane rengi ışıklar) aksesuar
        "outfit": lambda hu, s, v, y, up: not up and dark(hu, s, v),
        "acc": lambda hu, s, v, y, up: (up and dark(hu, s, v)) or (140 <= hu <= 200 and s > 0.3 and v > 0.3),
    },
    "gotik": {  # siyah elbise ve fiyonk; kedi kulakları + başlık aksesuar
        "outfit": lambda hu, s, v, y, up: not up and dark(hu, s, v),
        "acc": lambda hu, s, v, y, up: up and dark(hu, s, v),
    },
    "festival": {  # kırmızı yukata; sarı kuşak aksesuar; gözler kahverengi
        "brown_eyes": True,
        "outfit": lambda hu, s, v, y, up: not up and (hu >= 340 or hu <= 14) and s > 0.55 and v > 0.3,
        "acc": lambda hu, s, v, y, up: not up and 28 <= hu <= 60 and s > 0.35 and v > 0.45,
    },
    "tilki": {  # lila kimono; koyu mor kuşak aksesuar
        "outfit": lambda hu, s, v, y, up: not up and 235 <= hu <= 305 and 0.1 < s < 0.6 and v > 0.48,
        "acc": lambda hu, s, v, y, up: not up and 245 <= hu <= 315 and s > 0.2 and 0.12 < v <= 0.48,
    },
}


def classify(img, look):
    rig = animate.RIG[look]
    reg = REGIONS[look]
    style = STYLES.get(look, STYLES["klasik"])
    neck_y = reg["neck"][1]
    hand = animate.hand_mask(img, rig["hand_box"])
    h, w, _ = img.shape
    hsv = np.zeros((h, w, 3))
    for y in range(h):
        for x in range(w):
            r, gg, b = (int(c) / 255 for c in img[y, x, :3])
            hu, s, v = colorsys.rgb_to_hsv(r, gg, b)
            hsv[y, x] = (hu * 360, s, v)
    skin = np.zeros((h, w), bool)
    for y in range(h):
        for x in range(w):
            skin[y, x] = img[y, x, 3] > 0 and is_skin_hsv(*hsv[y, x])
    cheeks = emotes.FACE[look]["cheeks"]

    def is_blush(x, y, hu, s, v):
        near_skin = skin[max(y - 2, 0):y + 3, max(x - 2, 0):x + 3].sum()
        on_cheek = any(abs(x - cx) <= 12 and abs(y - cy) <= 7 for cx, cy in cheeks)  # allık çizgileri doygun olabilir
        return inside(x, y, reg["face"]) and ((on_cheek and near_skin >= 6) or ((s < 0.35 or v > 0.86) and near_skin >= 10))

    g = np.zeros((h, w), np.uint8)
    for y in range(h):
        for x in range(w):
            if not img[y, x, 3] or tuple(img[y, x, :3]) == OUTLINE:
                continue
            hu, s, v = hsv[y, x]
            up = y < neck_y
            in_eye = any(((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1
                         for cx, cy, rx, ry, _ in rig["eyes"])
            blueish = 190 <= hu <= 290 and s > 0.15
            reddish = hu >= 300 or hu <= 15
            if in_eye:
                # Göz elipsine giren perçem telleri saçtır (doygun pembe); göz kapağı gölgesi değildir.
                if (hu >= 330 or hu <= 10) and s >= 0.3 and v > 0.6 and not skin[y, x]:
                    g[y, x] = 1
                # Gri-mavi/mor iris tonları da göz sayılır; ten, beyaz ve kontur hariç.
                # Mavi/mor iris; Festival'de kahverengi iris. Gözün çevresindeki gri gölgeler göz sayılmaz
                # (sayılırsa göz rengi değişince gözün etrafında parlak halka oluşuyor).
                elif blueish or (style.get("brown_eyes") and not skin[y, x] and (hu <= 45 or hu >= 330) and s > 0.3 and 0.15 < v <= 0.6):
                    g[y, x] = 2
                continue
            if hand[y, x]:
                continue
            if style["outfit"](hu, s, v, y, up):
                g[y, x] = 3
                continue
            if style["acc"](hu, s, v, y, up):
                g[y, x] = 4
                continue
            if inside(x, y, reg["mouth"]) or inside(x, y, reg["neck"]):
                continue
            # Yüzdeki allık: çevresi çoğunlukla ten olan açık pembe pikseller saç değildir
            # (yüzün üstüne düşen saç telleri daha doygundur, onlar saç kalır).
            if is_blush(x, y, hu, s, v):
                continue
            if reddish and 0.15 <= s < 0.62 and v > 0.3:
                g[y, x] = 1
    # Saçın ışıltıları (çok açık pembe/beyaz) ve koyu gölge çizgileri: saça bitişik pembe/mor tonlu
    # sınıflanmamış pikselleri saça kat (koyu saç rengi seçilince pembe noktacıklar kalmasın).
    blocked = np.zeros((h, w), bool)
    for y in range(h):
        for x in range(w):
            blocked[y, x] = hand[y, x] or inside(x, y, reg["mouth"]) or inside(x, y, reg["neck"]) or skin[y, x] or any(
                ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1 for cx, cy, rx, ry, _ in rig["eyes"])
    for _ in range(4):
        add = []
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                if g[y, x] or blocked[y, x] or not img[y, x, 3] or tuple(img[y, x, :3]) == OUTLINE:
                    continue
                hu, s, v = hsv[y, x]
                # pembe/mor tonlu (saf beyaz önlük/bluz ve gri hariç), yüzdeki allık hariç
                if not ((hu >= 290 or hu <= 20) and s >= 0.06) or is_blush(x, y, hu, s, v):
                    continue
                n = (g[y - 1, x] == 1) + (g[y + 1, x] == 1) + (g[y, x - 1] == 1) + (g[y, x + 1] == 1)
                if n >= 2:
                    add.append((y, x))
        if not add:
            break
        for y, x in add:
            g[y, x] = 1
    # Kıyafet desenindeki pembe çiçekler saç değil: boyun altında, kenarlarının çoğu kıyafete değen
    # pembe adacıkları sabit bırak (saç tutamları kıyafetin dışına/arka plana da değer).
    seen1 = np.zeros((h, w), bool)
    for y, x in zip(*np.nonzero(g == 1)):
        if seen1[y, x] or y < neck_y:
            continue
        comp, stack, border = [], [(y, x)], []
        seen1[y, x] = True
        while stack:
            cy, cx = stack.pop()
            comp.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if not (0 <= ny < h and 0 <= nx < w):
                    border.append(0)
                elif g[ny, nx] == 1 and ny >= neck_y:
                    if not seen1[ny, nx]:
                        seen1[ny, nx] = True
                        stack.append((ny, nx))
                else:
                    border.append(g[ny, nx])
        cy0, cy1 = min(c[0] for c in comp), max(c[0] for c in comp) + 1
        cx0, cx1 = min(c[1] for c in comp), max(c[1] for c in comp) + 1
        roundish = cx1 - cx0 <= 16 and cy1 - cy0 <= 16 and 0.45 <= (cx1 - cx0) / (cy1 - cy0) <= 2.2
        if roundish and border and sum(1 for b in border if b == 3) >= 0.6 * len(border):
            for cy, cx in comp:
                g[cy, cx] = 0
    # Saçtaki koyu, doygun gölge çizgileri "aksesuar" rengine düşebiliyor; aksesuarlar büyük
    # bloklardır, küçük parçaları saça geri ver.
    seen = np.zeros((h, w), bool)
    for y, x in zip(*np.nonzero(g == 4)):
        if seen[y, x]:
            continue
        comp, stack = [], [(y, x)]
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            comp.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and g[ny, nx] == 4 and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(comp) < 25:
            for cy, cx in comp:
                hu, s, v = hsv[cy, cx]
                g[cy, cx] = 1 if (hu >= 300 or hu <= 15) else 0
    return g


if __name__ == "__main__":
    src, dst, look = sys.argv[1], sys.argv[2], sys.argv[3]
    img = np.array(Image.open(src).convert("RGBA"))
    g = classify(img, look)
    Image.fromarray(g, "L").save(dst)
    pal = np.array([[60, 60, 60], [255, 120, 200], [60, 160, 255], [60, 220, 120], [255, 200, 40]], np.uint8)
    vis = pal[g]
    vis[img[..., 3] == 0] = (20, 20, 24)
    Image.fromarray(vis).resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST).save("preview/groups_" + look + ".png")
    print(look, {k: int((g == v).sum()) for k, v in GROUPS.items()})
