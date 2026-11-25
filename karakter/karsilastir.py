"""SD adaylarını kullanıcının saç rengiyle boyayıp yüz kesitini büyüterek tek karşılaştırma görseline dizer.

Kullanım: python karsilastir.py <çıktı.png> <kesit x0,y0,x1,y1> <kare yüksekliği> <başlık=dosya>...
Her satır bir ifade: "baslik=klasor/ad" verilirse klasor/ad_0..5.png dizilir; ilk sütun kaynak (--kaynak).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from onizle_renk import recolor  # noqa: E402

COL = "#2e2a3a"


def tile(path, box, h):
    a = np.array(Image.open(path).convert("RGBA").crop(box))
    im = Image.fromarray(recolor(a, COL))
    return im.resize((round(im.width * h / im.height), h), Image.LANCZOS)


def main():
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a.startswith("--"):
            opts[a[2:]] = next(it)
        else:
            args.append(a)
    out, box, h = args[0], tuple(int(v) for v in args[1].split(",")), int(args[2])
    rows = [r.split("=", 1) for r in args[3:]]
    n = int(opts.get("adet", 6))
    font = ImageFont.truetype("arial.ttf", 22)
    ref = tile(opts["kaynak"], box, h) if "kaynak" in opts else None
    w = round((box[2] - box[0]) * h / (box[3] - box[1]))
    cols = n + (1 if ref else 0)
    W = Image.new("RGB", (cols * (w + 6), len(rows) * (h + 34)), "white")
    dr = ImageDraw.Draw(W)
    for r, (title, stem) in enumerate(rows):
        y = r * (h + 34)
        x = 0
        if ref:
            W.paste(ref, (0, y + 30))
            dr.text((4, y + 4), "kaynak", fill=(90, 90, 90), font=font)
            x = w + 6
        for i in range(n):
            f = "%s_%d.png" % (stem, i)
            if os.path.exists(f):
                W.paste(tile(f, box, h), (x + i * (w + 6), y + 30))
            dr.text((x + i * (w + 6) + 4, y + 4), "%s %d" % (title, i + 1), fill=(200, 0, 60), font=font)
    W.save(out)
    print(out, W.size)


if __name__ == "__main__":
    main()
