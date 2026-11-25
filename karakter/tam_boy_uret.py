"""Tam boy pozların (stand, sit) yüzüne göz kırpma ve konuşma ağzı adayları: yeşil sayfanın o çeyreğinde SD inpainting.

Yüz küçük (gözler arası ~25 px ayakta, ~42 px oturuşta): gözler --bolge içinde aranır, kesit büyütmesi --kadraj ile.
Kullanım: python tam_boy_uret.py <çıktı klasörü> [poz ...] [--parca goz_kapali,agiz_o] [--kadraj 1.7] [--adet 6] [--cfg 7]
Çıktı: <poz>_<parça>_0..N.png (çeyrek boyunda, smooth.sd_variant biçimi)
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_parca  # noqa: E402

SHEET = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme", "src", "poses", "yesil", "sheet.png")
# çeyreğin sayfadaki yeri ve çeyrek içinde yüzün arandığı alan
POZ = {"stand": ((384, 0), (100, 0, 290, 190)), "sit": ((384, 512), (60, 8, 300, 248))}
# büstteki SD parçalarıyla aynı istemler
PARCA = {
    "goz_kapali": ("goz", "closed eyes, calm", "open eyes, blue eyes"),
    "agiz_kapali": ("agiz", "closed mouth, small smile", "open mouth, teeth"),
    "agiz_o": ("agiz", "small round open mouth, :o", "teeth, wide open mouth"),
    "agiz_genis": ("agiz", "wide open mouth, laughing, happy", "teeth"),
}


def main():
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a.startswith("--"):
            opts[a[2:]] = next(it)
        else:
            args.append(a)
    out, poses = args[0], args[1:] or list(POZ)
    parts = opts["parca"].split(",") if "parca" in opts else list(PARCA)
    sheet = Image.open(SHEET).convert("RGB")
    pipe = sd_parca.load_pipe()
    for pz in poses:
        (qx, qy), bolge = POZ[pz]
        im = sheet.crop((qx, qy, qx + sheet.width // 2, qy + sheet.height // 2))
        for nm in parts:
            part, prompt, neg = PARCA[nm]
            sd_parca.generate(pipe, im, out, part, f"{pz}_{nm}", prompt, neg, int(opts.get("adet", 6)),
                              half_f=float(opts.get("kadraj", 1.7)), bolge=bolge, cfg=float(opts.get("cfg", 7)))


if __name__ == "__main__":
    main()
