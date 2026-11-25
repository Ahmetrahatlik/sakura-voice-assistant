"""Sakura'nın ifadelerini tek yüzden (yeşil sayfanın büst paneli) SD inpainting ile üretir: her ifade için adaylar.

Açık gözlü ifadelerde göz yeniden çizilmez (SD göz tarzını bozuyor); ifade kaş, ağız ve allıkla verilir.
Kullanım: python ifade_uret.py <çıktı klasörü> [ifade ...] [--adet 6]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sd_parca  # noqa: E402

SHEET = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme", "src", "poses", "yesil", "sheet.png")

SD = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme", "src", "poses", "sd")

# ad: (parçalar, istem, olumsuz istem[, seçenekler]); seçenek "taban": onaylı SD parçası (goz_kapali, agiz_o) ya da
# goz_kirp_taban (yalnız soldaki göz kapalı) üstüne çizilir, "cfg": istem gücü.
IFADE = {
    "utangac": ("kas+yanak+agiz", "embarrassed, shy, blushing, very red cheeks, deep blush, nose blush, worried eyebrows, "
                "small wavy closed mouth, nervous smile", "open mouth, angry, pale", {"cfg": 9}),
    "uzgun": ("kas+agiz", "sad, worried eyebrows, upturned eyebrows, small frown, closed mouth, downturned mouth",
              "smile, open mouth, happy, angry"),
    "uykulu": ("goz+agiz", "sleepy, closed eyes, drowsy, yawning, small open mouth", "smile, open eyes, blue eyes"),
    "sinirli": ("kas+agiz", "angry, furrowed eyebrows, v-shaped eyebrows, pouting, closed mouth, frown", "smile, open mouth"),
    "nese": ("goz+agiz", "laughing, closed eyes, ^_^, happy, wide open mouth, big smile", "open eyes, blue eyes, teeth"),
    # ağız SD'de hep gülüşe dönüyordu: onaylı "o" ağzın (agiz_o) üstüne yalnız kaş
    "saskin": ("kas", "surprised, shocked, raised eyebrows, high arched eyebrows", "angry, frown", {"taban": "agiz_o", "cfg": 9}),
    "gurur": ("kas+agiz", "smug, proud, confident smirk, closed mouth smile, raised eyebrows",
              "open mouth, teeth, sad", {"taban": "goz_kapali"}),
    "sevgi": ("yanak+agiz", "loving, affectionate, gentle smile, closed mouth smile, heavy blush, red cheeks",
              "open mouth, teeth, pale", {"taban": "goz_kapali", "cfg": 8}),
    "mutlu": ("kas+agiz", "happy, relaxed eyebrows, gentle smile, closed mouth smile", "open mouth, angry, sad"),
    "goz_kirp": ("agiz", "winking, playful smile, closed mouth smile, :)", "open mouth, teeth", {"taban": "goz_kirp_taban"}),
    "dusunce": ("kas+agiz", "thinking, pondering, one eyebrow raised, small pursed mouth, closed mouth, hmm",
                "smile, open mouth"),
}


def taban(im, ad):
    """Üstüne çizilecek başlangıç: onaylı bir SD parçası (src/poses/sd/<ad>.png, ör. goz_kapali, agiz_o) ya da
    goz_kirp_taban (yalnız soldaki gözü kapalı)."""
    if ad != "goz_kirp_taban":
        return Image.open(os.path.join(SD, ad + ".png")).convert("RGB")
    shut = Image.open(os.path.join(SD, "goz_kapali.png")).convert("RGB")
    a, b = np.array(im).astype(int), np.array(shut).astype(int)
    eyes, d, _ = sd_parca.find_parts(np.array(im))
    m = (np.abs(a - b).max(-1) > 6).astype(np.uint8) * 255
    m[:, int((eyes[0][0] + eyes[1][0]) / 2):] = 0  # yalnız soldaki göz
    m = np.array(Image.fromarray(m).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1))) / 255.0
    return Image.fromarray((a * (1 - m[..., None]) + b * m[..., None]).round().astype(np.uint8))


def main():
    args, n = [], 6
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--adet":
            n = int(next(it))
        else:
            args.append(a)
    out, names = args[0], args[1:] or list(IFADE)
    im = Image.open(SHEET).convert("RGB").crop((0, 0, 384, 512))
    pipe = sd_parca.load_pipe()
    for nm in names:
        part, prompt, neg = IFADE[nm][:3]
        opt = IFADE[nm][3] if len(IFADE[nm]) > 3 else {}
        src = taban(im, opt["taban"]) if "taban" in opt else im
        sd_parca.generate(pipe, src, out, part, nm, prompt, neg, n, cfg=opt.get("cfg", 7.0), ref=im)


if __name__ == "__main__":
    main()
