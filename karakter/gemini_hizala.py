"""Gemini sonucunu yuz.png'ye hizalar (benzerlik dönüşümü, göz/ağız dışındaki bölgeler üzerinden)."""
import math, os, sys, json
import numpy as np
from PIL import Image
D = os.environ.get('SAKURA_CIZIM_KLASORU', 'cizimler').rstrip('/\\') + '/'   # karakter çizimlerinin klasörü
N = 400
ref = Image.open(D + 'gonder/yuz.png').convert('RGB').resize((N, N), Image.LANCZOS)
R = np.asarray(ref.convert('L'), float)
# yuz.png = sheet (96,50)-(296,250); gözler sheet'te (168.5,147.6),(224.3,134.3), ağız (198,177): N/200 ölçek
k = N / 200
eyes = [((168.5 - 96) * k, (147.6 - 50) * k), ((224.3 - 96) * k, (134.3 - 50) * k)]
mouth = ((198.5 - 96) * k, (177.5 - 50) * k)
d = 55.8 * k
yy, xx = np.mgrid[0:N, 0:N]
ex = np.zeros((N, N), bool)
for x, y in eyes:
    ex |= ((xx - x) / (0.6 * d)) ** 2 + ((yy - y) / (0.45 * d)) ** 2 < 1
ex |= ((xx - mouth[0]) / (0.5 * d)) ** 2 + ((yy - mouth[1]) / (0.4 * d)) ** 2 < 1
W = (~ex).astype(float)

def warp(src, s, th, tx, ty, size=N):
    # çıktı (x,y) → kaynak: kaynak = s*R(th)*(p - c) + c + t   (kaynak N ölçeğinde)
    c = size / 2
    a, b = s * math.cos(th), s * math.sin(th)
    sc = src.width / size
    coef = (a * sc, -b * sc, (c - a * c + b * c + tx) * sc, b * sc, a * sc, (c - b * c - a * c + ty) * sc)
    return src.transform((size, size), Image.AFFINE, coef, resample=Image.BICUBIC)

def err(src, p):
    g = np.asarray(warp(src, *p).convert('L'), float)
    return (np.abs(g - R) * W).sum() / W.sum()

def fit(path):
    src = Image.open(path).convert('RGB')
    best = (1.0, 0.0, 0.0, 0.0); be = err(src, best)
    for step in [(0.02, 0.01, 8), (0.01, 0.005, 4), (0.004, 0.002, 2), (0.002, 0.001, 1), (0.001, 0.0005, 0.5)]:
        ds, dt, dp = step
        improved = True
        while improved:
            improved = False
            for i, dv in [(0, ds), (0, -ds), (1, dt), (1, -dt), (2, dp), (2, -dp), (3, dp), (3, -dp)]:
                p = list(best); p[i] += dv
                e = err(src, p)
                if e < be:
                    be, best, improved = e, tuple(p), True
    return best, be, err(src, (1.0, 0, 0, 0))

if __name__ == '__main__':
    res = {}
    import glob
    for n in sys.argv[2:] or sorted(os.path.basename(f)[:-4] for f in glob.glob(D + 'geri-koy/*.png')):
        p, e, e0 = fit(D + 'geri-koy/' + n + '.png')
        res[n] = p
        print(n, 'ölçek %.4f açı %.3f° kayma %.1f,%.1f px(400)' % (p[0], math.degrees(p[1]), p[2], p[3]), 'hata %.2f (hizasız %.2f)' % (e, e0))
    json.dump(res, open(sys.argv[1], 'w'))
