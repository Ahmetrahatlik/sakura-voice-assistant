"""LivePortrait karelerini (yeşil saç) kullanıcının saç rengine boyayıp önizleme MP4'ü yapar.

Saç ayrıştırma sakura-deneme/smooth.py'deki unmix_hair ile; renk = hedef rengin tonu, gölge oranla.
Kullanım: python onizle_renk.py <kare klasörü> <çıktı.mp4> [#saçrengi] [genişlik=384]
"""
import glob
import os
import subprocess
import sys

import numpy as np
from PIL import Image

DENEME = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme")
sys.path.insert(0, DENEME)
sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "skills", "sakura-piksel", "scripts"))
import smooth  # noqa: E402
import sp_common  # noqa: E402


def recolor(a, hexcol):
    t = np.array([int(hexcol[i:i + 2], 16) for i in (1, 3, 5)], float) / 255
    mx, mn = t.max(), t.min()
    lt = (mx + mn) / 2
    import colorsys
    ht, _, st = colorsys.rgb_to_hls(*t)
    w, s, under = smooth.unmix_hair(a)
    m = w > 0
    out = a[..., :3].astype(float)
    if m.any():
        mean_s = np.median(s[w >= 0.9]) if (w >= 0.9).any() else 0.5
        l = np.clip(s[m] / max(mean_s, 1e-3) * lt, 0, 1)  # gölge: hedef açıklığa oranla
        hair = sp_common.hls_to_rgb(np.full(l.shape, ht), l, np.full(l.shape, st)).astype(float)
        out[m] = w[m, None] * hair + (1 - w[m, None]) * under[m]
    return np.clip(out, 0, 255).astype(np.uint8)


def main():
    src, mp4 = sys.argv[1], sys.argv[2]
    col = sys.argv[3] if len(sys.argv) > 3 else "#2e2a3a"
    width = int(sys.argv[4]) if len(sys.argv) > 4 else 384
    tmp = os.path.join(src, "_renk")
    os.makedirs(tmp, exist_ok=True)
    fs = sorted(glob.glob(os.path.join(src, "f_*.png")))
    for i, f in enumerate(fs):
        im = Image.open(f).convert("RGBA")
        im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
        Image.fromarray(recolor(np.array(im), col)).save(os.path.join(tmp, "r_%03d.png" % i))
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-framerate", "25", "-i", os.path.join(tmp, "r_%03d.png"),
                    "-vf", "loop=1:150:0", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", mp4], check=True)
    print("tamam", len(fs), "kare →", mp4)


if __name__ == "__main__":
    main()
