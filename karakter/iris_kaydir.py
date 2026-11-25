"""Yana bakış: Sakura'nın kendi irisini göz açıklığı içinde yatay kaydırır (yeni çizim yok, orijinal pikseller).

İris = mavi bölgenin dolu elipsi (göz bebeği ve parlamalar dahil); açıklık = iris + çevresindeki göz beyazı.
Açıklık önce göz beyazıyla doldurulur, iris dx kadar kaydırılıp açıklığa kırpılarak yeniden konur.
Kullanım: python iris_kaydir.py <kaynak.png> <çıktı.png> <dx: gözler arası mesafenin oranı, + sağa>
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

DENEME = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme")
sys.path.insert(0, DENEME)
import smooth  # noqa: E402
from poses import hsv_of, label  # noqa: E402


def shift_eyes(rgb, frac):
    eyes = smooth.blue_eyes(rgb)
    d = float(eyes[1][0] - eyes[0][0])
    out = rgb.astype(float).copy()
    hh, ss, vv = hsv_of(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))
    H, W = rgb.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    dx = int(round(frac * d))
    for cx, cy in eyes:
        win = (abs(xx - cx) < 0.45 * d) & (abs(yy - cy) < 0.32 * d)
        blue = win & (hh >= 185) & (hh <= 270) & (ss >= 0.2) & (vv >= 0.2)
        lab, n = label(blue)
        i = np.argmax(np.bincount(lab.ravel())[1:]) + 1
        ys, xs = np.nonzero(lab == i)
        icx, icy = xs.mean(), ys.mean()
        rx, ry = ((xs.max() - xs.min()) / 2 + 1) * 1.12, ((ys.max() - ys.min()) / 2 + 1) * 1.08  # koyu dış halka dahil
        iris = ((xx - icx) / rx) ** 2 + ((yy - icy) / ry) ** 2 <= 1.0
        white = win & ~iris & (vv > 0.78) & (ss < 0.18) & (((xx - icx) / (rx * 2.2)) ** 2 + ((yy - icy) / (ry * 1.1)) ** 2 <= 1)
        opening = iris | white
        wcol = np.median(rgb[white], axis=0) if white.any() else np.array([250, 250, 252])
        layer = rgb.astype(float).copy()
        layer[opening] = wcol
        moved = np.zeros_like(iris)
        moved[:, max(dx, 0):W + min(dx, 0)] = iris[:, max(-dx, 0):W + min(-dx, 0)]
        src = np.roll(rgb.astype(float), dx, axis=1)
        # iris yumuşak kenarla konur ve açıklığa (1 px genişletilmiş) kırpılır: tırtıklı kesik kalmasın
        ma = np.array(Image.fromarray((moved * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))) / 255.0
        op = np.array(Image.fromarray((opening * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) > 0
        op = np.array(Image.fromarray((op * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))) / 255.0
        a = (ma * op)[..., None]
        layer = layer * (1 - a) + src * a
        # açıklığın kenarı yumuşak (göz kapağı çizgisine yapışık pikseller sert kalmasın)
        m = np.array(Image.fromarray((opening * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))) / 255.0
        m = np.maximum(m, opening.astype(float))[..., None]
        out = out * (1 - m) + layer * m
    return np.clip(out, 0, 255).astype(np.uint8)


if __name__ == "__main__":
    src, dst, frac = sys.argv[1], sys.argv[2], float(sys.argv[3])
    a = np.array(Image.open(src).convert("RGB"))
    Image.fromarray(shift_eyes(a, frac)).save(dst)
    print("tamam", dst)
