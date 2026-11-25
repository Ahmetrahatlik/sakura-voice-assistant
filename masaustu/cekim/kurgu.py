"""Tam ekran kaydından dikey (9:16) Luna videosu: kadraj Sakura'nın penceresini (balon dahil) yumuşakça izler,
Luna'nın sesi quiet.log'daki "ses" anlarına eklenir.

python kurgu.py <ham.mp4> <kayıt başı HH:MM:SS.fff> <baş sn> <son sn> <çıktı.mp4>
"""
import csv
import datetime as dt
import os
import re
import subprocess
import sys

FF = r"ffmpeg"
SAKURA = os.path.expanduser(r"~\.claude\sakura")
SW, SH = 1920, 1080
W = SH * 9 // 16 // 2 * 2  # 606
FPS = 30

ham, t0s, bas, son, out = os.path.abspath(sys.argv[1]), sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), os.path.abspath(sys.argv[5])
tmp = os.path.splitext(out)[0] + "_tmp"
os.makedirs(tmp, exist_ok=True)

# kadraj: pencerenin sağ kenarı + 20 px şeridin sağında; pencerenin solu (balon) taşarsa sola kayar
def satir(r):
    if len(r) == 6:  # Türkçe ondalık virgülü: "0,04,L,T,R,B"
        r = [r[0] + "." + r[1]] + r[2:]
    return float(r[0]), int(r[1]), int(r[3])


iz = [x for x in (satir(r) for r in csv.reader(open(ham + ".iz.csv"))) if x[2] > x[1]]


SAG = len(sys.argv) > 6 and sys.argv[6] == "sag"  # klasör sahneleri: şerit ekranın sağına sabit (pencere de orada)


def target(t):
    if SAG:
        return SW - W
    i =max(0, min(len(iz) - 1, next((k for k, r in enumerate(iz) if r[0] >= t), len(iz) - 1)))
    _, L, R = iz[i]
    x = R + 20 - W
    if L - 10 < x:
        x = L - 10
    return max(0, min(SW - W, x))


cam = target(bas)
cmds = []
n = int((son - bas) * FPS)
for f in range(n + 1):
    t = bas + f / FPS
    goal = target(t)
    # yumuşak takip: farkın %12'si her karede, en çok 25 px/kare (~750 px/sn)
    step = max(-25, min(25, (goal - cam) * 0.12))
    if abs(goal - cam) < 1:
        step = goal - cam
    cam += step
    cmds.append(f"{f / FPS:.4f} crop x {int(round(cam))};")
open(os.path.join(tmp, "kadraj.txt"), "w").write("\n".join(cmds))
xs = [int(c.split()[-1][:-1]) for c in cmds]
print("kadraj x:", min(xs), "..", max(xs))

# ses: kayıt aralığındaki "ses" satırları
t0 = dt.datetime.strptime(t0s, "%H:%M:%S.%f")
sesler = []
for line in open(os.path.join(SAKURA, "quiet.log"), encoding="utf-8"):
    m = re.search(r" ses (\d\d:\d\d:\d\d\.\d+)\|([^|]*)\|(.*)$", line.rstrip("\n"))
    if not m:
        continue
    at = (dt.datetime.strptime(m.group(1), "%H:%M:%S.%f") - t0).total_seconds()
    # KAYDIR="metin başı=sn;..." : el sallamalı sözde ses selamdan sonra çalıyor, balonla birlikte başlasın
    for kv in filter(None, os.environ.get("KAYDIR", "").split(";")):
        k, v = kv.rsplit("=", 1)
        if m.group(3).startswith(k):
            at += float(v)
    if bas - 0.5 <= at <= son:
        sesler.append((at - bas, m.group(2), m.group(3)))
inputs, filt, mix = [], [], []
for i, (at, em, text) in enumerate(sesler):
    wav = os.path.join(tmp, f"ses_{i}.wav")
    subprocess.run([os.path.join(SAKURA, "Sakura.exe"), "voicetest", wav, text, em], check=True)
    d = max(0, int(at * 1000))
    inputs += ["-i", wav]
    filt.append(f"[{i + 1}:a]adelay={d}|{d},volume=0.8[a{i}]")
    mix.append(f"[a{i}]")
    print(f"ses {at:5.2f} sn  {em}: {text}")
# BULANIK="x:y:g:y:başlangıç sn;..." : kırpılmış şeritte (606×1080) bu kutular bulanıklaşır (ad, profil resmi)
kutular = [list(map(float, b.split(":"))) for b in os.environ.get("BULANIK", "").split(";") if b]
fc = f"[0:v]sendcmd=f=kadraj.txt,crop={W}:{SH}:{xs[0]}:0"
for i, (bx, by, bw, bh, bt) in enumerate(kutular):
    bx, by, bw, bh = int(bx), int(by), int(bw), int(bh)
    fc += f"[k{i}];[k{i}]split[k{i}a][k{i}b];[k{i}b]crop={bw}:{bh}:{bx}:{by},boxblur=8:3[k{i}c];[k{i}a][k{i}c]overlay={bx}:{by}:enable='gte(t,{bt - bas})'"
fc += ",scale=1080:1920:flags=lanczos,setsar=1[v]"
if mix:
    fc += ";" + ";".join(filt) + ";" + "".join(mix) + f"amix=inputs={len(mix)}:normalize=0,apad[a]"
args = [FF, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(bas), "-t", str(son - bas), "-i", ham] + inputs + \
    ["-filter_complex", fc, "-map", "[v]"] + (["-map", "[a]", "-shortest", "-c:a", "aac", "-b:a", "160k"] if mix else []) + \
    ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", out]
subprocess.run(args, check=True, cwd=tmp)  # sendcmd dosyası göreli: Windows yolundaki ':' kaçışıyla uğraşılmaz
print("tamam:", out)
