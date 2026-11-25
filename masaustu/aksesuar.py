"""Aksesuarlar (gözlük, kulaklık, kedi kulağı, bayrak beresi): smooth.py bunları kaynak görüntülere, başın göz
konumuna göre takar; her aksesuar ayrı bir görünüm olur (frames/yeni-<ad>). SMOOTH_AKS=<ad> ile seçilir.

Katmanlar src/aksesuar/<ad>.png: Sakura'nın yakın yüz görselinin (bas.png) hizasında, aksesuarın kendisi saydam
zeminde; aksesuar.json'daki "eyes" o görseldeki iki göz merkezi. Bir kareye takarken katman, katmandaki gözler
karedeki gözlere oturacak şekilde ölçeklenip döndürülür. Gözlük çizim değil: göz konumundan ince yuvarlak çerçeve
çizilir (kâkül önde kalır).
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "src", "aksesuar")
NAMES = ("gozluk", "kulaklik", "kedi", "bere")
AKS = os.environ.get("SMOOTH_AKS", "")
WALK = ("kedi", "bere")  # yürürken (yandan) yalnız bunlar; önden çizilmiş gözlük ve kulaklık yanda tutmuyor

_meta = None
_layers = {}


def meta():
    global _meta
    if _meta is None:
        _meta = json.load(open(os.path.join(DIR, "aksesuar.json"), encoding="utf-8"))
    return _meta


def layer(name):
    if name not in _layers:
        _layers[name] = Image.open(os.path.join(DIR, name + ".png")).convert("RGBA")
    return _layers[name]


def _geom(eyes):
    (x0, y0), (x1, y1) = eyes
    return math.hypot(x1 - x0, y1 - y0), math.atan2(y1 - y0, x1 - x0), ((x0 + x1) / 2, (y0 + y1) / 2)


def top_reach(name, d):
    """Aksesuarın göz ortasının ne kadar üstüne çıktığı (göz arası mesafesi d olan karede, piksel)."""
    if name == "gozluk":
        return 0.0
    E = meta()["eyes"]
    dl, _, (mx, my) = _geom(E)
    top = layer(name).getbbox()[1]
    return (my - top) * d / dl


def _paste_layer(a, name, eyes, flip=False):
    """Katmanı karedeki gözlere oturtup a'nın (RGBA) üstüne bindirir. flip: katman aynalanır (yandan yürürken
    berenin sarkık ucu geriye düşsün)."""
    E = meta()["eyes"]
    dl, al, (lx, ly) = _geom(E)
    d, ang, (mx, my) = _geom(eyes)
    k = d / dl
    L = layer(name)
    if flip:
        L = L.transpose(Image.FLIP_LEFT_RIGHT)
        E = [(L.width - E[1][0], E[1][1]), (L.width - E[0][0], E[0][1])]
        # amblem (beyaz ay-yıldız) aynada ters döner: kendi kutusunda geri çevrilir, bayrak doğru kalsın
        arr = np.array(L)
        white = (arr[..., :3].min(-1) > 200) & (arr[..., 3] > 200)
        if white.any():
            ys, xs = np.nonzero(white)
            x0, x1, y0, y1 = xs.min() - 3, xs.max() + 4, ys.min() - 3, ys.max() + 4
            arr[y0:y1, x0:x1] = arr[y0:y1, x0:x1][:, ::-1]
            L = Image.fromarray(arr, "RGBA")
        dl, al, (lx, ly) = _geom(E)
    # önce LANCZOS ile küçült (önceden çarpılmış alfa: kenarda renk kaçmasın), sonra döndür + taşı
    sw, sh = max(1, round(L.width * k)), max(1, round(L.height * k))
    small = L.convert("RGBa").resize((sw, sh), Image.LANCZOS).convert("RGBA")
    th = ang - al
    c, s = math.cos(th), math.sin(th)
    # çıktı (x, y) → küçük katman: q = R(-th)·(p - m) + l·k
    lxk, lyk = lx * k, ly * k
    coef = (c, s, lxk - c * mx - s * my, -s, c, lyk + s * mx - c * my)
    h, w = a.shape[:2]
    lay = small.transform((w, h), Image.AFFINE, coef, resample=Image.BICUBIC)
    base = Image.fromarray(a, "RGBA")
    base.alpha_composite(lay)
    return np.array(base), np.array(lay)[..., 3]


def _glasses(a, eyes):
    """İnce yuvarlak gözlük: camlar göz merkezlerinde (azıcık aşağı), yarıçap 0,355d; yeşil saç (kâkül) önde kalır."""
    g = meta()["gozluk"]
    (x0, y0), (x1, y1) = eyes
    d, ang, _ = _geom(eyes)
    ux, uy = math.cos(ang), math.sin(ang)
    px, py = -uy, ux  # aşağı
    r, dn = g["r"] * d, g["dn"] * d
    lw = max(g["lw"] * d, 0.9)
    ss = 4
    h, w = a.shape[:2]
    L = Image.new("L", (w * ss, h * ss), 0)
    dr = ImageDraw.Draw(L)
    width = max(1, round(lw * ss))
    cs = [(x0 + px * dn, y0 + py * dn), (x1 + px * dn, y1 + py * dn)]
    for cx, cy in cs:
        dr.ellipse([(cx - r) * ss, (cy - r) * ss, (cx + r) * ss, (cy + r) * ss], outline=255, width=width)
    p0 = (cs[0][0] + ux * r, cs[0][1] + uy * r)
    p1 = (cs[1][0] - ux * r, cs[1][1] - uy * r)
    mid = ((p0[0] + p1[0]) / 2 - px * 0.12 * d, (p0[1] + p1[1]) / 2 - py * 0.12 * d)
    pts = [(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * mid[0] + t * t * p1[0]) * ss,
            ((1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * mid[1] + t * t * p1[1]) * ss) for t in np.linspace(0, 1, 20)]
    dr.line(pts, fill=255, width=width)
    for (cx, cy), sg in ((cs[0], -1), (cs[1], 1)):
        e = (cx + sg * ux * r, cy + sg * uy * r)
        f = (e[0] + sg * ux * 0.18 * d - px * 0.04 * d, e[1] + sg * uy * 0.18 * d - py * 0.04 * d)
        dr.line([(e[0] * ss, e[1] * ss), (f[0] * ss, f[1] * ss)], fill=255, width=width)
    m = np.asarray(L.resize((w, h), Image.LANCZOS), float) / 255
    rgb = a[..., :3].astype(float)
    dom = (rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2])) / np.maximum(rgb[..., 1], 1)
    m = m * (1 - np.clip(dom / 0.3, 0, 1)) * (a[..., 3] > 0)  # kâkül önde; boşlukta (saydam) çizilmez
    out = a.copy()
    out[..., :3] = (rgb * (1 - m[..., None]) + np.array(g["renk"], float) * m[..., None]).round().astype(np.uint8)
    return out, (m * 255).astype(np.uint8)


def wear(a, eyes, name=None, flip=False):
    """a (RGBA, uint8) üstüne aksesuar; (yeni kare, aksesuar maskesi 0-255). eyes: [(x, y), (x, y)] soldan sağa."""
    name = name or AKS
    if not name or eyes is None:
        return a, np.zeros(a.shape[:2], np.uint8)
    if name == "gozluk":
        return _glasses(a, eyes)
    return _paste_layer(a, name, eyes, flip)


def pad_top(a, n):
    """Kareye üstten n px saydam pay."""
    if n <= 0:
        return a
    return np.concatenate([np.zeros((n,) + a.shape[1:], a.dtype), a], 0)


def eyes_any(rgba, min_px=3):
    """Küçük yüzlerde de çalışan göz bulucu: en büyük iki parlak mavi bölge (boyutları yakın, aynı hizada)."""
    import poses
    hh, ss, vv = poses.hsv_of(rgba)
    lab, n = poses.label((hh >= 185) & (hh <= 270) & (ss >= 0.35) & (vv >= 0.45) & (rgba[..., 3] > 0))
    if n < 2:
        return None
    sizes = np.bincount(lab.ravel())[1:]
    top2 = np.argsort(-sizes)[:2]
    if sizes[top2[1]] < max(min_px, 0.3 * sizes[top2[0]]):
        return None
    pts = sorted((np.nonzero(lab == i + 1)[1].mean(), np.nonzero(lab == i + 1)[0].mean()) for i in top2)
    d = pts[1][0] - pts[0][0]
    if d <= 0 or abs(pts[1][1] - pts[0][1]) > 0.5 * d:
        return None
    return pts
