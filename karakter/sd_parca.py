"""Sakura'nın yüzünde seçilen parçaları (göz, tek göz, kaş, ağız) Stable Diffusion inpainting ile yeniden çizer.

Maskenin dışı piksel piksel aynı kalır (sd_goz.py'nin genel hâli). Kullanım:
  sd/Scripts/python sd_parca.py <kaynak.png> <çıktı klasörü> <parçalar> <ad> "<istem>" ["<olumsuz>"] [adet=6] [strength=1]
    [--bolge x0,y0,x1,y1] [--tohum 2000] [--kadraj 1.7]
parçalar: goz, goz_sol, goz_sag (resimde soldaki/sağdaki göz), kas, yanak (allık), agiz; birden çoğu "+" ile (kas+agiz) tek geçişte
çizilir, ifade tutarlı olsun diye. --bolge: gözlerin aranacağı alan (tam boy panelde yüz küçük; kaynağın tamamı çıktıya
yazılır). --kadraj: SD'ye verilen kare kesitin yarı genişliği, gözler arası mesafe cinsinden.
Çıktı: <ad>_0.png ... (kaynakla aynı boyda) ve <ad>_maske.png
"""
import math
import os
import sys

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter

DENEME = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme")
MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modeller", "mistoon-inpaint")
BASE = "1girl, anime, masterpiece, best quality, clean lineart, "  # "green hair" göz rengine sızıyordu
NEG = "lowres, blurry, bad anatomy, deformed, realistic, 3d, makeup, eyeshadow, lipstick, teeth"


