"""Sakura'nın büst çiziminde yalnız gözleri Stable Diffusion inpainting ile yeniden çizer (ör. kapalı göz).

Yüz çevresi kesilip 512 px'e büyütülür, maskeli bölge çizilir, eski boyuta küçültülüp yumuşak kenarla yerine konur;
maskenin dışı piksel piksel aynı kalır. Kullanım:
  sd/Scripts/python sd_goz.py <kaynak.png> <çıktı klasörü> [adet=6] ["istem"]
"""
import os
import sys

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter

DENEME = os.path.join(os.path.expanduser("~"), ".claude", "sakura-deneme")
MODEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modeller", "mistoon-inpaint")
PROMPT = "1girl, anime, closed eyes, eyelashes, smile, blush, green hair, masterpiece, best quality, clean lineart"
NEG = "open eyes, blue eyes, pupils, iris, lowres, blurry, bad anatomy, deformed, extra eyes, realistic, 3d, makeup, eyeshadow"


def eyes(rgb):
    sys.path.insert(0, DENEME)
    import smooth
    return smooth.blue_eyes(rgb)


def main():
    src, out = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    prompt = sys.argv[4] if len(sys.argv) > 4 else PROMPT
    os.makedirs(out, exist_ok=True)
    im = Image.open(src).convert("RGB")
    pts = eyes(np.array(im))
    if pts is None:
        sys.exit("gözler bulunamadı")
    d = float(pts[1][0] - pts[0][0])
    mask = Image.new("L", im.size, 0)
    dr = ImageDraw.Draw(mask)
    for x, y in pts:
        rx, ry = d * 0.44, d * 0.31
        dr.ellipse((x - rx, y - ry * 1.1, x + rx, y + ry * 0.8), fill=255)
    # yüz çevresi kare kesit (gözlerin ortası, gözler arası mesafenin ~3,4 katı)
    cx, cy = (pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2 + d * 0.3
    half = int(d * 1.7)
    box = (int(cx - half), int(cy - half), int(cx + half), int(cy + half))
    crop = im.crop(box).resize((512, 512), Image.LANCZOS)
    mcrop = mask.crop(box).resize((512, 512), Image.LANCZOS)

    from diffusers import StableDiffusionInpaintPipeline, DPMSolverMultistepScheduler
    pipe = StableDiffusionInpaintPipeline.from_pretrained(MODEL, torch_dtype=torch.float16, safety_checker=None, requires_safety_checker=False)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config, use_karras_sigmas=True)
    pipe = pipe.to("cuda")
    pipe.enable_attention_slicing()

    soft = mask.filter(ImageFilter.GaussianBlur(d * 0.06))  # yapıştırma kenarı
    for i in range(n):
        g = torch.Generator("cuda").manual_seed(1000 + i)
        r = pipe(prompt=prompt, negative_prompt=NEG, image=crop, mask_image=mcrop, num_inference_steps=30,
                 guidance_scale=7.0, strength=1.0, generator=g, width=512, height=512).images[0]
        back = r.resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
        layer = im.copy()
        layer.paste(back, box[:2])
        res = Image.composite(layer, im, soft)
        res.save(os.path.join(out, "kapali_%d.png" % i))
        print("kare", i, "tamam")


if __name__ == "__main__":
    main()
