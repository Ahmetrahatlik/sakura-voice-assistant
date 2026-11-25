"""Sakura.exe export ile kullanıcının renklerinde kareleri alıp büyütülmüş tek sayfaya dizer (doğrulama için).

Kullanım: python export_sayfa.py <sakura klasörü> <çıktı.png> <satır>...
satır: "başlık|prefix|emote|kare,kare,..." (emote boş olabilir), ör. "mutlu|idle_|mutlu|0,20"
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

COLORS = ["hair=#2e2a3a", "eyes=#2b3a7a", "outfit=#2e2a3a", "ribbon=#2e2a3a"]


def main():
    home, out, rows = sys.argv[1], sys.argv[2], sys.argv[3:]
    exe = os.path.join(home, "Sakura.exe")
    tmp = tempfile.mkdtemp()
    font = ImageFont.truetype("arial.ttf", 20)
    grid = []
    for r in rows:
        title, prefix, emote, frames = r.split("|")
        cells = []
        for f in frames.split(","):
            p = os.path.join(tmp, "%s_%s_%s.png" % (prefix, emote, f))
            args = [exe, "export", p, "prefix=" + prefix, "frame=" + f] + COLORS + (["emote=" + emote] if emote else [])
            subprocess.run(args, check=True, cwd=home)
            cells.append(("%s %s" % (title, f), Image.open(p).convert("RGBA")))
        grid.append(cells)
    z = 2
    cw = max(im.width for row in grid for _, im in row) * z
    ch = max(im.height for row in grid for _, im in row) * z
    cols = max(len(row) for row in grid)
    W = Image.new("RGB", (cols * (cw + 8), len(grid) * (ch + 30)), (236, 238, 244))
    dr = ImageDraw.Draw(W)
    for y, row in enumerate(grid):
        for x, (t, im) in enumerate(row):
            big = im.resize((im.width * z, im.height * z), Image.LANCZOS)
            ox, oy = x * (cw + 8), y * (ch + 30) + 28
            W.paste(big, (ox, oy), big)
            dr.text((ox + 4, oy - 26), t, fill=(200, 0, 60), font=font)
    W.save(out)
    print(out, W.size)


if __name__ == "__main__":
    main()
