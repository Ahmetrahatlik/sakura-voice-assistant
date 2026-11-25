"""Yapay zekâ görselini gerçek pixel art sprite'a çevirir.

Kullanım: python pixelize.py src/klasik.png out/klasik_base.png [blok] [renk]
- Arka plan (düz gri) kenarlardan flood-fill ile silinir.
- Görsel önce sınırlı palete indirilir, sonra her blokta en sık renk alınır (bulanıklık yok).
- Silüetin dışına 1 px koyu kontur eklenir ki her arka planda okunsun.
"""
import sys
from collections import deque

import numpy as np
from PIL import Image

OUTLINE = (43, 29, 46)


def flood(near, seeds):
    h, w = near.shape
    mask = np.zeros((h, w), bool)
    q = deque()
    for y, x in seeds:
        if near[y, x] and not mask[y, x]:
            mask[y, x] = True
            q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not mask[ny, nx]:
                mask[ny, nx] = True
                q.append((ny, nx))
    return mask


def remove_bg(rgb, tol=16, hole_tol=9, hole_min=40):
    h, w, _ = rgb.shape
    # Alt kenar karakterin gövdesini kestiği için tohum olarak kullanılmaz,
    # yoksa bluzun gri gölgeleri de arka planla birlikte silinir.
    border = np.concatenate([rgb[0], rgb[:, 0], rgb[:, -1]])
    bg = np.median(border, axis=0)
    diff = np.abs(rgb.astype(int) - bg).max(axis=2)
    seeds = [(0, x) for x in range(w)] + [(y, 0) for y in range(h)] + [(y, w - 1) for y in range(h)]
    mask = flood(diff < tol, seeds)
    # Saç tutamları arasında kapalı kalmış arka plan adacıkları (sıkı tolerans).
    near = (diff < hole_tol) & ~mask
    seen = np.zeros_like(near)
    for y, x in zip(*np.nonzero(near)):
        if seen[y, x]:
            continue
        comp = flood(near & ~seen, [(y, x)])
        seen |= comp
        if comp.sum() < hole_min:
            continue
        # Beyaz bluzun gri gölgeleri de arka plan rengine çok yakın; adacığı
        # yalnızca çevresi belirgin renkliyse (saç) sil, nötr/açık çevrede (bluz) bırak.
        ring = np.zeros_like(comp)
        ring[2:] |= comp[:-2]
        ring[:-2] |= comp[2:]
        ring[:, 2:] |= comp[:, :-2]
        ring[:, :-2] |= comp[:, 2:]
        ring &= ~comp & ~mask
        rc = rgb[ring].astype(int)
        if not ring.any() or ((rc.max(axis=1) - rc.min(axis=1)) > 30).mean() < 0.3:
            continue
        mask |= comp
    return ~mask


def cleanup(outa, bg, tol=42):
    """Küçültme sonrası kalan gri arka plan artıklarını siler.

    - Kenar saçağı: arka plan rengine yakın ve şeffaflığa komşu pikseller (2 tur soyulur).
    - Saç telleri arasındaki gri adacıklar: arka plana yakın, çevresi beyaz (bluz/önlük) olmayan küçük bölgeler.
    """
    rgb = outa[:, :, :3].astype(int)
    near = (np.abs(rgb - bg).max(axis=2) < tol) & (rgb.max(axis=2) - rgb.min(axis=2) < 45)
    h, w = near.shape
    for _ in range(2):
        a = outa[:, :, 3] > 0
        t = np.zeros_like(a)
        t[1:] |= ~a[:-1]
        t[:-1] |= ~a[1:]
        t[:, 1:] |= ~a[:, :-1]
        t[:, :-1] |= ~a[:, 1:]
        kill = a & near & t
        outa[kill] = 0
        near &= ~kill
    a = outa[:, :, 3] > 0
    seen = np.zeros_like(near)
    for y, x in zip(*np.nonzero(near & a)):
        if seen[y, x]:
            continue
        comp, stack, border = [], [(y, x)], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            comp.append((cy, cx))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if not (0 <= ny < h and 0 <= nx < w):
                    continue
                if near[ny, nx] and a[ny, nx]:
                    if not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
                elif a[ny, nx]:
                    border.append(rgb[ny, nx])
        white = sum(1 for c in border if min(c) > 215)
        if len(comp) <= 150 and border and white < 0.3 * len(border):
            for cy, cx in comp:
                outa[cy, cx] = 0


def pixelize(path, out, block=4, colors=40, clean_tol=42, method=Image.Quantize.MEDIANCUT, holes=True):
    """clean_tol: artık temizliğinde arka plana yakınlık eşiği; beyaz zeminde açık ten silinmesin diye düşük tutulur.
    method: palet yöntemi; FASTOCTREE küçük renk alanlarını (mavi gözler) medyan kesimden iyi korur.
    holes: saç tutamları arasındaki kapalı arka plan adacıklarını da sil (poses.py kapatır, kendi kuralı yakayı korur)."""
    im = Image.open(path).convert("RGB")
    rgb = np.array(im)
    fg = remove_bg(rgb) if holes else remove_bg(rgb, hole_min=10 ** 9)  # holes=False: saçla çevrili yaka silinmesin
    bgcol = np.median(np.concatenate([rgb[0], rgb[:, 0], rgb[:, -1]]), axis=0)
    q = im.quantize(colors=colors, method=method, dither=Image.Dither.NONE)
    pal = np.array(q.getpalette()[: colors * 3]).reshape(-1, 3)
    idx = np.array(q)
    h, w = idx.shape
    H, W = h // block, w // block
    outa = np.zeros((H, W, 4), np.uint8)
    for Y in range(H):
        for X in range(W):
            sl = (slice(Y * block, (Y + 1) * block), slice(X * block, (X + 1) * block))
            f = fg[sl]
            if f.mean() < 0.5:
                continue
            vals = idx[sl][f]
            c = np.bincount(vals).argmax()
            outa[Y, X, :3] = pal[c]
            outa[Y, X, 3] = 255
    cleanup(outa, bgcol, clean_tol)
    a = outa[:, :, 3] > 0
    ring = np.zeros_like(a)
    ring[1:] |= a[:-1]
    ring[:-1] |= a[1:]
    ring[:, 1:] |= a[:, :-1]
    ring[:, :-1] |= a[:, 1:]
    ring &= ~a
    outa[ring] = (*OUTLINE, 255)
    Image.fromarray(outa, "RGBA").save(out)
    return outa


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    block = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    colors = int(sys.argv[4]) if len(sys.argv) > 4 else 40
    a = pixelize(src, dst, block, colors)
    print(dst, a.shape)
