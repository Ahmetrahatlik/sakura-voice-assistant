"""Poz sayfasını (ChatGPT'den 2×2 görsel) dört ayrı pixel sprite'a çevirir.

Kullanım: python poses.py src/poses/sheet.webp
Paneller: sol üst = bust (kollar aşağıda büst), sağ üst = stand (tam boy ayakta), sol alt = walk (yürüyüş, sağa bakar),
sağ alt = sit (yerde oturuş). Çıktı: out/pose_<ad>.png. Tam boy pozlar aynı ölçekte küçültülür (ayakta boy STAND_H).
"""
import os
import sys

import numpy as np
from PIL import Image

import pixelize

HERE = os.path.dirname(os.path.abspath(__file__))
NAMES = [["bust", "stand"], ["walk", "sit"]]
# piksel inceliği: 2 = blok 2 (videolar, kullanıcı seçti), 1 = blok 4 (masaüstü uygulaması, "luna" görünümü).
# POSE_K=1 python poses.py → frames/yeni (masaüstündeki Sakura'nın yeni çizimli görünümü). Ölçüler K ile, alan eşikleri K² ile ölçeklenir.
K = int(os.environ.get("POSE_K", "2"))
TAG = "" if K == 2 else "_k%d" % K  # ara dosya adları K'ya göre ayrı
_sh = os.environ.get("POSE_SHARP", "")
SHARP = tuple(float(v) for v in _sh.split(",")) if _sh else None  # (yarıçap, yüzde) deneme için
SHINE = float(os.environ.get("POSE_SHINE", "0.8"))
# Masaüstü büstü yüze yakın kadraj: eski Sakura'da yüz 192×256 çerçevede ~1,6 kat büyüktü, o yüzden daha net görünüyordu (1,4: omuz ve papyon da kalsın)
BUST_ZOOM = 1.4 if K == 1 else 1.0
BUST = (192 * K, 256 * K)   # eski büst çerçevesi (video tuvalinde aynı boyda durur)
STAND_H = 320 * K   # tam boy ayakta sprite yüksekliği (piksel)
BLOCK = 4 // K
MARGIN = 24


def panels(sheet):
    """Izgara çizgilerinden (açık gri, tek renk sütun/satır) bölüp her paneli içerik kutusuna kırpar."""
    a = np.array(sheet).astype(int)
    h, w, _ = a.shape
    cx, cy = w // 2, h // 2
    out = {}
    for r, (y0, y1) in enumerate(((0, cy), (cy, h))):
        for c, (x0, x1) in enumerate(((0, cx), (cx, w))):
            p = a[y0:y1, x0:x1]
            ink = (p.min(axis=2) < 225)
            # panelin kenarındaki ızgara çizgisini yok say
            ink[:6] = ink[-6:] = False
            ink[:, :6] = ink[:, -6:] = False
            ys, xs = np.nonzero(ink)
            box = (x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1)
            out[NAMES[r][c]] = sheet.crop(box)
    return out


def on_white(img, scale):
    w, h = round(img.width * scale), round(img.height * scale)
    big = img.resize((w, h), Image.LANCZOS)
    if SHARP:
        # küçültmeden önce keskinleştirme: konturlar ve kirpikler blokta en sık renk seçilirken kaybolmasın
        from PIL import ImageFilter
        big = big.filter(ImageFilter.UnsharpMask(radius=SHARP[0], percent=int(SHARP[1]), threshold=2))
    canvas = Image.new("RGB", (w + MARGIN * 2, h + MARGIN * 2), (255, 255, 255))
    canvas.paste(big, (MARGIN, MARGIN))
    return canvas


def main(path):
    sheet = Image.open(path).convert("RGB")
    ps = panels(sheet)
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    full = STAND_H * BLOCK / ps["stand"].height
    for name, img in ps.items():
        if name == "bust":
            # Büst: genişliği eski büste oturt; alt kenar kırpılır (gövde kesik).
            scale = BUST[0] * BLOCK / img.width * BUST_ZOOM
        else:
            scale = full
        pixelize_image(name, img, scale)
    if os.path.exists(WALK_SHEET):
        # yürüme kareleri eski yürüyüş paneliyle aynı boya ölçeklenir
        frames = walk_sheet_frames()
        h = sorted(f.height for f in frames)[len(frames) // 2]
        for i, f in enumerate(frames):
            pixelize_image(f"wk{i}", f, full * ps["walk"].height / h)


def pixelize_image(name, img, scale):
    """Tek görseli pixel sprite'a çevirir: out/pose<TAG>_<ad>_raw.png (+ gözler için _smooth.png)."""
    tmp = os.path.join(HERE, "out", f"_pose{TAG}_{name}.png")
    on_white(img, scale).save(tmp)
    dst = os.path.join(HERE, "out", f"pose{TAG}_{name}_raw.png")  # ham çıktı; save_frames her seferinde bundan başlar
    # beyaz zemin: açık ten arka plan sanılmasın; octree: gözlerin küçük mavi alanı palette kalsın
    a = pixelize.pixelize(tmp, dst, BLOCK, 96, clean_tol=12, method=Image.Quantize.FASTOCTREE, holes=False)
    # Aynı ızgarada yumuşak küçültme: gözler buradan alınır (blokta en sık renk küçük göz detayını mozaiğe çeviriyor,
    # parlamayı kaybediyordu)
    big = Image.open(tmp).convert("RGB")
    smooth = np.array(big.resize((a.shape[1], a.shape[0]), Image.LANCZOS, box=(0, 0, a.shape[1] * BLOCK, a.shape[0] * BLOCK)))
    # Kenar payını at, sprite'ı içeriğe kırp (büst: sabit 192×256, üstten hizalı).
    ys, xs = np.nonzero(a[..., 3])
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    a = a[y0:y1, x0:x1]
    smooth = smooth[y0:y1, x0:x1]
    if name == "bust":
        out = np.zeros((BUST[1], BUST[0], 4), np.uint8)
        sm = np.zeros((BUST[1], BUST[0], 3), np.uint8)
        hh, ww = min(a.shape[0], BUST[1] - 4 * K), min(a.shape[1], BUST[0])
        ox = (BUST[0] - ww) // 2
        sx = (a.shape[1] - ww) // 2  # geniş kadrajda ortadan kes (yüz ortada)
        out[4 * K:4 * K + hh, ox:ox + ww] = a[:hh, sx:sx + ww]
        sm[4 * K:4 * K + hh, ox:ox + ww] = smooth[:hh, sx:sx + ww]
        a, smooth = out, sm
    Image.fromarray(a, "RGBA").save(dst)
    Image.fromarray(smooth, "RGB").save(os.path.join(HERE, "out", f"pose{TAG}_{name}_smooth.png"))
    os.remove(tmp)
    print(name, a.shape[1], "x", a.shape[0])


# ChatGPT'den 8 karelik yürüme döngüsü (2 satır × 4, sağa bakar). walk4.webp: ilk deneme, bacaklar hiç
# birbirinin yanından geçmiyordu (hep aynı açık poz), kayar gibi görünüyordu.
WALK_SHEET = os.path.join(HERE, "src", "poses", "walk8.webp")


def _runs(mask, min_len):
    runs, start = [], None
    for i, c in enumerate(mask):
        if c and start is None:
            start = i
        if not c and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(mask)))
    return [r for r in runs if r[1] - r[0] > min_len]


def walk_sheet_frames():
    """Yürüme sayfasını beyaz boşluklardan satırlara, sonra her satırı figürlere böler (soldan sağa, yukarıdan aşağı)."""
    im = Image.open(WALK_SHEET).convert("RGB")
    ink = np.array(im).min(axis=2) < 230
    out = []
    for y0, y1 in _runs(ink.any(axis=1), 40):
        row = ink[y0:y1]
        for x0, x1 in _runs(row.any(axis=0), 40):
            ys = np.nonzero(row[:, x0:x1].any(axis=1))[0]
            out.append(im.crop((x0, y0 + ys.min(), x1, y0 + ys.max() + 1)))
    return out


