"""Sakura'nın yüz ifadeleri: gözleri, ağzı ve allığı piksel düzeyinde yeniden çizer, üstüne efekt ekler.

Her ifade bir karenin (RGBA numpy dizisi) kopyasını alıp değiştirir. Yüz koordinatları görünüme
özeldir (FACE). animate.py her ifade için ayrı kare seti üretir: frames/<görünüm>/emotes/<ifade>/.
"""
import numpy as np

DARK = (43, 29, 46, 255)
LIP = (150, 50, 70, 255)
MOUTH_IN = (110, 30, 50, 255)
TONGUE = (235, 120, 135, 255)
BLUSH = (240, 120, 140, 255)
HEART = [(230, 60, 100, 255), (255, 150, 180, 255)]
SPARK = (255, 236, 140, 255)
NOTE = (120, 90, 220, 255)
SWEAT = (150, 205, 255, 255)
BANG = (245, 170, 40, 255)
TEAR = (120, 185, 255, 255)
GLOOM = (110, 120, 200, 255)
ZZZ = (170, 160, 240, 255)

FACE = {
    "klasik": {
        "eyes": [(85, 78), (122, 70)],      # göz merkezleri (sol, sağ)
        "eye_r": (12, 8),
        "mouth": (106, 97),                 # ağız merkezi
        "mouth_box": (96, 90, 118, 104),
        "cheeks": [(80, 88), (127, 82)],
        "tilt": -0.2,                       # baş sağa doğru hafif yukarı eğik (y/x)
        "fx_left": (6, 14),                 # efektlerin yüzen noktaları (sol üstteki boşluk)
        "fx_right": (166, 0),
        "sweat": (140, 50),
    }
}

# rig.py'nin otomatik bulduğu yeni görünümler
import json as _json
import os as _os
_rigs = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "rigs.json")
if _os.path.exists(_rigs):
    for _name, _r in _json.load(open(_rigs, encoding="utf-8")).items():
        FACE[_name] = _r["face"]


