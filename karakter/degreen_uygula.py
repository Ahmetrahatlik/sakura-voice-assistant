"""Önceden üretilmiş adaylara sonradan degreen uygular (sd_parca'ya eklenmeden önce üretilenler için).
Kullanım: python degreen_uygula.py <aday klasörü> <kaynak.png> [ifade ...]"""
import glob
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_parca  # noqa: E402
from ifade_uret import IFADE  # noqa: E402

out, src = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGB")
eyes, d, mouth = sd_parca.find_parts(np.array(im))
for nm in sys.argv[3:] or list(IFADE):
    parts = [p for p in IFADE[nm][0].split("+") if p in ("agiz", "yanak")]
    gz = [p for p in IFADE[nm][0].split("+") if p.startswith("goz") or p == "kas"]
    if IFADE[nm][3:] and IFADE[nm][3].get("taban", "").startswith("goz"):
        gz.append("goz")
    for f in glob.glob(os.path.join(out, nm + "_[0-9].png")):
        r = Image.open(f).convert("RGB")
        if parts:
            r = sd_parca.degreen(r, sd_parca.part_mask(im.size, parts, eyes, d, mouth))
        if gz:
            r = sd_parca.keep_hair(r, im, sd_parca.part_mask(im.size, gz, eyes, d, mouth))
        r.save(f)
    print(nm, "tamam")