def hsv_of(a):
    rgb = a[..., :3].astype(float) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(mx)
    dd = np.maximum(d, 1e-9)
    h = np.where(mx == r, ((g - b) / dd) % 6, h)
    h = np.where(mx == g, (b - r) / dd + 2, h)
    h = np.where(mx == b, (r - g) / dd + 4, h)
    return np.where(d > 0, h * 60, 0), s, mx


def label(mask):
    """Bağlı bölgeler (4 komşuluk): (etiket dizisi, bölge sayısı)."""
    lab = np.zeros(mask.shape, np.int32)
    n = 0
    hh, ww = mask.shape
    for y, x in zip(*np.nonzero(mask)):
        if lab[y, x]:
            continue
        n += 1
        lab[y, x] = n
        stack = [(y, x)]
        while stack:
            cy, cx = stack.pop()
            for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= ny < hh and 0 <= nx < ww and mask[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n
                    stack.append((ny, nx))
    return lab, n


def box_count(mask, r):
    """Her pikselin (2r+1)² çevresindeki True sayısı."""
    p = np.pad(mask.astype(int), r)
    c = p.cumsum(0).cumsum(1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]


def neighbors4(mask):
    m = mask.astype(int)
    n = np.zeros_like(m)
    n[1:] += m[:-1]
    n[:-1] += m[1:]
    n[:, 1:] += m[:, :-1]
    n[:, :-1] += m[:, 1:]
    return n


def face_box(a):
    """Yüz: üst yarıdaki en büyük ten bölgesi. (alın, çene, sol x, sağ x)"""
    h, s, v = hsv_of(a)
    skin = (a[..., 3] > 0) & (h >= 5) & (h <= 45) & (s >= 0.1) & (s <= 0.45) & (v > 0.7)
    lab, n = label(skin)
    best, size = 0, 0
    for i in range(1, n + 1):
        ys = np.nonzero(lab == i)[0]
        if ys.min() < a.shape[0] * 0.45 and len(ys) > size:
            best, size = i, len(ys)
    fy, fx = np.nonzero(lab == best)
    return fy.min(), fy.max(), fx.min(), fx.max()


def body_skin_zone(a, chin):
    """Çenenin altında tenin hemen yakını (eller, uyluklar): oradaki pembe gölgeler tendir, saça katılmaz.
    (Eller küçük olduğu için pembe gölgeleri "tenle çevrili değil" sayılıp saç rengine boyanıyordu.)"""
    h, s, v = hsv_of(a)
    skin = (a[..., 3] > 0) & (h >= 5) & (h <= 45) & (s >= 0.1) & (s <= 0.45) & (v > 0.7)
    zone = box_count(skin, 2 * K) > 0
    zone[:chin + 10 * K] = False
    return zone, skin


def groups(a):
    """Renk grupları: 1 saç, 2 göz, 3 kıyafet (hırka, etek, çorap, ayakkabı, papyon), 4 kurdele (baştaki fiyonklar).

    Saç yalnız renkle seçilmez (gölgeli ten de pembemsi): başa bağlı pembe bölgeler saçtır.
    """
    h, s, v = hsv_of(a)
    vis = a[..., 3] > 0
    outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
    skin = vis & (h >= 5) & (h <= 45) & (s >= 0.1) & (s <= 0.45) & (v > 0.7)
    lab, n = label(skin)
    H = a.shape[0]
    # yüz: üst yarıdaki en büyük ten bölgesi; çenesi başın alt sınırı
    best, size = 0, 0
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if ys.min() < H * 0.45 and len(ys) > size:
            best, size = i, len(ys)
    fy, fx = np.nonzero(lab == best)
    chin, fx0, fx1, ftop = fy.max(), fx.min(), fx.max(), fy.min()
    g = np.zeros(a.shape[:2], np.uint8)
    skin_n = box_count(skin, 2 * K) / (K * K)  # 5×5 (K=1) pencereye göre normalize
    # Saç: tenle çevrili olmayan pembe bölgeler (bacak gölgesi gibi pembemsi ten, çevresi ten olduğu için dışarıda kalır).
    # Yüzün içindeki küçük pembe parçalar (ağız, dil, allık) saç değildir. Kontur yüzünden baştan kopuk teller de saçtır.
    pink = vis & ~outline & ((h >= 330) | (h <= 10)) & (s >= 0.2) & (v >= 0.3) & (skin_n < 9)
    plab, pn = label(pink)
    bzone, _ = body_skin_zone(a, chin)
    for i in range(1, pn + 1):
        m = plab == i
        # gövdede tene değen pembe parça elin/uyluğun gölgesidir
        ring = (neighbors4(m) > 0) & ~m & vis & ~outline
        if (m & bzone).any() and ring.sum() and (ring & skin).sum() >= 0.2 * ring.sum():
            continue
        ys, xs = np.nonzero(m)
        in_face = ys.min() >= ftop and ys.max() <= chin and xs.min() >= fx0 and xs.max() <= fx1
        # çene altı/boyun gölgesi: yüzün alt yarısından ya da çeneden aşağıda başlar, yüz hizasında durur
        # (saç ise tepeden iner, yüzün üst yarısından yukarıda başlar)
        neck = ys.min() > (ftop + chin) // 2 and fx0 <= xs.mean() <= fx1 and ys.max() <= chin + 60 * K
        if len(ys) >= 4 * K * K and not (in_face and len(ys) < 150 * K * K) and not neck:
            g[m] = 1
    # saçın ışıltı ve gölge pikselleri: saça bitişik pembe/mor tonlu, tenle çevrili olmayanlar
    # ince pikselde gömleğin gri-pembe gölgeleri (s≈0.06-0.11) de saça yayılıyordu
    soft = vis & ~outline & ((h >= 290) | (h <= 20)) & (s >= (0.06 if K == 1 else 0.12)) & (skin_n < 9) & ~skin
    for k in range(8):
        n1 = neighbors4(g == 1)
        # ilk turlar iki saç komşusu ister; sonra kenardaki (kontura/boşluğa değen) tek komşulu pembeler de saça katılır
        add = soft & (g == 0) & ~bzone & (n1 >= (2 if k < 4 else 1))
        if not add.any():
            break
        g[add] = 1
    # saç tellerinin kenarındaki somon saçak ten rengine yakın: saçla çevrili ince/uzun "ten" parçaları saçtır
    # (kulak gibi toplu parçalar ve yüz, el, bacak gibi büyük bölgeler ten kalır)
    slab, sn = label(skin & (g == 0))
    for i in range(1, sn + 1):
        m = slab == i
        ys, xs = np.nonzero(m)
        if len(ys) > 120 * K * K:
            continue
        bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        thin = min(bh, bw) <= 4 * K or len(ys) / (bh * bw) < 0.35
        ring = (neighbors4(m) > 0) & ~m & vis & ~outline
        if thin and ring.sum() and (ring & (g == 1)).sum() >= 0.5 * ring.sum():
            g[m] = 1
    # gözler: başta, mavi
    eye = vis & (h >= 185) & (h <= 270) & (s >= 0.25) & (v >= 0.25)
    eye[chin + 1:] = False
    eye[:ftop] = False
    eye[:, :max(fx0 - 4 * K, 0)] = False
    eye[:, fx1 + 4 * K:] = False
    g[eye] = 2
    dark = vis & ~outline & (v < 0.45) & (s < 0.5) & (g == 0)
    # baştaki fiyonklar: çenenin üstünde, saçla çevrili koyu adacıklar (çevresinin en az %40'ı saç; çene yanındaki
    # yaka gölgesi de koyu ve çenenin üstünde ama çevresi ten/yaka, fiyonk sayılınca kurdele rengini alıyordu)
    dlab, dn = label(dark)
    for i in range(1, dn + 1):
        m = dlab == i
        ys, xs = np.nonzero(m)
        ring = (neighbors4(m) > 0) & ~m & vis & ~outline
        high = ys.min() < ftop + (chin - ftop) // 3  # fiyonk başın üstünde başlar; yaka gölgesi çene hizasında
        if ys.max() <= chin and high and len(ys) >= 15 * K * K and ring.sum() and (ring & (g == 1)).sum() >= 0.4 * ring.sum():
            g[m] = 4
    # fiyonkun içindeki çok koyu/doygun pikseller ve iç çizgiler de fiyonktur (yoksa renk değişince siyah benek kalır);
    # silüet konturu (boşluğa değen) hariç
    edge_out = outline & (neighbors4(~vis) > 0)
    for _ in range(3 * K):
        add = vis & (g == 0) & ~edge_out & (v < 0.35) & (neighbors4(g == 4) >= 2)
        if not add.any():
            break
        g[add] = 4
    # papyon kurdele grubuna alınmaz: algılama pozdan poza tutarsızdı (yarım papyon iki renk kalıyordu); kıyafetle boyanır
    # kıyafet: çenenin altındaki geri kalan koyu pikseller
    rest = dark & (g == 0)
    rest[:chin + 1] = False
    g[rest] = 3
    return g


def despeckle(a, protect, passes=2):
    """Tek başına kalan pikselleri (8 komşusunun hiçbiri benzer renkte değil) en sık komşu renge çeker.

    Resim küçültülürken saç ve hırkada tuz-biber gibi gürültü kalıyor; video 4 kat büyütünce göze batıyor.
    protect: dokunulmayacak yerler (göz parıltısı, ağız, ten üstündeki çizgiler).
    """
    H, W = a.shape[:2]
    outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
    for _ in range(passes):
        src = a.copy()
        vis = src[..., 3] > 0
        rgb = src[..., :3].astype(int)
        for y, x in zip(*np.nonzero(vis & ~outline & ~protect)):
            if y == 0 or x == 0 or y == H - 1 or x == W - 1:
                continue
            similar, votes = 0, {}
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if not vis[ny, nx] or outline[ny, nx]:
                        continue
                    if np.abs(rgb[ny, nx] - rgb[y, x]).max() < 36:
                        similar += 1
                    k = tuple(src[ny, nx])
                    votes[k] = votes.get(k, 0) + 1
            if similar == 0 and votes:
                a[y, x] = max(votes, key=votes.get)
    return a


def edge_fringe(a, passes=3):
    """Silüet kenarındaki açık renkli kırıntılar (beyaz zeminden kalan karışım): konturun K piksel içindeki, koyu
    komşulu gri-beyaz pikseller en sık koyu komşu renge çekilir (çorap ve saç kenarındaki beyaz noktalar/çizgi).
    Ten ve gömlek etkilenmez: tenin doygunluğu yüksek, gömlek kenarı konturdan uzaktadır."""
    H, W = a.shape[:2]
    for _ in range(passes):
        src = a.copy()
        hh, ss, vv = hsv_of(src)
        vis = src[..., 3] > 0
        outline = (src[..., 0] == 43) & (src[..., 1] == 29) & (src[..., 2] == 46)
        zone = box_count(outline | ~vis, K) > 0
        edge = vis & ~outline & (vv > 0.45) & (ss < 0.12) & zone
        for y, x in zip(*np.nonzero(edge)):
            votes, dark = {}, 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if (dy or dx) and 0 <= ny < H and 0 <= nx < W and vis[ny, nx] and not outline[ny, nx] and vv[ny, nx] < 0.35:
                        dark += 1
                        k = tuple(src[ny, nx])
                        votes[k] = votes.get(k, 0) + 1
            if dark >= 2:
                a[y, x] = max(votes, key=votes.get)
    return a


def absorb_into_hair(a, g, passes=3):
    """Saçla çevrili (4 komşusundan en az 3'ü saç) ama saç sayılmamış pikseller saça katılır; açık renkliyse (pembe
    saçın parıltısı, koyu saçta beyaz nokta gibi kalıyordu) komşu saçın rengini alır."""
    hh, ss, vv = hsv_of(a)
    outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
    bzone, _ = body_skin_zone(a, face_box(a)[1])
    for _ in range(passes):
        hair = g == 1
        n = neighbors4(hair)
        cand = (a[..., 3] > 0) & ~hair & ~outline & (g != 2) & (g != 4) & (n >= 3) & ~(box_count(g == 4, 2 * K) > 0) & ~bzone
        if not cand.any():
            break
        for y, x in zip(*np.nonzero(cand)):
            if vv[y, x] > 0.8 and ss[y, x] < 0.25:
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if g[ny, nx] == 1:
                        a[y, x] = a[ny, nx]
                        break
            g[y, x] = 1
    # saç kenarındaki gri-beyaz saçak (beyaz zeminle karışım): konturun K piksel içinde, saça değen açık griler saç olur
    vis = a[..., 3] > 0
    zone = box_count(outline | ~vis, K) > 0
    hh, ss, vv = hsv_of(a)
    for _ in range(2 * K):
        rim = vis & ~outline & zone & ~bzone & (g != 1) & (g != 2) & (ss < 0.15) & (vv > 0.45) & (neighbors4(g == 1) >= 1)
        if not rim.any():
            break
        for y, x in zip(*np.nonzero(rim)):
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if g[ny, nx] == 1:
                    a[y, x] = a[ny, nx]
                    break
            g[y, x] = 1
        hh, ss, vv = hsv_of(a)
    # saçın koyu gölge kümeleri (kıyafete ya da gruba düşmemiş): çevresinin çoğu saç olan küçük koyu parçalar saçtır
    dark = (a[..., 3] > 0) & ~outline & (vv < 0.32) & ((g == 0) | (g == 3)) & ~(box_count(g == 4, 2 * K) > 0)
    lab, n = label(dark)
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() > 200 * K * K:
            continue
        ring = (neighbors4(m) > 0) & ~m & (a[..., 3] > 0) & ~outline
        if ring.sum() and (ring & (g == 1)).sum() >= 0.6 * ring.sum():
            g[m] = 1
    return a, g


def soften_hair_shine(a, g, keep=0.45):
    """Saçın parlama ışıklarını yumuşatır: ortalamadan açık tonlar ortalamaya doğru çekilir (keep: kalan fark oranı).

    Uygulama rengi değiştirirken açıklık farkını korur; pembe saçın beyaza yakın parlaması koyu saç renginde
    neredeyse beyaz şerit gibi kalıyordu. Gölgelere dokunulmaz."""
    import colorsys
    hair = (g == 1) & (a[..., 3] > 0)
    ys, xs = np.nonzero(hair)
    hls = [colorsys.rgb_to_hls(*(a[y, x, :3] / 255.0)) for y, x in zip(ys, xs)]
    mean_l = float(np.mean([l for _, l, _ in hls]))
    for (y, x), (hh, l, ss) in zip(zip(ys, xs), hls):
        if l > mean_l:
            r, gg, b = colorsys.hls_to_rgb(hh, mean_l + (l - mean_l) * keep, ss)
            a[y, x, :3] = (round(r * 255), round(gg * 255), round(b * 255))
    return a


def final_cleanup(a, g):
    """Son temizlik (bağımsız göz denetiminde bulunan kusurlar):
    - saçla çevrili (5×5'in %70'i saç) pembe/beyaz benekler saç olur, açık olanlar komşu saç rengini alır;
    - çevresi çoğunlukla koyu (çorap, hırka) gri-beyaz noktalar en sık koyu komşu renge çekilir;
    - şeffaflığa değen minik açık kırıntılar ve gövdeden kopuk küçük parçalar silinir."""
    H, W = a.shape[:2]
    r = 2 * K
    bzone, _ = body_skin_zone(a, face_box(a)[1])
    for _ in range(2):
        hh, ss, vv = hsv_of(a)
        vis = a[..., 3] > 0
        outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
        body = vis & ~outline
        total = np.maximum(box_count(body, r), 1)
        hair = g == 1
        hair_frac = box_count(hair, r) / total
        pinkish = (hh >= 290) | (hh < 5) | (ss < 0.12)
        near_bow = box_count(g == 4, r) > 0  # küçük fiyonkun iç pikselleri saçla çevrili, saça katılmasın
        cand = body & ~hair & (g != 2) & pinkish & (hair_frac >= 0.7) & ~near_bow & ~bzone
        for y, x in zip(*np.nonzero(cand)):
            if vv[y, x] > 0.6:
                ys, xs = np.nonzero(hair[max(y - r, 0):y + r + 1, max(x - r, 0):x + r + 1])
                if len(ys):
                    k = len(ys) // 2
                    a[y, x] = a[max(y - r, 0) + ys[k], max(x - r, 0) + xs[k]]
            g[y, x] = 1
        hh, ss, vv = hsv_of(a)
        # saç uçları ve kenarları: saça (4 komşudan en az 2'si) değen pembe/somon ya da açık renkli kalıntılar saçtır
        # (yüz kutusu hariç: allık, dudak, yanak saça komşu olabilir)
        ftop, chin, fx0, fx1 = face_box(a)
        face = np.zeros_like(body)
        face[ftop:chin + 1, fx0:fx1 + 1] = True
        hair = g == 1
        n4 = neighbors4(hair)
        tint = ((hh >= 290) | (hh <= 25)) & (ss >= 0.12)
        lightish = (vv > 0.7) & (ss < 0.25)
        near_hair = box_count(hair, r) >= 0.25 * (2 * r + 1) ** 2  # saç kenarındaki parlama çizgileri tek yandan değer
        rest = body & ~hair & (g != 2) & (g != 4) & ~face & ~bzone & ~(box_count(g == 4, r) > 0) & (tint | lightish) & ((n4 >= 1) & tint | (n4 >= 2) | near_hair)
        for y, x in zip(*np.nonzero(rest)):
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < H and 0 <= nx < W and g[ny, nx] == 1:
                    a[y, x] = a[ny, nx]
                    break
            g[y, x] = 1
        hh, ss, vv = hsv_of(a)
        dark = body & (vv < 0.35)
        dark_frac = box_count(dark, r) / total
        speck = body & (vv > 0.45) & (ss < 0.15) & (dark_frac >= 0.55) & (g != 2)
        src = a.copy()
        for y, x in zip(*np.nonzero(speck)):
            y0, x0 = max(y - r, 0), max(x - r, 0)
            win = dark[y0:y + r + 1, x0:x + r + 1]
            ys, xs = np.nonzero(win)
            votes = {}
            for yy, xx in zip(ys, xs):
                k = tuple(src[y0 + yy, x0 + xx])
                votes[k] = votes.get(k, 0) + 1
            if votes:
                a[y, x] = max(votes, key=votes.get)
    # boyun ve yaka üstündeki kopuk küçük saç parçaları: çizimde ince pembe tutam, koyu saç renginde leke gibi
    # okunuyor. Ana saç kütlesine bağlı olmayan, çenenin altında yüz hizasındaki parçalar çevrelerinin rengini alır.
    ftop, chin, fx0, fx1 = face_box(a)
    lab, n = label(g == 1)
    if n > 1:
        sizes = np.bincount(lab.ravel())[1:]
        big = sizes.max()
        vis = a[..., 3] > 0
        for i, size in enumerate(sizes, 1):
            if size >= 0.05 * big:
                continue
            m = lab == i
            ys, xs = np.nonzero(m)
            if chin - 4 * K <= ys.mean() <= chin + 70 * K and fx0 - 10 * K <= xs.mean() <= fx1 + 10 * K:
                ring = m.copy()
                for _ in range(2 * K):
                    ring |= neighbors4(ring) > 0
                ring &= ~m & vis & (g != 1)
                if ring.any():
                    a[m] = np.median(a[ring], axis=0).astype(np.uint8)
                    g[m] = 0
    # yaka bandı: çenenin hemen altında, yüz hizasındaki saç pikselleri (yakanın üstünden geçen ince tutam) koyu saç
    # renginde yakada leke gibi duruyor; yakanın rengini alır. Tutamın yüz hizası dışındaki kısmı saç kalır.
    collar = np.zeros(g.shape, bool)
    w = fx1 - fx0
    collar[chin + 1:chin + 1 + 30 * K, fx0 + w // 8:fx1 - w // 8] = True
    zone_hair = collar & (g == 1)
    if zone_hair.any():
        vis = a[..., 3] > 0
        hh, ss, vv = hsv_of(a)
        ref = vis & (g != 1) & (vv > 0.6) & ~((a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46))
        src = a.copy()
        for y, x in zip(*np.nonzero(zone_hair)):
            for d in range(1, 24 * K):
                hit = [xx for xx in (x - d, x + d) if 0 <= xx < W and ref[y, xx]]
                if hit:
                    a[y, x] = src[y, hit[0]]
                    break
            g[y, x] = 0
    # kıyafetin kenarından dışarı çıkan küçük açık renkli çıkıntılar (oturuşta hırka kenarında pembe "tik"):
    # çevresi kıyafet/kontur/boşluk olan küçük ten-beyaz parçalar ve yalnız kalan konturları silinir
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
    lightp = vis & ~outline & (g == 0) & (vv > 0.6)
    lab, n = label(lightp)
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() > 40 * K * K:
            continue
        ring = (neighbors4(m) > 0) & ~m
        outside = ring & ~vis
        near_out = (box_count(~vis, K) > 0) & m
        inner = ring & vis & ~outline
        if near_out.any() and inner.sum() and (inner & (g == 3)).sum() >= 0.6 * inner.sum():
            a[m] = 0
    vis = a[..., 3] > 0
    outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
    lonely = outline & vis & (neighbors4(vis & ~outline) == 0)
    a[lonely] = 0
    # yüz dışında tene bitişik magenta gölgeler (palet boyun/el gölgesini pembe-kırmızıya çekiyor): yakındaki tenin
    # biraz koyulaştırılmış tonuna çekilir
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    skin = vis & (hh >= 5) & (hh <= 45) & (ss >= 0.1) & (ss <= 0.45) & (vv > 0.7)
    ftop, chin, fx0, fx1 = face_box(a)
    magenta = vis & (g == 0) & ((hh >= 325) | (hh <= 5)) & (ss >= 0.2) & (vv >= 0.5) & (box_count(skin, 8 * K) > 0)
    magenta[ftop:chin + 1, fx0:fx1 + 1] = False  # yüzde allık ve ağız kalır
    src = a.copy()
    rr = 8 * K  # yan profilde boyun gölgesi yüz teninden birkaç piksel uzakta
    for y, x in zip(*np.nonzero(magenta)):
        y0, x0 = max(y - rr, 0), max(x - rr, 0)
        win = skin[y0:y + rr + 1, x0:x + rr + 1]
        if win.any():
            c = np.median(src[y0:y + rr + 1, x0:x + rr + 1][win][:, :3], axis=0) * 0.82
            a[y, x, :3] = c.astype(np.uint8)
    # şeffaflığa değen minik açık kırıntılar
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    light = vis & (vv > 0.6) & (ss < 0.2)
    lab, n = label(light)
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() <= 2 * K * K and (neighbors4(~vis) > 0)[m].any():
            a[m] = 0
    # gövdeden kopuk küçük parçalar
    vis = a[..., 3] > 0
    lab, n = label(vis)
    if n > 1:
        sizes = np.bincount(lab.ravel())[1:]
        for i, size in enumerate(sizes, 1):
            if size < 30 * K * K:
                a[lab == i] = 0
    g[a[..., 3] == 0] = 0
    return a, g


def smooth_eyes(a, g, smooth):
    """Göz bölgeleri (her mavi irisin çevresinde, kirpikleri de içine alan elips) yumuşak küçültmeden alınır:
    parlama, göz bebeği ve iris geçişi orijinaldeki gibi kalır. Dönüş: (görsel, göz bölgesi maskesi)."""
    zone = np.zeros(g.shape, bool)
    lab, n = label(g == 2)
    if not n:
        return a, zone
    sizes = np.bincount(lab.ravel())[1:]
    yy, xx = np.mgrid[0:g.shape[0], 0:g.shape[1]]
    for i in np.argsort(-sizes)[:2] + 1:
        ys, xs = np.nonzero(lab == i)
        if len(ys) < 3:
            continue
        cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
        rx, ry = (xs.max() - xs.min()) / 2 + 3 * K, (ys.max() - ys.min()) / 2 + 3 * K
        zone |= ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1
    zone &= a[..., 3] > 0
    a = a.copy()
    a[zone, :3] = smooth[zone]
    return a, zone


def save_frames():
    """Temizlenmiş sprite + grup haritası: out/pose_<ad>.png ve out/pose_<ad>_groups.png (animate_poses girdisi).
    Girdi her zaman ham out/pose_<ad>_raw.png: temizlik iki kez uygulanırsa saçta turuncu noktalar çıkıyordu."""
    names = ["bust", "stand", "walk", "sit"] + [f"wk{i}" for i in range(8)
                                                if os.path.exists(os.path.join(HERE, "out", f"pose{TAG}_wk{i}_raw.png"))]
    for name in names:
        a = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_{name}_raw.png")).convert("RGBA"))
        smooth = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_{name}_smooth.png")).convert("RGB"))
        a, eye_zone = smooth_eyes(a, groups(a), smooth)
        g = groups(a)
        hh, ss, vv = hsv_of(a)
        ftop, chin, fx0, fx1 = face_box(a)
        # Tutamların arasında kalan beyaz arka plan boşlukları: neredeyse beyaz, çevresi çoğunlukla saç olan
        # bölgeler şeffaf yapılır (koyu saç renginde beyaz kama gibi görünüyorlar). Bluz kıyafet/tenle çevrili, kalır.
        hh, ss, vv = hsv_of(a)
        white = (a[..., 3] > 0) & (ss < 0.18) & (vv > 0.86) & (g != 2)
        lab, n = label(white)
        hair = g == 1
        outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
        for i in range(1, n + 1):
            m = lab == i
            if m.sum() < 6 * K * K:
                continue
            ring = (neighbors4(m) > 0) & ~m & (a[..., 3] > 0) & ~outline
            # çenenin altında, yüz hizasında duran beyaz, saç tellerinin arasından görünen yakadır, boşluk değil
            ys_, xs_ = np.nonzero(m)
            collar = chin - 10 * K <= ys_.mean() <= chin + 80 * K and fx0 - 20 * K <= xs_.mean() <= fx1 + 20 * K
            if ring.sum() and not collar and not (m & eye_zone).any() and (ring & hair).sum() >= 0.55 * ring.sum():
                a[m] = 0
        # Saf beyaz (s<0.035, v>0.97) arka plandır: çizimde hiçbir yüzey bu kadar beyaz değil, gömleğin parlak yerleri
        # bile hafif sıcak/gridir. Çevresi çoğunlukla gömlek tonu olmayan saf beyaz kümeler (çene ile saç arası, saç
        # tutamları arası) şeffaf yapılır; gömleğin ortasındaki parlamalar gömlekle çevrili olduğu için kalır.
        hh, ss, vv = hsv_of(a)
        vis = a[..., 3] > 0
        pure = vis & (ss < 0.035) & (vv > 0.97)
        shirtish = vis & ~pure & (ss < 0.12) & (vv > 0.75)
        lab, n = label(pure)
        for i in range(1, n + 1):
            m = lab == i
            ring = (neighbors4(m) > 0) & ~m & vis & ~outline
            if ring.sum() and not (m & eye_zone).any() and (ring & shirtish).sum() < 0.5 * ring.sum():
                a[m] = 0
        g[a[..., 3] == 0] = 0
        # gürültü temizliği: göz çevresi ve ten üstü (ağız, allık, parmak çizgileri) korunur
        hh, ss, vv = hsv_of(a)
        skin = (a[..., 3] > 0) & (hh >= 5) & (hh <= 45) & (ss >= 0.1) & (ss <= 0.45) & (vv > 0.7)
        protect = eye_zone | (box_count(g == 2, 3) > 0) | (box_count(skin, 1) >= 3)
        a = despeckle(a, protect)
        a = edge_fringe(a)
        g = groups(a)  # boşluk açılınca kenardaki pembe saçak da saça katılsın
        a, g = absorb_into_hair(a, g)
        a, g = final_cleanup(a, g)
        a = soften_hair_shine(a, g, SHINE)
        g[a[..., 3] == 0] = 0
        Image.fromarray(a, "RGBA").save(os.path.join(HERE, "out", f"pose{TAG}_{name}.png"))
        Image.fromarray(g, "L").save(os.path.join(HERE, "out", f"pose{TAG}_{name}_groups.png"))
        print(name, {k: int((g == i).sum()) for k, i in (("saç", 1), ("göz", 2), ("kıyafet", 3), ("kurdele", 4))})


# ---- Animasyon: her poz için nefes + göz kırpma (idle), ağzı oynayan konuşma (talk); büste 9 ifade ----

PATTERN = [0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0]   # talk.py ile aynı ağız ritmi
ALT = {"open": "smile", "smile": "o", "cat": "o", "o": "yawn", "frown": "yawn", "yawn": "o", "wavy": "o"}
BREATH = {"bust": 1.0, "stand": 0.45, "sit": 0.6}  # bu oranın üstündeki satırlar nefeste 1 px kalkar (büst: hepsi)


def face_of(a, g, name):
    """Göz ve ağız yerleri: emotes.FACE biçiminde yüz + animate.close_eyes biçiminde göz listesi."""
    h, s, v = hsv_of(a)
    vis = a[..., 3] > 0
    skin = vis & (h >= 5) & (h <= 45) & (s >= 0.1) & (s <= 0.45) & (v > 0.7)
    lab, n = label(g == 2)
    eyes = []
    for i in sorted(range(1, n + 1), key=lambda i: -(lab == i).sum())[:2]:
        ys, xs = np.nonzero(lab == i)
        if len(ys) >= 3:
            eyes.append((int(round(xs.mean())), int(round(ys.mean())), (xs.max() - xs.min()) // 2 + 4 * K, (ys.max() - ys.min()) // 2 + 3 * K))
    eyes.sort()
    if not eyes:
        return None, []
    ey = max(e[1] + e[3] for e in eyes)
    x0 = min(e[0] - e[2] for e in eyes) - 6 * K
    x1 = max(e[0] + e[2] for e in eyes) + 6 * K
    # ağız: gözlerin altında, çevresi (neredeyse) tamamen ten olan pembe/kırmızı parça. Çene konturu da kırmızımsıdır
    # ama bir yanı boyna/saça değer; allık küçük ve soluktur.
    cand = vis & ~skin & ((h >= 330) | (h <= 15)) & (s >= 0.2)
    cand[:ey - 2] = False
    cand[ey + 45 * K:] = False
    cand[:, :max(x0, 0)] = False
    cand[:, x1:] = False
    clab, cn = label(cand)
    mouthy, best = np.zeros_like(cand), 0
    for i in range(1, cn + 1):
        m = clab == i
        n_ = int(m.sum())
        ring = (neighbors4(m) > 0) & ~m
        ys_, xs_ = np.nonzero(m)
        # gözlerin arasında ve onlara yakın (çene çizgisi daha aşağıda, allık gözlerin altında yanlarda kalır)
        between = len(eyes) < 2 or eyes[0][0] - 4 * K <= xs_.mean() <= eyes[1][0] + 4 * K
        near = len(eyes) < 2 or ys_.mean() <= ey + 0.75 * (eyes[1][0] - eyes[0][0])
        if n_ >= 6 * K * K and n_ > best and between and near and ring.sum() and (ring & skin).sum() >= 0.7 * ring.sum():
            mouthy, best = m, n_
    ys, xs = np.nonzero(mouthy)
    mouth = (int(round(xs.mean())), int(round(ys.mean()))) if len(ys) >= 4 else None
    # ağzın tamamı (dil, diş, dudak çizgisi): doygun çekirdekten tene değmeden büyüyen bölge, kutuyla sınırlı
    region = np.zeros_like(mouthy)
    if mouth:
        bx0, by0, bx1, by1 = xs.min() - 2 * K, ys.min() - 2 * K, xs.max() + 3 * K, ys.max() + 3 * K
        allowed = np.zeros_like(mouthy)
        allowed[by0:by1, bx0:bx1] = True
        allowed &= vis & ~skin
        region = mouthy.copy()
        for _ in range(4 * K):
            region |= (neighbors4(region) > 0) & allowed
    rx = int(round(np.mean([e[2] for e in eyes])))
    ry = int(round(np.mean([e[3] for e in eyes])))
    tilt = (eyes[1][1] - eyes[0][1]) / max(eyes[1][0] - eyes[0][0], 1) if len(eyes) == 2 else 0.0
    W = a.shape[1]
    face = {
        "eyes": [(e[0], e[1]) for e in eyes], "eye_r": (rx, ry),
        "mouth": mouth or (eyes[0][0], ey + 10),
        "mouth_box": (xs.min() - 3, ys.min() - 3, xs.max() + 4, ys.max() + 6) if mouth else (0, 0, 0, 0),
        "cheeks": [(e[0] - 2, e[1] + e[3] + 4) for e in eyes], "tilt": round(tilt, 2),
        "fx_left": (6, 14), "fx_right": (W - 26, 0), "sweat": (eyes[-1][0] + rx + 4, max(eyes[-1][1] - ry - 10, 0)),
        "has_mouth": mouth is not None, "mouth_mask": region, "mouth_w": int(xs.max() - xs.min() + 1) if mouth else 0,
    }
    rig_eyes = [(cx, cy, rx_, ry_, (cy + 1, cy + 2, cy + 1)) for cx, cy, rx_, ry_ in eyes]
    return face, rig_eyes


def clear_mouth(img, face):
    """Açık ağzı siler: ağız bölgesini çevresindeki tenin ortanca rengiyle doldurur (sütun sütun almak burun
    gölgesinden dikey çizgi bırakıyordu)."""
    out = img.copy()
    m = face["mouth_mask"]
    if not m.any():
        return out
    h, s, v = hsv_of(img)
    skin = (img[..., 3] > 0) & (h >= 5) & (h <= 45) & (s >= 0.1) & (s <= 0.45) & (v > 0.7)
    ring = m.copy()
    for _ in range(3 * K):
        ring |= neighbors4(ring) > 0
    ring &= ~m & skin
    out[m] = np.median(img[ring], axis=0).astype(np.uint8) if ring.any() else img[m][0]
    return out


SMOOTH_TALK = False  # smooth.py açar: çizilmiş ağız yarıya basılır (pürüzsüz çizimde dudak çizgisi leke gibi duruyordu)


def squash_mouth(img, face):
    """Konuşurken arada kapanan ağız: ağız bölgesi kendi üst kenarına doğru yarı yüksekliğe basılır; açılan yer
    çevredeki tenle yumuşakça dolar."""
    m = face["mouth_mask"]
    if not m.any():
        return img
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = ys.min() - 1, ys.max() + 2, xs.min() - 1, xs.max() + 2
    region, mreg = img[y0:y1, x0:x1].copy(), m[y0:y1, x0:x1]
    out = img.copy()
    # boşluğu komşu ortalamalarıyla doldur (düz yama yerine yumuşak geçiş)
    hole = np.zeros(m.shape, bool)
    hole[y0:y1, x0:x1] = mreg
    out = clear_mouth(out, face).astype(float)
    for _ in range(30):
        avg = out.copy()
        avg[1:-1, 1:-1] = (out[:-2, 1:-1] + out[2:, 1:-1] + out[1:-1, :-2] + out[1:-1, 2:]) / 4
        out[hole] = avg[hole]
    out = out.astype(np.uint8)
    h = y1 - y0
    nh = max(2, h // 2)
    r = np.array(Image.fromarray(region, "RGBA").resize((x1 - x0, nh), Image.LANCZOS))
    rm = np.array(Image.fromarray((mreg * 255).astype(np.uint8)).resize((x1 - x0, nh), Image.LANCZOS)) > 100
    ty = y0 + h // 4
    sub = out[ty:ty + nh, x0:x1]
    sub[rm] = r[rm]
    return out


def closed_mouth(img, face):
    if SMOOTH_TALK:
        return squash_mouth(img, face)
    """Konuşurken arada kapanan ağız: ağzı siler, ölçeğe göre küçük, uçları hafif kalkık bir dudak çizer."""
    import emotes
    out = clear_mouth(img, face)
    cx, cy = face["mouth"]
    hw = max(1, face["mouth_w"] // 4)
    for x in range(cx - hw, cx + hw + 1):
        y = cy - (K if hw >= 3 * K and abs(x - cx) >= hw - K + 1 else 0)
        out[y:y + K, x] = emotes.LIP
    return out


def coarse_overlay(shape, face, emote, i):
    """İfadenin allığı ve efektleri (kalp, nota, ter...) emotes.py ile yarım çözünürlükte çizilip K kat büyütülür:
    eski kaba pixel boyutunda ve doğru yerde dururlar. Gözlere ve ağza dokunulmaz (ifade çizimleri gelene kadar;
    gözü silip yeniden çizmek yeni çizimde gözü oyulmuş gibi gösteriyordu)."""
    import emotes
    h, w = shape[0] // K, shape[1] // K
    layer = np.zeros((h, w, 4), np.uint8)
    half = dict(face)
    sc = lambda p: (p[0] // K, p[1] // K)
    half["eyes"] = [sc(e) for e in face["eyes"]]
    half["cheeks"] = [sc(c) for c in face["cheeks"]]
    half["sweat"] = sc(face["sweat"])
    # efektler başın yanında, büstün en üstünde değil: oraya konuşma balonu biniyor, parıltının yarısı kalıyordu
    half["fx_left"], half["fx_right"] = (6, 40), (w - 26, 40)
    _, _, _, bl, effect, _ = emotes.EMOTES[emote]
    if effect in ("tear", "sweat"):
        effect = None  # bu ölçekte damla "+" işareti gibi görünüyor; ifade çizimleri gelince yeniden
    if bl and K > 1:  # yeni görünümde (K=1) ifade çizimlerinin kendi allığı var; piksel çizgiler kaba duruyordu
        emotes.blush(layer, half, bl == "heavy")
    if effect:
        emotes.fx(layer, half, effect, i)
    return layer.repeat(K, axis=0).repeat(K, axis=1)


def breathe(img, cut, up):
    """Nefes: kesimin üstü K piksel kalkar (animate.breathe 1 piksel kaydırır)."""
    import animate
    for _ in range(K if up else 0):
        img = animate.breathe(img, cut, True)
    return img


# Konuşma ağız sırası (12 karelik döngü): k kapalı, o küçük yuvarlak, a orijinal açık, g geniş açık
TALK_SEQ = "aokgaokaogka"


def emit_pose(name, a, g, face, out_dir, emote=None, plain=False, blink=None, mouths=None):
    """plain: masaüstü uygulamasının adları (idle_, talk_ ve bildirimde oynayan wave_). Yeni çizimde el sallayan
    poz yok; wave_ selam zıplaması: büst iki kez hafifçe aşağı inip kalkar (alt kenar pencerenin dibinde kesik)."""
    os.makedirs(os.path.join(out_dir, "groups"), exist_ok=True)
    gimg = np.zeros_like(a)
    gimg[..., 0] = g
    gimg[..., 3] = a[..., 3]
    cut = int(a.shape[0] * BREATH.get(name, 1.0))

    def save(fname, frame, gframe):
        gframe = gframe.copy()
        gframe[frame[..., 3] == 0, 0] = 0
        Image.fromarray(frame, "RGBA").save(os.path.join(out_dir, fname))
        gg = gframe[..., 0]
        Image.fromarray(np.stack([gg, gg, gg], -1), "RGB").save(os.path.join(out_dir, "groups", fname))

    # blink: {kare no: (resim, grup haritası)}; 24 karelik döngüde (~3,4 sn) bir kez yarı kapalı → kapalı → yarı kapalı.
    # İfadenin kendi gözleri kapalıysa ya da kırpmıyorsa kırpmaz.
    bl = {}
    if blink and (not emote or __import__("emotes").EMOTES[emote][5]):
        for k, (bi, bg_) in blink.items():
            gb_ = gimg.copy()
            gb_[..., 0] = bg_
            gb_[..., 3] = bi[..., 3]
            bl[k] = (bi, gb_)
    for i in range(24):
        frame, gframe = (bl[i][0].copy(), bl[i][1].copy()) if i in bl else (a.copy(), gimg.copy())
        if emote:
            ov = coarse_overlay(a.shape, face, emote, i)
            m = ov[..., 3] > 0
            frame[m] = ov[m]
            gframe[m, 0] = 0  # efekt ve allık boyanmaz
        up = (i // 3) % 2 == 1
        talk, gtalk = frame.copy(), gframe.copy()
        if mouths:
            # çizilmiş ağız şekilleri: ağız bölgesi (yumuşak maske) o anki kareye (göz kırpan kare dahil) taşınır
            shapes, mm = mouths
            sh = shapes[TALK_SEQ[i % len(TALK_SEQ)]]
            m3 = mm[..., None]
            talk[..., :3] = (talk[..., :3] * (1 - m3) + sh[..., :3] * m3).round().astype(np.uint8)
            gtalk[mm > 0.5, 0] = 0  # ağız boyanmaz
        elif PATTERN[i % 12] and face["has_mouth"]:
            # ağız nefes kaydırmasından önce çizilir; nefes iki kareye de aynı uygulanır
            talk = closed_mouth(talk, face)
            gtalk[(talk != frame).any(axis=2), 0] = 0
        pre = "" if plain else name + "-"
        save(f"{pre}idle_{i:02d}.png", breathe(frame, cut, up), breathe(gframe, cut, up))
        save(f"{pre}talk_{i:02d}.png", breathe(talk, cut, up), breathe(gtalk, cut, up))
        if plain:
            # 20 karelik selam: ilk 12 karede iki zıplama (aşağı-yukarı), sonra dinlenir
            for j in (i,):
                if j >= 20:
                    continue
                dy = int(round(3 * K * abs(np.sin(j * np.pi / 6)))) if j < 12 else 0
                fr, gf = frame.copy(), gframe.copy()
                if dy:
                    fr = np.concatenate([np.zeros((dy,) + fr.shape[1:], np.uint8), fr[:-dy]])
                    gf = np.concatenate([np.zeros((dy,) + gf.shape[1:], np.uint8), gf[:-dy]])
                save(f"wave_{j:02d}.png", fr, gf)


def animate_poses(look="klasik", walk=True, extra=None):
    """walk=False: kodla üretilen yürüme kareleri yazılmaz (masaüstünde kötü görünüyor; çizilmiş adım kareleri bekleniyor).
    extra: {poz adı: emit_pose'a ek argümanlar} (tam boy pozun göz kırpma ve konuşma ağzı kareleri, smooth.full_extras)."""
    d = os.path.join(HERE, "frames", look)
    for name in ("bust", "stand", "sit", "walk"):
        a = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_{name}.png")).convert("RGBA"))
        g = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_{name}_groups.png")))
        if name == "walk":
            if walk:
                walk_cycle(look)
            continue
        face, rig_eyes = face_of(a, g, name)
        print(name, "gözler", [e[:2] for e in rig_eyes], "ağız", face["mouth"] if face["has_mouth"] else None)
        emit_pose(name, a, g, face, d, **(extra or {}).get(name, {}))
        if name == "bust":
            import emotes
            for e in emotes.EMOTES:
                emit_pose(name, a, g, face, os.path.join(d, "emotes", e), e)


# ---- Yürüme döngüsü: tek yürüyüş karesinden, bacakları kalçadan döndürerek ----
# Ölçüler out/pose_walk.png içinde (186×315, sağa yürür): etek y≈165'te biter, bacaklar y≈185'te ayrılır.
# (Ölçüler kaba K=1 karesine göredir, K ile çarpılır.)
HEM, SPLIT_Y, SPLIT_X = 166 * K, 200 * K, 98 * K
HIP_Y = 150 * K      # kalça eklemi eteğin altında, etek bitiminden yukarıda: bacak oradan döner
HIP_BACK, HIP_FRONT = (86 * K, HIP_Y), (110 * K, HIP_Y)
HAND = (72 * K, 196 * K)  # kalçadaki sol el (x <, y <): bacakla dönmesin, gövdede kalsın
SWING = 36           # bir adımda her bacağın döndüğü toplam açı (derece); eklem çorap üstünde
STEPS = 8            # döngü karesi
PAD = 16 * K         # gövde adımla kalkınca saç kesilmesin diye üst pay


def leg_masks(a):
    vis = a[..., 3] > 0
    back = np.zeros_like(vis)
    front = np.zeros_like(vis)
    H = a.shape[0]
    xs = np.arange(a.shape[1])
    for y in range(HEM, min(SPLIT_Y, H)):
        back[y] = vis[y] & (xs < SPLIT_X)
        front[y] = vis[y] & (xs >= SPLIT_X)
    lower = vis.copy()
    lower[:SPLIT_Y] = False
    lab, n = label(lower)
    sizes = np.bincount(lab.ravel())[1:]
    for i in np.argsort(-sizes)[:2] + 1:
        m = lab == i
        (back if np.nonzero(m)[1].mean() < SPLIT_X else front)[m] = True
    # bacaklara değen küçük kırıntılar da en yakın bacağa
    for i in np.argsort(-sizes)[2:] + 1:
        m = lab == i
        (back if np.nonzero(m)[1].mean() < SPLIT_X else front)[m] = True
    # kutudaki el: ten pikselleri + 2 px çevresi (kontur); kutudaki çorap/kalça kenarı bacakta kalır
    h, s, v = hsv_of(a)
    box = np.zeros_like(vis)
    box[:HAND[1], :HAND[0]] = True
    hand = box & vis & (h >= 5) & (h <= 45) & (s >= 0.1) & (v > 0.6)
    hand = box & (box_count(hand, 2 * K) > 0)
    # kontur bacakla dönmez (köşeleri kalçada siyah sivri gibi taşıyordu); döndükten sonra yeniden çizilir
    outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
    return back & ~hand & ~outline, front & ~hand & ~outline


def rotate(layer, mask, pivot, deg):
    """Katmanı pivot etrafında döndürür (en yakın komşu), tüm tuval üzerinde: büyük açıda ayak kesilmesin."""
    import math
    hh, ww = mask.shape
    yy, xx = np.mgrid[0:hh, 0:ww]
    r = math.radians(deg)
    ca, sa = math.cos(r), math.sin(r)
    dx, dy = xx + 0.5 - pivot[0], yy + 0.5 - pivot[1]
    ix = np.floor(ca * dx + sa * dy + pivot[0]).astype(int)
    iy = np.floor(-sa * dx + ca * dy + pivot[1]).astype(int)
    ok = (ix >= 0) & (ix < ww) & (iy >= 0) & (iy < hh)
    ok[ok] = mask[iy[ok], ix[ok]]
    out = np.zeros_like(layer)
    out[ok] = layer[iy[ok], ix[ok]]
    return out, ok


def walk_cycle(look="klasik"):
    import animate
    src = np.array(Image.open(os.path.join(HERE, "out", "pose" + TAG + "_walk.png")).convert("RGBA"))
    gsrc = np.array(Image.open(os.path.join(HERE, "out", "pose" + TAG + "_walk_groups.png")))
    H, W = src.shape[:2]
    SIDE, BOTTOM = 40 * K, 80 * K
    # çalışma tuvali: üstte adım payı, yanlarda ve altta dönen bacaklara yer
    a = np.zeros((PAD + H + BOTTOM, SIDE + W + SIDE, 4), np.uint8)
    a[PAD:PAD + H, SIDE:SIDE + W] = src
    gimg = np.zeros_like(a)
    gimg[PAD:PAD + H, SIDE:SIDE + W, 0] = gsrc
    gimg[..., 3] = a[..., 3]
    back0, front0 = leg_masks(src)
    back = np.zeros(a.shape[:2], bool)
    front = np.zeros_like(back)
    back[PAD:PAD + H, SIDE:SIDE + W] = back0
    front[PAD:PAD + H, SIDE:SIDE + W] = front0
    # Uyluğun çıplak kısmı (etek ile çorap arası) çizimdeki gibi gövdede sabit kalır; yalnız çorabın başladığı
    # yerden aşağısı döner. (Uyluk da dönünce iki tonlu düz bloklar ve dikiş çıkıyor, kalça yanlarında taşan
    # ince parçalar kontur alıp siyah diken gibi görünüyordu.) Eklem her bacakta çorap üst kenarının ortası.
    hs, ss_, vs = hsv_of(a)
    dark = (vs < 0.35) & (a[..., 3] > 0)
    pivots = []
    for mask in (back, front):
        top = None
        for y in range(PAD + HEM, a.shape[0]):
            row = mask[y]
            if row.sum() >= 4 * K and (dark[y] & row).sum() >= 0.6 * row.sum():
                top = y
                break
        mask[:top] = False
        cols = np.nonzero(mask[top])[0]
        pivots.append((int(cols.mean()), top, cols))
    legs = back | front
    body, gbody = a.copy(), gimg.copy()
    # gövdeden çoraplı bacaklar ve onların eski konturu çıkar (kontur döndükten sonra yeniden çizilir); uyluk kalır
    old_outline = (a[..., 0] == 43) & (a[..., 1] == 29) & (a[..., 2] == 46)
    old_outline[:min(p[1] for p in pivots)] = False
    body[legs | old_outline] = 0
    gbody[legs | old_outline] = 0
    # Gövde ayrıldıktan sonra: çorabın üst satırı birkaç satır yukarı uzatılır (uyluğun arkasında, gövdenin altında
    # kalır): bacak dönünce çorap üstüyle uyluk arasında boşluk açılmasın
    for mask, (_, top, cols) in zip((back, front), pivots):
        for y in range(top - 6 * K, top):
            a[y, cols] = a[top, cols]
            gimg[y, cols] = gimg[top, cols]
            mask[y, cols] = True
    hip_b, hip_f = [(x, y) for x, y, _ in pivots]
    d = os.path.join(HERE, "frames", look)
    for old in os.listdir(d):
        if old.startswith("walk_"):
            os.remove(os.path.join(d, old))
            if os.path.exists(os.path.join(d, "groups", old)):
                os.remove(os.path.join(d, "groups", old))
    OH, OW = PAD + H, SIDE + W + SIDE  # çıktı karesi: ayaklar dipte
    for i in range(STEPS):
        t = i / STEPS
        frame = np.zeros_like(a)
        gframe = np.zeros_like(a)
        # öndeki bacak öne açıktan geriye, arkadaki geriden öne süpürür; döngü sonunda roller yer değiştirmiş olur
        for mask, pivot, deg in ((back, hip_b, -SWING * t), (front, hip_f, SWING * t)):
            layer, lm = rotate(np.where(mask[..., None], a, 0).astype(np.uint8), mask, pivot, deg)
            glayer, _ = rotate(np.where(mask[..., None], gimg, 0).astype(np.uint8), mask, pivot, deg)
            frame[lm] = layer[lm]
            gframe[lm] = glayer[lm]
        bm = body[..., 3] > 0
        frame[bm] = body[bm]
        gframe[bm] = gbody[bm]
        # gövdeden kopuk minik kırıntılar (el çevresinde kalan kontur parçaları) silinir
        lab, n = label(frame[..., 3] > 0)
        for k, size in enumerate(np.bincount(lab.ravel())[1:], 1):
            if size < 12 * K * K:
                frame[lab == k] = 0
                gframe[lab == k] = 0
        frame = animate.outline(frame)
        # yere basan ayak hep aynı hizada: en alttaki satır çıktı karesinin dibine gelir
        lowest = np.nonzero(frame[..., 3].any(axis=1))[0].max()
        top = lowest + 1 - OH
        if top < 0:  # ayak yukarıda kaldıysa üstte boş satır açılır
            frame = np.concatenate([np.zeros((-top,) + frame.shape[1:], np.uint8), frame])
            gframe = np.concatenate([np.zeros((-top,) + gframe.shape[1:], np.uint8), gframe])
            lowest, top = lowest - top, 0
        frame, gframe = frame[top:lowest + 1], gframe[top:lowest + 1]
        gg = gframe[..., 0].copy()
        gg[frame[..., 3] == 0] = 0
        Image.fromarray(frame, "RGBA").save(os.path.join(d, f"walk_{i:02d}.png"))
        Image.fromarray(np.stack([gg, gg, gg], -1), "RGB").save(os.path.join(d, "groups", f"walk_{i:02d}.png"))
    print("yürüme:", STEPS, "kare")


def walk_frames(look):
    """Çizilmiş yürüme kareleri (wk0..): yüz hizasından yatay, ayak tabanından dikey hizalanır; walk_XX olarak yazılır.
    Adım uzunluğunu da walk.txt'ye yazar (uygulama yürüme hızını buna göre ayarlar, ayaklar kaymasın)."""
    items = []
    i = 0
    while os.path.exists(os.path.join(HERE, "out", f"pose{TAG}_wk{i}.png")):
        a = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_wk{i}.png")).convert("RGBA"))
        g = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_wk{i}_groups.png")))
        # yatay çapa: baş hizasındaki (boyun %8-%20'si) en öndeki piksel, yani yüz profili. Yan profilde face_box
        # saçı ya da eli yüz sanabiliyor; kareler iki ayrı yere kayıyordu.
        h = a.shape[0]
        band = a[int(h * 0.08):int(h * 0.20), :, 3] > 0
        ax = int(np.nonzero(band.any(axis=0))[0].max())
        # göz: yan profilde iris küçük ve soluk mavi (s≈0.1), groups() yüz kutusunu da şaşırıyor; yüz önündeki
        # 16 px'lik baş bandında mavimsi pikseller göz grubu olur (yoksa göz rengi yürürken uygulanmıyordu)
        hh, ss, vv = hsv_of(a)
        eye = (a[..., 3] > 0) & (hh >= 180) & (hh <= 260) & (ss >= 0.08) & (vv >= 0.3)
        eye[:int(h * 0.08)] = False
        eye[int(h * 0.20):] = False
        eye[:, :max(ax - 16 * K, 0)] = False
        g = g.copy()
        g[eye] = 2
        items.append((a, g, ax))
        i += 1
    if not items:
        return
    left = max(ax for a, g, ax in items) + 4 * K
    right = max(a.shape[1] - ax for a, g, ax in items) + 4 * K
    H = max(a.shape[0] for a, g, ax in items)
    d = os.path.join(HERE, "frames", look)
    for old in os.listdir(d):
        if old.startswith("walk_"):
            os.remove(os.path.join(d, old))
            if os.path.exists(os.path.join(d, "groups", old)):
                os.remove(os.path.join(d, "groups", old))
    widths = []
    for k, (a, g, ax) in enumerate(items):
        frame = np.zeros((H, left + right, 4), np.uint8)
        gf = np.zeros((H, left + right), np.uint8)
        y0, x0 = H - a.shape[0], left - ax
        frame[y0:, x0:x0 + a.shape[1]] = a
        gf[y0:, x0:x0 + a.shape[1]] = g
        Image.fromarray(frame, "RGBA").save(os.path.join(d, f"walk_{k:02d}.png"))
        Image.fromarray(np.stack([gf, gf, gf], -1), "RGB").save(os.path.join(d, "groups", f"walk_{k:02d}.png"))
        # adım: alt %8'deki (ayaklar) piksellerin yatay yayılımı
        feet = np.nonzero(a[int(a.shape[0] * 0.92):, :, 3].any(axis=0))[0]
        widths.append(feet.max() - feet.min())
    # bir döngüde (2 adım) alınan yol ≈ 2 × (ayaklar en açıkken aradaki mesafe − bir ayakkabı boyu)
    step = int(2 * max(widths) * 0.6)
    with open(os.path.join(d, "walk.txt"), "w") as f:
        f.write(str(step))
    print("yürüme:", len(items), "kare, adım", step, "px")


def desktop_look(look="yeni"):
    """Masaüstü uygulaması için yeni çizimli görünüm: frames/<look>/ altında idle_, talk_, wave_ ve 9 ifade;
    gezinti için tam boy pozlar (stand-, sit-, walk_) da aynı klasöre yazılır."""
    import emotes
    d = os.path.join(HERE, "frames", look)
    a = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_bust.png")).convert("RGBA"))
    g = np.array(Image.open(os.path.join(HERE, "out", f"pose{TAG}_bust_groups.png")))
    face, rig_eyes = face_of(a, g, "bust")
    print(look, "gözler", [e[:2] for e in rig_eyes], "ağız", face["mouth"] if face["has_mouth"] else None)
    emit_pose("bust", a, g, face, d, plain=True)
    for e in emotes.EMOTES:
        emit_pose("bust", a, g, face, os.path.join(d, "emotes", e), e, plain=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "src", "poses", "sheet.webp"))
    save_frames()
    if K == 1:
        desktop_look()
        animate_poses("yeni", walk=False)
        walk_frames("yeni")
    else:
        animate_poses(walk=not os.path.exists(WALK_SHEET))
        walk_frames("klasik")