def find_parts(rgb):
    sys.path.insert(0, DENEME)
    import smooth
    from poses import hsv_of, label
    eyes = smooth.blue_eyes(rgb)
    if eyes is None:
        sys.exit("gözler bulunamadı")
    d = float(eyes[1][0] - eyes[0][0])
    ey = (eyes[0][1] + eyes[1][1]) / 2
    # ağız: gözlerin altında, gözler arasında, kırmızı-pembe en büyük bölge
    hh, ss, vv = hsv_of(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))
    red = ((hh >= 335) | (hh <= 20)) & (ss >= 0.45) & (vv >= 0.35)
    yy, xx = np.mgrid[0:rgb.shape[0], 0:rgb.shape[1]]
    # daha aşağısı boyun gölgesi (ağızla birleşip maskeyi yakaya kadar indiriyordu)
    zone = (yy > ey + 0.45 * d) & (yy < ey + 1.05 * d) & (xx > eyes[0][0] - 0.2 * d) & (xx < eyes[1][0] + 0.2 * d)
    lab, n = label(red & zone)
    if not n:
        sys.exit("ağız bulunamadı")
    # en büyük değil, beklenen ağız noktasına (göz ortasının ~0,75d altı, baş eğikliğiyle) yakın ve büyük olan:
    # oturma pozunda boyun gölgesi ağızdan büyük çıkıyordu
    ang = np.arctan2(eyes[1][1] - eyes[0][1], eyes[1][0] - eyes[0][0])
    ex = (eyes[0][0] + eyes[1][0]) / 2 - np.sin(ang) * 0.75 * d
    ey2 = ey + np.cos(ang) * 0.75 * d
    best, score = 0, -1
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        sc = len(ys) * np.exp(-((xs.mean() - ex) ** 2 + (ys.mean() - ey2) ** 2) / (0.3 * d) ** 2)
        if sc > score:
            best, score = i, sc
    ys, xs = np.nonzero(lab == best)
    mouth = ((xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, xs.max() - xs.min(), ys.max() - ys.min())
    return eyes, d, mouth


def ellipse(dr, cx, cy, rx, ry, ang, ry_down=None):
    """Döndürülmüş elips (ang radyan, baş eğikliği); ry_down verilirse alt yarı o yarıçapla."""
    pts = []
    for k in range(48):
        t = 2 * math.pi * k / 48
        x, y = rx * math.cos(t), (ry_down if ry_down and math.sin(t) > 0 else ry) * math.sin(t)
        pts.append((cx + x * math.cos(ang) - y * math.sin(ang), cy + x * math.sin(ang) + y * math.cos(ang)))
    dr.polygon(pts, fill=255)


def part_mask(size, parts, eyes, d, mouth):
    mask = Image.new("L", size, 0)
    dr = ImageDraw.Draw(mask)
    ang = math.atan2(eyes[1][1] - eyes[0][1], eyes[1][0] - eyes[0][0])
    up = (math.sin(ang), -math.cos(ang))  # göz çizgisine dik, yukarı
    for p in parts:
        if p in ("goz", "goz_sol", "goz_sag"):
            sel = eyes if p == "goz" else [eyes[0] if p == "goz_sol" else eyes[1]]
            ry = d * 0.31
            for x, y in sel:
                ellipse(dr, x, y - ry * 0.15, d * 0.44, ry * 0.95, ang)
        elif p == "kas":
            # kaşlar perçemin altında, gözün ~0,4d üstünde; maske göze inmez (açık göz SD ile bozuluyor)
            for x, y in eyes:
                ellipse(dr, x + up[0] * d * 0.40, y + up[1] * d * 0.40, d * 0.40, d * 0.15, ang)
        elif p == "yanak":
            # allık: gözlerin altında, biraz dışa doğru (göz maskesine değmez)
            for k, (x, y) in enumerate(eyes):
                out = -1 if k == 0 else 1
                ellipse(dr, x + out * d * 0.08 - up[0] * d * 0.50, y - up[1] * d * 0.50, d * 0.26, d * 0.12, ang)
        elif p == "yas":
            # gözyaşı izleri: gözün altından çeneye kadar yanak (saç keep_hair ile korunur)
            for k, (x, y) in enumerate(eyes):
                out = -1 if k == 0 else 1
                ellipse(dr, x + out * d * 0.06 - up[0] * d * 0.62, y - up[1] * d * 0.62, d * 0.32, d * 0.62, ang)
        elif p == "agiz":
            mx, my, mw, mh = mouth
            rx, ry = max(mw * 0.9, d * 0.28), max(mh * 1.1, d * 0.18)
            ellipse(dr, mx, my, rx, ry, ang, ry_down=ry * 1.5)  # aşağı doğru açılabilsin
        else:
            sys.exit("bilinmeyen parça: " + p)
    return mask


def degreen(im, mask):
    """Saç olmayan bölgede (ağız, allık) zeytin/haki tonlu çizgileri kahverengiye çeker: SD ağız çizgisini yeşil saçtan
    renk alarak çiziyor, saç boyama (smooth.green_tint, 40-65° zeytin) bunu saç sanıp siyah leke yapıyordu.
    Belirgin yeşil (gerçek saç tutamı, G diğerlerinden 20+ fazla) dokunulmaz."""
    a = np.array(im).astype(float)
    m = np.array(mask.filter(ImageFilter.MaxFilter(5))).astype(float) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lo = np.minimum(r, b)
    cap = lo + 0.5 * (np.maximum(r, b) - lo)  # ton ~30° (ten çizgisi) üstüne çıkmasın
    fix = (g > cap) & (g - np.maximum(r, b) < 20) & (m > 0)
    a[..., 1] = np.where(fix, g * (1 - m) + cap * m, g)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def keep_hair(res, im, mask):
    """Göz/kaş bölgesinde SD'nin soluk (zeytin/gri-yeşil) çizdiği saç tutamı, kaynakta orada saç varsa kaynağın
    pikseliyle değişir; kaynakta saç yoksa degreen. Saç boyama soluk tutamı siyah leke yapıyordu. Koyu çizgiler
    (kaş, kirpik) ve belirgin yeşil saç olduğu gibi kalır."""
    a, o = np.array(res).astype(float), np.array(im).astype(float)
    dom_o = (o[..., 1] - np.maximum(o[..., 0], o[..., 2])) / np.maximum(o[..., 1], 1) * (o[..., 1] > 70)
    dom_r = (a[..., 1] - np.maximum(a[..., 0], a[..., 2])) / np.maximum(a[..., 1], 1)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    olive = (g > np.minimum(r, b) + 0.5 * (np.maximum(r, b) - np.minimum(r, b))) & (dom_r < 0.35) & (g > 50)
    hair_o = np.array(Image.fromarray((np.clip(dom_o / 0.3, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))) / 255
    m = np.array(mask.filter(ImageFilter.MaxFilter(5))).astype(float) / 255
    w = (m * hair_o * olive)[..., None]
    out = Image.fromarray(np.clip(a * (1 - w) + o * w, 0, 255).astype(np.uint8))
    return degreen(out, mask)


def load_pipe():
    from diffusers import StableDiffusionInpaintPipeline, DPMSolverMultistepScheduler
    pipe = StableDiffusionInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, safety_checker=None, requires_safety_checker=False)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
    pipe = pipe.to("cuda")
    pipe.enable_attention_slicing()
    return pipe


def generate(pipe, im, out, part, name, prompt, neg="", n=6, strength=1.0, seed=2000, half_f=1.7, bolge=None, cfg=7.0, ref=None):
    """im: kaynak (PIL RGB). bolge: gözlerin aranacağı (x0, y0, x1, y1); çıktılar kaynakla aynı boyda.
    ref: gözlerin ve ağzın arandığı asıl çizim (im ondan türetilmişse, ör. gözü önceden kapatılmış; kapalı gözde iris yok)."""
    os.makedirs(out, exist_ok=True)
    ref = ref or im
    if bolge:
        ox, oy, x1, y1 = bolge
        eyes, d, mouth = find_parts(np.array(ref.crop((ox, oy, x1, y1))))
        eyes = [(x + ox, y + oy) for x, y in eyes]
        mouth = (mouth[0] + ox, mouth[1] + oy) + mouth[2:]
    else:
        eyes, d, mouth = find_parts(np.array(ref))
    mask = part_mask(im.size, part.split("+"), eyes, d, mouth)
    mask.save(os.path.join(out, name + "_maske.png"))
    cx, cy = (eyes[0][0] + eyes[1][0]) / 2, (eyes[0][1] + eyes[1][1]) / 2 + d * 0.3
    half = int(d * half_f)
    box = (int(cx - half), int(cy - half), int(cx + half), int(cy + half))
    # kesit kaynağın dışına taşarsa beyazla doldurulur (çıktıya yalnız maske içi yazılır)
    pad = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), (255, 255, 255))
    pad.paste(im, (-box[0], -box[1]))
    crop = pad.resize((512, 512), Image.LANCZOS)
    mpad = Image.new("L", pad.size, 0)
    mpad.paste(mask, (-box[0], -box[1]))
    mcrop = mpad.resize((512, 512), Image.LANCZOS)
    soft = mask.filter(ImageFilter.GaussianBlur(max(d * 0.05, 0.8)))
    nohair = [p for p in part.split("+") if p in ("agiz", "yanak")]
    nh = part_mask(im.size, nohair, eyes, d, mouth) if nohair else None
    gz = [p for p in part.split("+") if p.startswith("goz") or p == "kas"]
    em = part_mask(im.size, gz, eyes, d, mouth) if gz else None
    for i in range(n):
        g = torch.Generator("cuda").manual_seed(seed + i)
        r = pipe(prompt=BASE + prompt, negative_prompt=NEG + (", " + neg if neg else ""), image=crop, mask_image=mcrop,
                 num_inference_steps=30, guidance_scale=cfg, strength=strength, generator=g, width=512, height=512).images[0]
        layer = im.copy()
        layer.paste(r.resize(pad.size, Image.LANCZOS), box[:2])
        res = Image.composite(layer, im, soft)
        if nh is not None:
            res = degreen(res, nh)
        if em is not None:
            res = keep_hair(res, ref, em)
        res.save(os.path.join(out, "%s_%d.png" % (name, i)))
    print(name, n, "aday tamam")


def main():
    args, opts = [], {}
    it = iter(sys.argv[1:])
    for a in it:
        if a.startswith("--"):
            opts[a[2:]] = next(it)
        else:
            args.append(a)
    src, out, part, name, prompt = args[:5]
    neg = args[5] if len(args) > 5 and args[5] else ""
    n = int(args[6]) if len(args) > 6 else 6
    strength = float(args[7]) if len(args) > 7 else 1.0  # <1: mevcut çizimden başlar (renk/tarz korunur)
    bolge = tuple(int(v) for v in opts["bolge"].split(",")) if "bolge" in opts else None
    generate(load_pipe(), Image.open(src).convert("RGB"), out, part, name, prompt, neg, n, strength,
             int(opts.get("tohum", 2000)), float(opts.get("kadraj", 1.7)), bolge)


if __name__ == "__main__":
    main()