HEART_PX = [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."]
SPARK_PX = ["..#..", "..#..", "#####", "..#..", "..#.."]
SPARK_SM = [".#.", "###", ".#."]
NOTE_PX = ["..###", "..#.#", "..#..", "..#..", "###..", "###.."]
BANG_PX = ["##", "##", "##", "##", "##", "..", "##"]
SWEAT_PX = [".#.", "###", "###", ".#."]
Z_PX = ["####", "..#.", ".#..", "####"]
GLOOM_PX = ["#.#.#", "#.#.#", "#.#.#", "#...#", "#...."]


def is_skin(p):
    r, g, b = int(p[0]), int(p[1]), int(p[2])
    return p[3] and r > 215 and g > 165 and b > 130 and r - b > 25


def put(img, x, y, c):
    h, w, _ = img.shape
    if 0 <= x < w and 0 <= y < h:
        img[y, x] = c


def stamp(img, pattern, x0, y0, color, scale=2):
    """Deseni scale kat büyütüp 1 px koyu konturla basar (her arka planda okunsun)."""
    cells = [(x0 + i * scale + a, y0 + j * scale + b)
             for j, row in enumerate(pattern) for i, ch in enumerate(row) if ch == "#"
             for a in range(scale) for b in range(scale)]
    filled = set(cells)
    for x, y in cells:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if (x + dx, y + dy) not in filled:
                put(img, x + dx, y + dy, DARK)
    for x, y in cells:
        put(img, x, y, color)


def skin_of(img, f):
    cx, cy = f["mouth"]
    return tuple(int(v) for v in img[cy - 8, cx])


def erase(img, box, skin):
    """Ağzı siler: kutudaki ağız içi (kırmızı/pembe) ve dudak çizgisi pikselleri, yalnızca çevresi ten olanlar.

    Çene konturu, boyun gölgesi ve kıyafet kutunun içine girse de korunur; dolgu, aynı sütunda hemen
    yukarıdaki ten pikselinden alınır ki yüzün gölgesi bozulmasın.
    """
    import colorsys
    x0, y0, x1, y1 = box
    h, w, _ = img.shape
    src = img.copy()
    skin_near = lambda y, x: sum(1 for yy in range(max(y - 2, 0), min(y + 3, h)) for xx in range(max(x - 2, 0), min(x + 3, w))
                                 if is_skin(src[yy, xx]))
    def mouthy(y, x):
        p = src[y, x]
        if not p[3] or is_skin(p) or tuple(int(c) for c in p[:3]) == DARK[:3]:
            return False
        hu, s, v = colorsys.rgb_to_hsv(*(int(c) / 255 for c in p[:3]))
        # ağız içi/dudak: doygun kırmızı-pembe ya da koyu; çene altındaki soluk pembe gölge ağız değildir
        return ((hu * 360 >= 320 or hu * 360 <= 25) and s > 0.32) or v < 0.5

    y1 -= 3  # kutunun alt payı çene/boyun gölgesine denk gelir; ağız oraya inmez
    mx0, mx1 = x0 + (x1 - x0) // 4, x1 - (x1 - x0) // 4
    my0, my1 = y0 + (y1 - y0) // 4, y1 - (y1 - y0) // 4
    stack = [(y, x) for y in range(my0, my1) for x in range(mx0, mx1) if mouthy(y, x) and skin_near(y, x) >= 3]
    region = set(stack)
    while stack:
        cy_, cx_ = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ny, nx = cy_ + dy, cx_ + dx
            if y0 <= ny < y1 and x0 <= nx < x1 and (ny, nx) not in region and mouthy(ny, nx):
                region.add((ny, nx))
                stack.append((ny, nx))
    for y, x in region:
        if True:
            fill = skin
            for yy in range(y - 1, max(y - 12, 0), -1):
                if is_skin(src[yy, x]):
                    fill = tuple(int(c) for c in src[yy, x])
                    break
            img[y, x] = fill


def is_hair(p):
    import colorsys
    if not p[3]:
        return False
    h, sat, v = colorsys.rgb_to_hsv(int(p[0]) / 255, int(p[1]) / 255, int(p[2]) / 255)
    h *= 360
    # Saç pembesi ~345-355°; göz kapağındaki ten gölgesi (~5°, düşük doygunluk) saç sayılmaz.
    return (h >= 300 or (h <= 15 and sat >= 0.28)) and 0.18 <= sat <= 0.7 and v > 0.45 and not is_skin(p)


def clear_eye(img, cx, cy, rx, ry, skin, ymax=None):
    """Gözü siler: yalnızca göz piksellerini (iris, beyaz, kirpik) tene çevirir.

    Elipsin içine giren saç tutamlarına ve onların koyu konturlarına dokunmaz; yoksa ten rengi
    saçın üstüne taşar. Doldurma rengi aynı sütunda aşağıdaki ilk ten pikselinden alınır ki
    yüzün gölgesi korunsun.
    """
    h, w, _ = img.shape
    src = img.copy()
    hair = lambda y, x: 0 <= y < h and 0 <= x < w and is_hair(src[y, x])
    inside = lambda y, x: ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1
    # Gerçek saç teli elipsin dışındaki saçtan içeri uzanır; göz kapağı/iris pembeleri içeride kopuk kalır.
    real_hair = set()
    stack = [(y, x) for y in range(cy - ry - 3, cy + ry + 4) for x in range(cx - rx - 3, cx + rx + 4)
             if not inside(y, x) and hair(y, x)]
    real_hair.update(stack)
    while stack:
        yy, xx = stack.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = yy + dy, xx + dx
            if (ny, nx) not in real_hair and inside(ny, nx) and hair(ny, nx):
                real_hair.add((ny, nx))
                stack.append((ny, nx))
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            if ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 > 1:
                continue
            if ymax is not None and y > ymax + round((x - cx) * -0.2):
                continue
            p = src[y, x]
            if is_skin(p) or (y, x) in real_hair:
                continue
            if int(p[:3].sum()) < 330 and sum(hair(y + dy, x + dx) for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1))) >= 2:
                continue  # saç tutamının koyu konturu
            fill = skin
            for yy in range(y + 1, min(y + 14, h)):
                if is_skin(src[yy, x]) and not inside(yy, x):
                    fill = tuple(int(v) for v in src[yy, x])
                    break
            img[y, x] = fill
    # Göz beyazı ten rengine çok yakınsa yukarıda ten sayılıp kalır: elipsin içinde, gözün altındaki tenden
    # belirgin farklı açık pikselleri de o tenle değiştir.
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            if not inside(y, x) or (y, x) in real_hair or not src[y, x, 3]:
                continue
            if ymax is not None and y > ymax + round((x - cx) * -0.2):
                continue
            ref = None
            for yy in range(cy + ry + 1, min(cy + ry + 8, h)):
                if is_skin(src[yy, x]):
                    ref = src[yy, x]
                    break
            if ref is not None and is_skin(src[y, x]) and abs(src[y, x, :3].astype(int) - ref[:3].astype(int)).max() > 22:
                img[y, x] = tuple(int(v) for v in ref)


