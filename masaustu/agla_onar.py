"""Ağlama kareleri: temizlik gözdeki parıltı noktalarını deliyor, çene yanındaki beyaz arka planı bırakıyor.
smooth.py sonrası çalıştır: ikisi de aynı karedeki üzgün ifadeden (renk + grup) düzeltilir."""
import glob
import os
import sys
import numpy as np
from PIL import Image

kok = os.path.join(sys.argv[1] if len(sys.argv) > 1 else "frames/yeni", "emotes")
Y0, Y1, X0, X1 = 78, 124, 98, 218  # 256 px'lik karede göz bandı
top = 0
for p in sorted(glob.glob(os.path.join(kok, "agla", "*.png"))):
    ad = os.path.basename(p)
    u = os.path.join(kok, "uzgun", ad)
    if not os.path.exists(u):
        continue
    a = np.array(Image.open(p).convert("RGBA"))
    b = np.array(Image.open(u).convert("RGBA"))
    if a.shape != b.shape or a.shape[0] < Y1:
        continue
    bant = np.zeros(a.shape[:2], bool)
    bant[Y0:Y1, X0:X1] = True
    h = (a[..., 3] < 128) & (b[..., 3] >= 128) & bant
    a[h] = b[h]
    # üzgün karede de delik olan parıltılar: etrafı dolu küçük saydam noktalar beyazla kapanır
    op = a[..., 3] >= 128
    kom = sum(np.roll(np.roll(op, dy, 0), dx, 1).astype(int) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    for _ in range(3):
        pr = ~op & bant & (kom >= 5)
        if not pr.any():
            break
        a[pr] = (238, 242, 250, 255)
        h = h | pr
        op = a[..., 3] >= 128
        kom = sum(np.roll(np.roll(op, dy, 0), dx, 1).astype(int) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
    # çene yanı / boyun arası beyaz arka plan: üzgün karede silinmiş, ağlamada kalmış → aynı yerde saydam
    bos = (a[..., 3] >= 128) & (b[..., 3] < 128) & ~bant & (a[..., :3].min(-1) >= 190)
    a[bos] = b[bos]
    h = h | bos
    if not h.any():
        continue
    Image.fromarray(a).save(p)
    top += int(h.sum())
    gp, gu = os.path.join(kok, "agla", "groups", ad), os.path.join(kok, "uzgun", "groups", ad)
    if os.path.exists(gp) and os.path.exists(gu):
        ga, gb = Image.open(gp), Image.open(gu)
        ma, mb = np.array(ga), np.array(gb)
        ma[h] = mb[h]
        ma[h & (b[..., 3] < 128)] = 0
        Image.fromarray(ma, ga.mode).save(gp)
print("tamamlanan piksel", top)
