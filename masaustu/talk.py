"""Konuşma kareleri: bekleme karelerinden (idle_XX) ağzı açılıp kapanan talk_XX kareleri üretir.

Kullanım: python talk.py [görünüm ...]   (görünüm verilmezse hepsi)
Her görünümün kök klasörüne ve emotes/<ifade>/ klasörlerine yazar; groups/ haritaları da güncellenir.
Ağız, ifadenin kendi ağzıyla "konuşan" bir ağız arasında gidip gelir. Nefes karelerinde yüz 1 px yukarıda
olduğu için ağız koordinatı o karelerde kaydırılır (animate.py: (i // 3) % 2 == 1).
"""
import os
import sys

import numpy as np
from PIL import Image

import emotes

HERE = os.path.dirname(os.path.abspath(__file__))
# İfadenin ağzı → konuşurken arada gelen ağız
ALT = {"open": "smile", "smile": "o", "cat": "o", "o": "yawn", "frown": "yawn", "yawn": "o", "wavy": "o"}
# 12 karelik döngüde hangi karelerde ağız değişir (düzenli olmasın, konuşma gibi dursun)
PATTERN = [0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0]


def shifted(face, dy):
    f = dict(face)
    mx, my = face["mouth"]
    x0, y0, x1, y1 = face["mouth_box"]
    f["mouth"] = (mx, my + dy)
    f["mouth_box"] = (x0, y0 + dy, x1, y1 + dy)
    return f


def build(look_dir, look, emote):
    face = emotes.FACE[look]
    kind = emotes.EMOTES[emote][2] if emote else "open"
    alt = ALT[kind]
    for i in range(12):
        name = f"idle_{i:02d}.png"
        src = os.path.join(look_dir, name)
        if not os.path.exists(src):
            return
        img = np.array(Image.open(src).convert("RGBA"))
        groups = np.array(Image.open(os.path.join(look_dir, "groups", name)).convert("RGB"))
        out = img.copy()
        if PATTERN[i]:
            f = shifted(face, -1 if (i // 3) % 2 == 1 else 0)
            emotes.mouth(out, f, alt, emotes.skin_of(out, f))
            groups = groups.copy()
            groups[(out != img).any(axis=2)] = 0  # yeniden çizilen ağız boyanmaz
        tname = f"talk_{i:02d}.png"
        Image.fromarray(out, "RGBA").save(os.path.join(look_dir, tname))
        Image.fromarray(groups, "RGB").save(os.path.join(look_dir, "groups", tname))


def main(looks):
    for look in looks:
        d = os.path.join(HERE, "frames", look)
        build(d, look, None)
        for e in emotes.EMOTES:
            build(os.path.join(d, "emotes", e), look, e)
        print("konuşma kareleri:", look)


if __name__ == "__main__":
    main(sys.argv[1:] or sorted(os.listdir(os.path.join(HERE, "frames"))))