def erase_eye(img, f, idx, skin):
    (cx, cy), (rx, ry) = f["eyes"][idx], f["eye_r"]
    clear_eye(img, cx, cy, rx, ry, skin)


def arc(img, cx, cy, half_w, height, tilt, color, up=True, thick=2, avoid_hair=False):
    """Eğik bir yay çizer: up=True ise ∩ (mutlu kapalı göz), değilse ∪ (gülümseme)."""
    steps = half_w * 6
    for k in range(-steps, steps + 1):
        t = k / steps
        x = cx + t * half_w
        bump = height * (1 - t * t)
        y = cy + tilt * t * half_w + (-bump if up else bump)
        for d in range(thick):
            px, py = int(round(x)), int(round(y)) + d
            if avoid_hair and 0 <= py < img.shape[0] and 0 <= px < img.shape[1] and is_hair(img[py, px]):
                continue
            put(img, px, py, color)


def happy_eye(img, f, idx, skin):
    erase_eye(img, f, idx, skin)
    cx, cy = f["eyes"][idx]
    arc(img, cx, cy + 3, 8, 5, f["tilt"], DARK, up=True, avoid_hair=True)


def sleepy_eye(img, f, idx, skin):
    """Yarı kapalı göz: üst yarıyı göz kapağıyla örter, iris alttan görünür."""
    (cx, cy), (rx, ry) = f["eyes"][idx], f["eye_r"]
    clear_eye(img, cx, cy, rx, ry, skin, ymax=cy - 1)
    arc(img, cx, cy - 1, 9, 1, f["tilt"], DARK, up=False, thick=2, avoid_hair=True)


def mouth(img, f, kind, skin):
    if kind == "open":
        return  # orijinal açık gülümseme
    erase(img, f["mouth_box"], skin)
    cx, cy = f["mouth"]
    t = f["tilt"]
    if kind == "smile":
        arc(img, cx, cy - 1, 5, 2, t, LIP, up=False, thick=1)
    elif kind == "cat":  # ω
        arc(img, cx - 3, cy - 1, 3, 2, t, LIP, up=False, thick=1)
        arc(img, cx + 3, cy - 2, 3, 2, t, LIP, up=False, thick=1)
    elif kind == "o":
        for y in range(cy - 3, cy + 4):
            for x in range(cx - 3, cx + 3):
                d = ((x + .5 - cx) / 2.6) ** 2 + ((y + .5 - cy) / 3.4) ** 2
                if d <= 1:
                    put(img, x, y, MOUTH_IN if d < 0.55 else LIP)
    elif kind == "frown":
        arc(img, cx, cy + 1, 4, 2, t, LIP, up=True, thick=1)
    elif kind == "yawn":
        for y in range(cy - 2, cy + 3):
            for x in range(cx - 2, cx + 2):
                d = ((x + .5 - cx) / 1.8) ** 2 + ((y + .5 - cy) / 2.6) ** 2
                if d <= 1:
                    put(img, x, y, MOUTH_IN if d < 0.5 else LIP)
    elif kind == "wavy":
        for i, x in enumerate(range(cx - 5, cx + 6)):
            put(img, x, cy + round(t * (x - cx)) + (0 if i % 4 in (0, 1) else 1), LIP)


def blush(img, f, heavy):
    for cx, cy in f["cheeks"]:
        if heavy:
            for k in range(3):  # anime "///" çizgileri
                for d in range(4):
                    put(img, cx - 4 + k * 3 + d // 2, cy + 2 - d, BLUSH)
        else:
            for x in range(cx - 3, cx + 3):
                put(img, x, cy, BLUSH)


def fx(img, f, kind, i):
    lx, ly = f["fx_left"]
    rx, ry = f["fx_right"]
    if kind == "sparkle":
        big = i % 4 < 2
        stamp(img, SPARK_PX if big else SPARK_SM, lx + (0 if big else 2), ly + (0 if big else 2), SPARK)
        stamp(img, SPARK_SM if big else SPARK_PX, lx + 18, ly + 40, SPARK)
        stamp(img, SPARK_SM, rx + 4, ry + 2 + (i % 4 < 2), SPARK, scale=2)
    elif kind == "hearts":
        for n, (x, y0) in enumerate(((lx, ly + 60), (lx + 16, ly + 46))):
            y = y0 - ((i * 3 + n * 17) % 50)
            stamp(img, HEART_PX, x, y, HEART[0], scale=3)
            put(img, x + 2, y + 2, HEART[1])
            put(img, x + 3, y + 2, HEART[1])
    elif kind == "notes":
        stamp(img, NOTE_PX, lx + 2, ly + 4 - 2 * (i % 4 < 2), NOTE, scale=3)
        stamp(img, NOTE_PX, lx + 18, ly + 34 + 2 * (i % 4 < 2), NOTE)
    elif kind == "bang":
        stamp(img, BANG_PX, lx + 12, ly + 4 + (i % 2), BANG, scale=3)
    elif kind == "sweat":
        sx, sy = f["sweat"]
        stamp(img, SWEAT_PX, sx, sy + (i % 6) // 2, SWEAT)
    elif kind == "tear":
        cx, cy = f["eyes"][0]
        stamp(img, SWEAT_PX, cx - 6, cy + 6 + (i % 8), TEAR, scale=1)
    elif kind == "zzz":
        for n, (x, y0, sc) in enumerate(((lx + 4, ly + 40, 2), (lx + 14, ly + 24, 3), (lx + 26, ly + 4, 4))):
            if (i // 3) % 4 >= n:
                stamp(img, Z_PX, x, y0 - (i % 3), ZZZ, scale=sc)
    elif kind == "wink_star":
        stamp(img, SPARK_PX if i % 4 < 2 else SPARK_SM, lx + 4, ly + 8, SPARK)
        stamp(img, SPARK_SM if i % 4 < 2 else SPARK_PX, rx + 2, ry + 2, SPARK)


# ifade adı: (sol göz, sağ göz, ağız, allık, efekt, göz kırpsın mı)
EMOTES = {
    "mutlu":    ("open", "open", "open", "light", "sparkle", True),
    "nese":     ("happy", "happy", "open", "light", "notes", False),
    "goz_kirp": ("open", "happy", "smile", "light", "wink_star", False),
    "sevgi":    ("happy", "happy", "cat", "heavy", "hearts", False),
    "gurur":    ("happy", "happy", "cat", "light", "sparkle", False),
    "utangac":  ("open", "open", "wavy", "heavy", "sweat", True),
    "saskin":   ("open", "open", "o", None, "bang", True),
    "uzgun":    ("open", "open", "frown", None, "tear", True),
    "agla":     ("open", "open", "frown", None, None, True),
    "uykulu":   ("sleepy", "sleepy", "yawn", None, "zzz", False),
    "sinirli":  ("open", "open", "frown", None, None, True),
    "dusunce":  ("open", "open", "smile", None, None, True),
}


def apply(img, look, name, i):
    f = FACE[look]
    le, re_, m, bl, effect, _ = EMOTES[name]
    out = img.copy()
    skin = skin_of(out, f)
    if le == "happy":
        happy_eye(out, f, 0, skin)
    if re_ == "happy":
        happy_eye(out, f, 1, skin)
    if le == "sleepy":
        sleepy_eye(out, f, 0, skin)
    if re_ == "sleepy":
        sleepy_eye(out, f, 1, skin)
    mouth(out, f, m, skin)
    if bl:
        blush(out, f, bl == "heavy")
    if effect:
        fx(out, f, effect, i)
    return out
