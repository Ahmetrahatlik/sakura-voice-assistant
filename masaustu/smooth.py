"""Pürüzsüz (pixelsiz) görünüm: ChatGPT çizimlerinden yumuşak kenarlı, küçültülmüş kareler → frames/yeni.

Kullanım: python smooth.py
Pixel hattı (poses.py) her bloğu tek renge indirirken saçta nokta, kenarda beyazlık, gözde bozulma bırakıyordu;
burada çizim olduğu gibi küçültülür. Arka plan kenardan taşma ile, saç tutamları/çene arasındaki kapalı beyaz
boşluklar halkalarına bakılarak silinir; kenar içe doğru yumuşatılır (beyaz hale kalmasın). Ardından poses.py'nin
animasyon adımları (nefes, konuşma, ifade efektleri, ayakta/oturma, yürüme) aynen kullanılır.
"""
import math
import os

os.environ["POSE_K"] = "1"  # poses: masaüstü ölçüleri, out/pose_k1_* dosyaları

import numpy as np
from PIL import Image, ImageFilter

import pixelize
import poses
poses.SMOOTH_TALK = True
from poses import box_count, hsv_of, label, neighbors4

HERE = poses.HERE

# Yeşil saç maskesi (2026-10-23): src/poses/yesil/<ad>.png varsa (Gemini'nin saçı düz yeşil kopyası) kaynak odur.
# Saç baştan sona yeşil kalır (küçültme, nefes, el sallama saç bilgisini kendiliğinden taşır); son adımda
# green_finalize her karede yeşilden saç oranı (0-1) ve gölgeyi çıkarır, saçı varsayılan pembeyle boyar.
# Sakura.cs bu oranla boyar: saç/ten sınıflandırması ve onun kenar hataları yok.
# Çıktı görünümü SMOOTH_LOOK (varsayılan "yeni"; denemeyi ayrı klasöre almak için ör. SMOOTH_LOOK=yesil).
GREEN_DIR = os.path.join(HERE, "src", "poses", "yesil")
GREEN = os.path.exists(os.path.join(GREEN_DIR, "sheet.png")) and os.environ.get("SMOOTH_GREEN", "1") == "1"
import aksesuar  # noqa: E402
# SMOOTH_AKS=<ad> (aksesuar.NAMES): aksesuarlı görünüm frames/yeni-<ad>
LOOK = os.environ.get("SMOOTH_LOOK", "yeni" + ("-" + aksesuar.AKS if aksesuar.AKS else ""))
BUST_EYES = None  # büstün göz merkezleri (placed tuvalinde): gözü kapalı/kırpan karelerde aksesuar buna göre takılır
ACC_MASKS = {}  # kare boyu → aksesuar maskesi: group_map orayı renk grubuna koymaz (bere kurdele sanılıp boyanmasın)
POSE_ACC = {}  # tam boy poz → (üst pay, gözler): göz kırpma/konuşma kareleri aynı payla, aynı yere takılır


def source(name):
    """Kaynak sayfa: yeşil kopyası varsa o."""
    g = os.path.join(GREEN_DIR, name + ".png")
    return g if GREEN and os.path.exists(g) else os.path.join(HERE, "src", "poses", name + ".webp")


if GREEN:
    poses.WALK_SHEET = source("walk8")


def green_tint(a):
    """Yeşile çalan pikseller (saç ya da saç karışımı)."""
    hh, ss, vv = hsv_of(a)
    f = a[..., :3].astype(int)
    pale = (ss >= 0.04) & (f[..., 1] - np.maximum(f[..., 0], f[..., 2]) >= 6)  # JPEG'in soluk yeşil pusu
    # 40-65°: yanağın üstündeki ince tutamlarda yeşil+ten karışımı zeytin/haki olur (ten 5-35°, ayrı kalır)
    olive = (hh >= 40) & (hh < 65) & (ss >= 0.12)
    return (((hh >= 65) & (hh <= 170) & ((ss >= 0.10) | pale)) | olive) & (vv >= 0.08)


def green_dom(rgb):
    """Yeşil baskınlığı 0..1 (1: saf saç, gölgeli/koyu yeşil dahil)."""
    f = rgb.astype(float)
    dom = f[..., 1] - np.maximum(f[..., 0], f[..., 2])
    return np.clip(dom / np.maximum(f[..., 1], 1) / 0.6, 0, 1)


def pinkify(a):
    """Yeşil saçı orijinal pembeye çevirir (aynı açıklık): kurdele/kıyafet kuralları pembe saça göre ayarlı."""
    out = a.copy()
    t = green_tint(a)
    if t.any():
        import colorsys
        px = a[t][:, :3].astype(float) / 255
        res = []
        for r, g, b in px:
            h, l, s_ = colorsys.rgb_to_hls(r, g, b)
            res.append(colorsys.hls_to_rgb(345 / 360, l, min(1, s_ * 0.7)))
        out[t, :3] = (np.array(res) * 255).round().astype(np.uint8)
    return out


def face_span(rgb_or_rgba):
    """Yüz kutusu (x0, x1, alın y, çene y). Mavi irisler varsa göz hizasından: anime yüzünde çene göz hizasının
    ~1,25 göz-arası-mesafe altındadır. Yoksa ten bileşeninin üst %55'inin genişliği (boyun/göğüs teni hariç)."""
    a = rgb_or_rgba
    rgb = a[..., :3]
    vis = a[..., 3] > 0 if a.shape[2] == 4 else np.ones(a.shape[:2], bool)
    hh, ss, vv = hsv_of(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))
    skin = vis & (hh >= 5) & (hh <= 45) & (ss >= 0.08) & (ss <= 0.5) & (vv > 0.7)
    lab, n = label(skin)
    best, size = 0, 0
    for i in range(1, n + 1):
        ys = np.nonzero(lab == i)[0]
        if ys.min() < a.shape[0] * 0.45 and len(ys) > size:
            best, size = i, len(ys)
    if not best:
        return None
    comp = lab == best
    fy, fx = np.nonzero(comp)
    top = fy.min()
    eyes = blue_eyes(rgb)
    if eyes is not None and eyes[1][0] - eyes[0][0] > 8:
        d = eyes[1][0] - eyes[0][0]
        ey = (eyes[0][1] + eyes[1][1]) / 2
        rows = comp[int(ey - 0.2 * d):int(ey + 0.6 * d)]
        xs = np.nonzero(rows.any(axis=0))[0]
        x0, x1 = (xs.min(), xs.max()) if len(xs) else (eyes[0][0] - 0.6 * d, eyes[1][0] + 0.6 * d)
        return int(x0), int(x1), int(top), int(ey + 1.25 * d)
    # Göz yok: allık bandı yüz tenini alın/çene diye ikiye bölebiliyor; en büyük parçayla yatayda çakışan diğer
    # üst parçalar da yüzdür (eller değil). Genişlik birleşimin üst %60'ından, çene genişlikten.
    cx0, cx1 = fx.min(), fx.max()
    union = comp.copy()
    for i in range(1, n + 1):
        if i == best:
            continue
        ys_, xs_ = np.nonzero(lab == i)
        if len(ys_) >= 30 and ys_.min() < a.shape[0] * 0.6 and xs_.min() <= cx1 and xs_.max() >= cx0:
            union |= lab == i
    uy, ux = np.nonzero(union)
    top = uy.min()
    hgt = uy.max() - top
    rows = union[top:top + int(0.6 * hgt) + 1]
    xs = np.nonzero(rows.any(axis=0))[0]
    x0, x1 = xs.min(), xs.max()
    return int(x0), int(x1), int(top), int(min(uy.max(), top + 1.1 * (x1 - x0)))


def cutout(img):
    """RGBA: arka plan ve kapalı beyaz boşluklar saydam, kenar içe doğru yumuşak."""
    rgb = np.array(img.convert("RGB"))
    a = rgb.astype(int)
    h, w, _ = a.shape
    mn, mx = a.min(axis=2), a.max(axis=2)
    near = (mn >= 238) & (mx - mn <= 20)
    # alt kenar tohum değil: büstte gömlek alt kenara değiyor, taşma gömleğe girerdi
    seeds = [(0, x) for x in range(w)] + [(y, 0) for y in range(h)] + [(y, w - 1) for y in range(h)]
    bg = pixelize.flood(near, seeds)
    # kenara (alt/yan) değen açık renkli cepler: saç panel kenarına değince aradaki arka plan kapalı kalıyordu. Ortadaki
    # (gömlek, panelin altına değer) korunur; yanlardakiler arka plan.
    lab, n = label(near & ~bg)
    edge_ids = set(np.unique(np.concatenate([lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    for i in edge_ids:
        xs = np.nonzero(lab == i)[1]
        if not (0.3 * w <= xs.mean() <= 0.7 * w):
            bg |= lab == i
    hh, ss, vv = hsv_of(np.dstack([rgb, np.full((h, w), 255, np.uint8)]))
    eyes = box_count((hh >= 185) & (hh <= 270) & (ss >= 0.3) & (vv >= 0.45), 8) > 0  # parlak iris (lacivert hırka değil)
    # Kapalı açık renkli bölgeler: halkasına (3 px dışı, konturları atlar) bakılır. Halkası çoğunlukla saçsa saç arası
    # cep/boşluktur; küçük ve halkası koyuysa kol ile gövde arası boşluktur. Gömlek (büyük, halkası hırka/papyon/ten),
    # gömlek düğmesi/parlaması, burun parlaması (tenle çevrili) ve göz beyazı kalır.
    light = (mn >= 232) & (mx - mn <= 24) & ~bg
    hair = ((hh >= 300) | (hh <= 12)) & (ss >= 0.2) & (vv > 0.45)
    if GREEN:
        hair |= green_tint(np.dstack([rgb, np.full((h, w), 255, np.uint8)])) & (ss >= 0.2)
    skinring = (hh >= 5) & (hh <= 45) & (ss >= 0.08) & (vv > 0.7)
    lab, n = label(light)
    small = 0.02 * h * w
    for i in range(1, n + 1):
        m = lab == i
        k = int(m.sum())
        if k < 6 or (m & eyes).any():
            continue
        ring = (box_count(m, 3) > 0) & ~m & ~bg & ~light
        r = ring.sum()
        if not r or (ring & skinring).sum() >= 0.7 * r:
            continue
        if (ring & hair).sum() >= 0.35 * r or (80 <= k < small and (ring & (vv < 0.5)).sum() >= 0.6 * r):
            bg |= m
    # Saf beyaz (çizimde arka plan rengi) kümeler: açık gömlekle birleşip "gömlek" sayılabiliyordu (çene yanı beyaz
    # üçgen). Kendi başına bakılır: halkasının ≥%25'i saçsa arka plandır. Gömlek parlamaları gömlekle çevrili, kalır.
    pure = (mn >= 250) & (mx - mn <= 6) & ~bg
    plab, pn = label(pure)
    for i in range(1, pn + 1):
        m = plab == i
        if m.sum() < 4 or (m & eyes).any():
            continue
        ring = (box_count(m, 2) > 0) & ~m & ~bg & ~pure
        lightring = (ring & (mn >= 215)).sum()
        # saça değiyor ya da (çene yanı üçgeni gibi) çevresinin yarısından azı açık renk (gömlek değil)
        if ring.sum() and ((ring & hair).sum() >= 0.25 * ring.sum() or (m.sum() >= 30 and lightring < 0.5 * ring.sum())):
            bg |= m
    # Yüzün iki yanında (saç ile çene/boyun arasında) kalan açık renkli arka plan: yüz kutusu göz hizasından ölçülür
    # (boyun/göğüs teni yüzü geniş gösterip bu bölgeyi kaçırıyordu). Çene üstü: yanlardaki tüm açık pikseller;
    # çene altı (boyun hizası): çevresinde gömlekten çok saç olan açık pikseller (yaka kalır).
    fs = face_span(np.dstack([rgb, np.full((h, w), 255, np.uint8)]))
    if fs:
        fx0, fx1, ftop, chin = fs
        fw = fx1 - fx0
        yy, xx = np.mgrid[0:h, 0:w]
        side = ((xx < fx0) & (xx > fx0 - fw)) | ((xx > fx1) & (xx < fx1 + fw))
        bg |= light & (yy <= chin) & (yy >= ftop) & side
        hc, lc = box_count(hair, 5), box_count(light, 5)
        low = (yy > chin) & (yy <= chin + int(0.45 * fw)) & side
        bg |= light & low & (hc > 0.5 * lc)
    fg = ~bg
    for _ in range(2):
        fg &= ~(neighbors4(~fg) > 0)  # kenardaki beyazla karışmış 2 px
    soft = np.array(Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)))
    alpha = np.where(fg, soft, 0).astype(np.uint8)  # yalnız içe doğru yumuşar
    return np.dstack([rgb, alpha])


def shrink(rgba, scale):
    im = Image.fromarray(rgba, "RGBA").convert("RGBa")  # önceden çarpılmış alfa: kenarda renk kaçmaz
    w, h = round(im.width * scale), round(im.height * scale)
    out = np.array(im.resize((w, h), Image.LANCZOS).convert("RGBA"))
    out[out[..., 3] < 8] = 0
    ys, xs = np.nonzero(out[..., 3])
    return out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def group_map(a, face_hint=None):
    """Yeşil modda: kurdele/kıyafet/göz grupları pembeye çevrilmiş kopyadan (mevcut kurallar), saç yalnız yeşillikten.
    Kopyada silinen arka plan pikselleri (çene yanı beyaz cepler) asıl karede de silinir."""
    if not GREEN:
        return group_map_pink(a, face_hint)
    p = pinkify(a)
    g = group_map_pink(p, face_hint)
    a[p[..., 3] == 0] = 0
    t = green_tint(a) & (a[..., 3] > 0)
    g[(g == 1) & ~t] = 0
    g[t] = 1
    m = ACC_MASKS.get(a.shape[:2])
    if m is not None:
        g[(m > 100) & ~t] = 0  # aksesuar boyanmaz (kedi kulağı yeşil: saç olarak boyanır)
    return g


def group_map_pink(a, face_hint=None):
    """Renk grupları (poses.groups) + saça bitişik yarı saydam/pembe kenar pikselleri saça (koyu saçta pembe hale kalmasın).
    face_hint: yüz kutusu (x0, x1, alın, çene); aynı hizaya oturtulmuş büst karelerinde ana büstünki verilir
    (gözleri kapalı/kırpan karelerde yüz ölçümü güvenilmez)."""
    g = poses.groups(a)
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    pinkish = (hh >= 290) | (hh <= 20)
    for _ in range(3):
        add = vis & (g == 0) & (neighbors4(g == 1) >= 1) & (pinkish | (a[..., 3] < 200)) & (ss >= 0.08)
        if not add.any():
            break
        g[add] = 1
    # saçın açık parlamaları (pembe saçta beyaza yakın): çevresinin çoğu saç olan açık pikseller saçtır; yoksa koyu
    # saçta beyaz nokta/şerit gibi kalıyor. Yüz kutusu ve gözler hariç.
    ftop, chin, fx0, fx1 = poses.face_box(a)
    face = np.zeros_like(vis)
    face[ftop:chin + 1, fx0:fx1 + 1] = True
    for _ in range(3):
        hair_frac = box_count(g == 1, 2) / np.maximum(box_count(vis, 2), 1)
        add = vis & (g == 0) & ~face & (vv > 0.55) & (hair_frac >= 0.5)
        if not add.any():
            break
        g[add] = 1
    # yüzün orta-alt kısmında (burun, ağız, yanak) saç olmaz: pembe burun/ağız saç rengine boyanıp siyah nokta oluyordu
    ftop, chin, fx0, fx1 = poses.face_box(a)
    w = fx1 - fx0
    mid = np.zeros_like(vis)
    mid[ftop + (chin - ftop) * 45 // 100:chin + 1, fx0 + w // 4:fx1 - w // 4] = True
    g[mid & (g == 1)] = 0
    # Yüz alt yarısı (göz hizasından çeneye): her satırda yüz teninin en sol ile en sağ pikseli arası hiçbir zaman saç
    # değildir. Yanak kenarı gölgesi ve allık pembe olduğu için saç sayılıp saç rengine boyanıyordu (yüzde mor leke).
    skin = vis & (hh >= 5) & (hh <= 45) & (ss >= 0.08) & (ss <= 0.5) & (vv > 0.7)
    lab, n = label(skin)
    best, size = 0, 0
    for i in range(1, n + 1):
        ys_ = np.nonzero(lab == i)[0]
        if ys_.min() < a.shape[0] * 0.45 and len(ys_) > size:
            best, size = i, len(ys_)
    if best:
        comp = lab == best
        fy, fx = np.nonzero(comp)
        top, fw = fy.min(), fx.max() - fx.min()
        eyes = blue_eyes(a[..., :3])
        ey = int(min(e[1] for e in eyes)) if eyes else int(top + 0.35 * fw)
        chin_y = min(fy.max(), int(top + 1.1 * fw))
        if face_hint:
            ey = face_hint[2] + int(0.35 * (face_hint[1] - face_hint[0]))
            chin_y = face_hint[3]
        for y in range(ey, chin_y + 1):
            xs_ = np.nonzero(comp[y])[0]
            if len(xs_):
                row = g[y, xs_.min():xs_.max() + 1]
                row[row == 1] = 0
    # Tutamların koyu gölge kenarları: saça bitişik koyu pembe-kahve pikseller saçtır (sayılmayınca orijinal renginde
    # kalıp lacivert saçın yanında siyah şerit gibi görünüyordu). 3 tur büyür; göz ve ten hariç.
    hh, ss, vv = hsv_of(a)
    darkpink = vis & ((hh >= 290) | (hh <= 20)) & (ss >= 0.25) & (vv < 0.62) & (g != 2) & ~skin
    for _ in range(3):
        add = darkpink & (g != 1) & (box_count(g == 1, 1) > 0)
        if not add.any():
            break
        g[add] = 1
    # Kâkül uçları ve göz köşesindeki tutamlar: ana saç kütlesinden 4-komşulukla pembe pikseller üzerinden uzanan
    # bölgeler saçtır (yüz içindeki küçük parçalar ağız/allık sanılıp pembe kalıyordu). Göz hizasının biraz altına kadar;
    # yanak allığı daha aşağıda kalır.
    fs0 = face_hint or face_span(a)
    if fs0:
        eyes = blue_eyes(a[..., :3])
        if eyes:
            d = eyes[1][0] - eyes[0][0]
            ylim = (eyes[0][1] + eyes[1][1]) / 2 + 0.3 * d
        else:
            ylim = fs0[2] + 0.55 * (fs0[1] - fs0[0])
        yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        pink = vis & ((hh >= 290) | (hh <= 15)) & (ss >= 0.15) & (vv > 0.4) & (g != 2) & ~skin & (yy < ylim)
        for _ in range(40):
            add = pink & (g != 1) & (neighbors4(g == 1) > 0)
            if not add.any():
                break
            g[add] = 1
    # Kâkül-alın ve tutam-yanak sınırındaki karışım pikselleri (pembe+ten; tenden daha doygun): saça bitişikse saçtır.
    # Allığı korumak için yalnız göz hizasının biraz üstüne kadar ya da yüzün yan şeritlerinde.
    if fs0:
        fx0_, fx1_ = fs0[0], fs0[1]
        fw_ = fx1_ - fx0_
        ylim2 = ylim - 0.05 * (eyes[1][0] - eyes[0][0]) if eyes else fs0[2] + 0.45 * fw_
        mix = vis & ((hh >= 330) | (hh <= 22)) & (ss >= 0.3) & (vv > 0.6) & (g != 2)
        zone = (yy < ylim2) | (xx < fx0_ + 0.1 * fw_) | (xx > fx1_ - 0.1 * fw_)
        for _ in range(2):
            add = mix & zone & (g != 1) & (neighbors4(g == 1) > 0)
            if not add.any():
                break
            g[add] = 1
    # Saçla çevrili (8 komşudan ≥5'i saç) pembemsi ten tonundaki kıymıklar: kâkül/tutam kenarındaki karışım
    # pikselleridir (doygunluk 0,2-0,3; tenden ancak biraz pembe). Allık tenle çevrilidir, etkilenmez.
    for _ in range(2):
        n8 = box_count(g == 1, 1) - (g == 1)
        sliver = vis & (g != 1) & (g != 2) & ((hh >= 330) | (hh <= 25)) & (ss >= 0.15) & (vv > 0.5) & (n8 >= 5)
        if not sliver.any():
            break
        g[sliver] = 1
    # Çene/yanak konturu: çizimin çizgisi pembe-kahve olduğu için saç sayılıp saç rengine boyanıyordu (yüzde koyu
    # çizgi). Göz hizasından çene altına kadar, tene 2 px komşu saç-grubu pikselleri orijinal renginde kalır.
    fs = face_hint or face_span(a)
    if fs:
        fx0, fx1, ftop, chin = fs
        fw = fx1 - fx0
        near_skin = box_count(skin, 2) > 0
        yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        band = (yy >= ftop + int(0.3 * fw)) & (yy <= chin + int(0.35 * fw)) & (xx >= fx0 - 4) & (xx <= fx1 + 4)
        g[band & near_skin & (g == 1) & (vv < 0.72)] = 0  # yalnız koyu çizgi; parlak saç tutamı saç kalır
        # Kâküller: göz hizasının üstünde, yüz kutusunun içindeki pembe parçalar saçtır (çizgilerle bölünmüş küçük
        # uçlar "ağız/allık" sanılıp pembe kalıyordu). Kaşlar da saç rengindedir.
        eyes = blue_eyes(a[..., :3])
        ey = (eyes[0][1] + eyes[1][1]) / 2 - 0.3 * (eyes[1][0] - eyes[0][0]) if eyes else ftop + 0.28 * fw
        pink = vis & ((hh >= 290) | (hh <= 15)) & (ss >= 0.12) & (vv > 0.4)
        g[(yy < ey) & (xx >= fx0 - 6) & (xx <= fx1 + 6) & pink & (g == 0)] = 1
        # Fiyonkun gruba girmemiş siyah lobları: başta, kurdeleye komşu nötr-koyu pikseller kurdeledir (yoksa kurdele
        # rengi değişince yanında simsiyah parça kalıyor)
        dark = vis & (vv < 0.3) & (ss < 0.4) & (yy < chin) & (g != 2)
        for _ in range(16):
            add = dark & (g != 4) & (box_count(g == 4, 1) > 0)
            if not add.any():
                break
            g[add] = 4
    # Son temizlik: yüz kutusu dışındaki küçük (≤60 px) açık renkli kırıntılar (gömlek ve yaka büyük bölgedir, kalır).
    # Saydamlığa değiyorsa silinir (a yerinde değişir), saçın içindeyse saça katılır (koyu saçta beyaz nokta kalmasın).
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    light = vis & (vv > 0.8) & (ss < 0.22) & (g == 0) & ~face
    lab, n = label(light)
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() > 60:
            continue
        ring = (neighbors4(m) > 0) & ~m
        if (ring & ~vis).any():
            a[m] = 0
        elif (ring & (g == 1)).sum() >= 0.3 * ring.sum():
            g[m] = 1
    # Saç ile çene/boyun arasında kalan beyaz arka plan parçaları: beyaz bölgenin 3 px dışındaki halkası hem saç (≥%20)
    # hem ten (≥%10) içeriyorsa arka plandır → saydam. Yaka saça neredeyse değmez, gömlek tene değmez, göz beyazı ve
    # dişlerin çevresinde saç yoktur; onlar kalır. (Ölçüm: uykulu karede çene solu 244 px saç%34 ten%22; yaka saç%7.)
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    skin = vis & (hh >= 5) & (hh <= 45) & (ss >= 0.08) & (ss <= 0.5) & (vv > 0.7)
    white = vis & (a[..., :3].min(axis=2) >= 232)
    lab, n = label(white)
    for i in range(1, n + 1):
        m = lab == i
        if m.sum() < 10:
            continue
        ring = (box_count(m, 3) > 0) & ~m & vis & ~white
        r = max(int(ring.sum()), 1)
        if (ring & (g == 2)).sum() >= 0.15 * r:  # göz parıltısı ve göz akı silinmez (irisle çevrili)
            continue
        if (ring & (g == 1)).sum() >= 0.2 * r and (ring & skin).sum() >= 0.1 * r:
            a[m] = 0
    g[a[..., 3] == 0] = 0
    return g


def defringe(a):
    """Saydamlığa değen açık/gri kenar pikselleri (beyaz zeminden kalan karışım) silinir."""
    for _ in range(2):
        hh, ss, vv = hsv_of(a)
        vis = a[..., 3] > 0
        edge = vis & (vv > 0.6) & (ss < 0.25) & (neighbors4(~vis) > 0)
        if not edge.any():
            break
        a[edge] = 0
    return a


def save(name, a):
    a = defringe(a)
    g = group_map(a)
    Image.fromarray(a, "RGBA").save(os.path.join(HERE, "out", f"pose_k1_{name}.png"))
    Image.fromarray(g, "L").save(os.path.join(HERE, "out", f"pose_k1_{name}_groups.png"))
    print(name, a.shape[1], "x", a.shape[0])


BW, BH = 256, 256  # masaüstü büst tuvali (el sallayan el sığsın diye eski 192'den geniş)
EXPR_SHEET = source("ifade1")  # 2×2: el sallama, el sallama (gözler kapalı), gülme, şaşırma
EXPR_SHEET2 = source("ifade2")  # Gemini 2×2: utangaç, üzgün, uykulu, kızgın
# Gemini 3×2: uykulu (yeniden), mutlu, göz kırpma, sevgi, gururlu, düşünceli
EXPR_SHEET3 = source("ifade3")
SHEET3_KEYS = [["uykulu", "mutlu", "goz_kirp"], ["sevgi", "gurur", "dusunce"]]


def grid_panels(path, rows, cols):
    """Izgarayı eşit böler; her panel kenarındaki çizgi için 6 px kırpılır, sonra içeriğe (mürekkep kutusu) kırpılır."""
    im = Image.open(path).convert("RGB")
    out = []
    for r in range(rows):
        row = []
        for c in range(cols):
            p = im.crop((c * im.width // cols + 6, r * im.height // rows + 6, (c + 1) * im.width // cols - 6, (r + 1) * im.height // rows - 6))
            ink = np.array(p).min(axis=2) < 225
            ys, xs = np.nonzero(ink)
            row.append(p.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)))
        out.append(row)
    return out


def skin_anchor(img):
    """Yüz (üst yarıdaki en büyük ten bölgesi): (orta x, alın y), genişlik. Bir gözü kapalı panelleri hizalamak için."""
    rgb = np.array(img.convert("RGB"))
    hh, ss, vv = hsv_of(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))
    skin = (hh >= 5) & (hh <= 45) & (ss >= 0.1) & (ss <= 0.5) & (vv > 0.7)
    lab, n = label(skin)
    best, size = 0, 0
    for i in range(1, n + 1):
        ys = np.nonzero(lab == i)[0]
        if ys.min() < rgb.shape[0] * 0.45 and len(ys) > size:
            best, size = i, len(ys)
    ys, xs = np.nonzero(lab == best)
    return ((xs.min() + xs.max()) / 2, ys.min()), xs.max() - xs.min()


def blue_eyes(rgb):
    """İki gözün merkezleri (en büyük iki mavi bölge), soldan sağa; bulunamazsa None."""
    hh, ss, vv = hsv_of(np.dstack([rgb, np.full(rgb.shape[:2], 255, np.uint8)]))
    lab, n = label((hh >= 185) & (hh <= 270) & (ss >= 0.35) & (vv >= 0.45))  # parlak iris; lacivert hırka değil
    if n < 2:
        return None
    sizes = np.bincount(lab.ravel())[1:]
    top2 = np.argsort(-sizes)[:2]
    if sizes[top2[1]] < 0.3 * sizes[top2[0]]:
        return None  # tek göz (göz kırpma) ya da iris + rastgele mavi parça
    pts = []
    for i in top2 + 1:
        ys, xs = np.nonzero(lab == i)
        pts.append((xs.mean(), ys.mean()))
    pts.sort()
    d = pts[1][0] - pts[0][0]
    w = rgb.shape[1]
    if not (0.08 * w <= d <= 0.45 * w) or abs(pts[1][1] - pts[0][1]) > 0.5 * d:
        return None
    return pts


SD_DIR = os.path.join(HERE, "src", "poses", "sd")  # Stable Diffusion / iris kaydırma ile yalnız göz ya da ağzı değişmiş büstler


def sd_variant(name, panel="bust"):
    """Yeşil sayfanın bir panelinin yalnız gözü/kaşı/ağzı değişmiş hâli (src/poses/sd/<ad>.png, sayfanın o panelin
    çeyreği: büst sol üst, stand sağ üst, sit sağ alt). Sayfaya geri yapıştırılıp aynı panel kesiminden geçer: maskenin
    dışı aynı olduğu için kareler birebir hizalı çıkar."""
    f = os.path.join(SD_DIR, name + ".png")
    if not GREEN or not os.path.exists(f):
        return None
    sheet = Image.open(source("sheet")).convert("RGB")
    w, h = sheet.width // 2, sheet.height // 2
    sheet.paste(Image.open(f).convert("RGB"), {"bust": (0, 0), "stand": (w, 0), "walk": (0, h), "sit": (w, h)}[panel])
    return poses.panels(sheet)[panel]


def graft(a, base, other, grow=2):
    """other'ın base'ten farklı olan bölgesi (göz ya da ağız yaması) a'ya taşınır: ifadenin kendi kaşı/ağzı kalır."""
    m = diff_mask(base, other, grow)[..., None]
    out = a.copy()
    out[..., :3] = (a[..., :3] * (1 - m) + other[..., :3] * m).round().astype(np.uint8)
    return out


def diff_mask(a, b, grow=2, blur=1.2):
    """İki hizalı kare arasında değişen bölge: yumuşak maske 0..1 (ağız/göz yamasını başka kareye taşımak için)."""
    from PIL import ImageFilter
    m = (np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).max(-1) > 10) & (a[..., 3] > 0)
    im = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * grow + 1)).filter(ImageFilter.GaussianBlur(blur))
    return np.array(im) / 255.0


def placed(img, scale, mid, target):
    """Çizimi scale ile küçültüp göz ortası (mid, kaynak pikseli) target'a gelecek şekilde BW×BH tuvale koyar."""
    rgba = cutout(img)
    im = Image.fromarray(rgba, "RGBA").convert("RGBa")
    w, h = round(im.width * scale), round(im.height * scale)
    small = np.array(im.resize((w, h), Image.LANCZOS).convert("RGBA"))
    small[small[..., 3] < 8] = 0
    out = np.zeros((BH, BW, 4), np.uint8)
    ox, oy = int(round(target[0] - mid[0] * scale)), int(round(target[1] - mid[1] * scale))
    x0, y0 = max(ox, 0), max(oy, 0)
    x1, y1 = min(ox + w, BW), min(oy + h, BH)
    out[y0:y1, x0:x1] = small[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    out = defringe(out)
    if aksesuar.AKS:
        e = blue_eyes(out[..., :3])
        if BUST_EYES is not None:
            d0 = BUST_EYES[1][0] - BUST_EYES[0][0]
            if e is None or abs((e[1][0] - e[0][0]) - d0) > 0.15 * d0 or abs(e[0][1] - BUST_EYES[0][1]) > 0.3 * d0:
                e = BUST_EYES
        out, m = aksesuar.wear(out, e)
        if BUST_EYES is None or e is BUST_EYES:
            ACC_MASKS[out.shape[:2]] = m
    return out


def transplant_eyes(base, closed):
    """Göz kırpma karesi: kapalı gözlü çizimin göz bölgesi (hizalanmış) büstün gözlerinin üstüne yumuşak geçişle konur."""
    eyes = blue_eyes(base[..., :3])
    out = base.copy()
    if eyes is None:
        return out
    hh, ss, vv = hsv_of(base)
    blue = (hh >= 185) & (hh <= 270) & (ss >= 0.35) & (vv >= 0.3)
    yy, xx = np.mgrid[0:BH, 0:BW]
    mask = np.zeros((BH, BW))
    for cx, cy in eyes:
        near = blue & (abs(xx - cx) < 25) & (abs(yy - cy) < 25)
        ys, xs = np.nonzero(near)
        rx, ry = (xs.max() - xs.min()) / 2 + 6, (ys.max() - ys.min()) / 2 + 6
        d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
        mask = np.maximum(mask, np.clip((1.3 - d) / 0.5, 0, 1))  # kenarda yumuşak
    m = (mask[..., None] * (closed[..., 3:] > 0)).astype(float)
    out[..., :3] = (out[..., :3] * (1 - m) + closed[..., :3] * m).astype(np.uint8)
    return out


def hand_wave(a, frames=20):
    """El sallama: büstün solundaki (yüzün solunda) el bilekten ±derece döner; elin açtığı yer komşu piksellerle dolar."""
    import animate
    hh, ss, vv = hsv_of(a)
    vis = a[..., 3] > 0
    skin = vis & (hh >= 5) & (hh <= 45) & (ss >= 0.1) & (ss <= 0.5) & (vv > 0.6)
    ftop, chin, fx0, fx1 = poses.face_box(a)
    lab, n = label(skin)
    best, size = 0, 0
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if xs.mean() < fx0 and len(ys) > size:
            best, size = i, len(ys)
    if not best:
        return [a] * frames
    hand = box_count(lab == best, 2) > 0
    hand &= vis
    ys, xs = np.nonzero(lab == best)
    bottom = ys.max()
    pivot = (xs[ys >= bottom - 3].mean(), bottom)
    plate = animate.inpaint(a, hand)
    layer = np.where(hand[..., None], a, 0).astype(np.uint8)
    angles = [0, 7, 13, 16, 13, 7, 0, -5, -8, -5, 0, 7, 13, 16, 13, 7, 0, -5, -8, -5][:frames]
    out = []
    for ang in angles:
        lay, lm = poses.rotate(layer, hand, pivot, ang)
        f = plate.copy()
        f[lm] = lay[lm]
        out.append(f)
    return out


def write_set(d, name, frame, g):
    os.makedirs(os.path.join(d, "groups"), exist_ok=True)
    Image.fromarray(frame, "RGBA").save(os.path.join(d, name))
    gg = g.copy()
    gg[frame[..., 3] == 0] = 0
    Image.fromarray(np.stack([gg, gg, gg], -1), "RGB").save(os.path.join(d, "groups", name))


def desktop_bust(sheet_bust):
    """Masaüstü büstü + ifadeler: frames/yeni (idle_, talk_, wave_, emotes/<ifade>/)."""
    import emotes
    d = os.path.join(HERE, "frames", LOOK)
    src = np.array(sheet_bust.convert("RGB"))
    e0 = blue_eyes(src)
    s0 = poses.BUST[0] / sheet_bust.width * poses.BUST_ZOOM
    mid0 = ((e0[0][0] + e0[1][0]) / 2, (e0[0][1] + e0[1][1]) / 2)
    dist0 = e0[1][0] - e0[0][0]
    target = (BW / 2 + (mid0[0] - sheet_bust.width / 2) * s0, 4 + mid0[1] * s0)
    if aksesuar.AKS:
        # şapka/kulak başın üstüne çıkar: büst o kadar aşağı iner (saç tuvalin tepesine değiyordu)
        dy = math.ceil(max(0.0, aksesuar.top_reach(aksesuar.AKS, dist0 * s0) - target[1] + 3))
        target = (target[0], target[1] + dy)
    base = placed(sheet_bust, s0, mid0, target)
    global BUST_EYES
    BUST_EYES = blue_eyes(base[..., :3])
    hint = face_span(base)
    gb = group_map(base, hint)
    Image.fromarray(base, "RGBA").save(os.path.join(HERE, "out", "pose_k1_bust.png"))
    Image.fromarray(gb, "L").save(os.path.join(HERE, "out", "pose_k1_bust_groups.png"))
    face, _ = poses.face_of(base, gb, "bust")
    blink = None
    waves = {}
    if os.path.exists(EXPR_SHEET):
        # panel kenarındaki ince gri çizgi arka plan temizliğini durduruyor (saç yanında beyaz parçalar kalıyordu): 6 px kırp
        trim = lambda im: im.crop((6, 6, im.width - 6, im.height - 6))
        ps = {k: trim(v) for k, v in poses.panels(Image.open(EXPR_SHEET).convert("RGB")).items()}
        p1, p2 = ps["bust"], ps["stand"]
        def fit(p_eyes_from, p):
            e = blue_eyes(np.array(p_eyes_from.convert("RGB")))
            mid = ((e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2)
            return placed(p, s0 * dist0 / (e[1][0] - e[0][0]), mid, target)
        wave_open, wave_closed = fit(p1, p1), fit(p1, p2)
        w_open, w_closed = hand_wave(wave_open), hand_wave(wave_closed)
        # el sallarken arada sevinçle gözlerini kapatır (5.-10. kareler)
        waves["default"] = [w_closed[i] if 5 <= i <= 10 else w_open[i] for i in range(20)]
        waves["nese"] = w_closed
        for k in ("default", "nese"):
            waves[k] = [(f, group_map(f, hint)) for f in waves[k]]
    # Stable Diffusion parçaları: kapalı göz (göz kırpma), yana bakış (emotes/bak_sol|bak_sag), konuşma ağızları
    var = {}
    for nm in ("goz_kapali", "bak_sol", "bak_sag", "agiz_kapali", "agiz_o", "agiz_genis"):
        v = sd_variant(nm)
        if v is not None:
            var[nm] = placed(v, s0, mid0, target)
    if "goz_kapali" in var:
        closed = var["goz_kapali"]
        blink = {20: (closed, group_map(closed, hint)), 21: (closed, group_map(closed, hint))}
    mouths = None
    if all(k in var for k in ("agiz_kapali", "agiz_o", "agiz_genis")):
        shapes = {"k": var["agiz_kapali"], "o": var["agiz_o"], "g": var["agiz_genis"], "a": base}
        mm = np.maximum.reduce([diff_mask(base, shapes[k]) for k in "kog"])
        mouths = (shapes, mm)
    poses.emit_pose("bust", base, gb, face, d, plain=True, blink=blink, mouths=mouths)
    for side in ("bak_sol", "bak_sag"):
        if side in var:
            v = var[side]
            poses.emit_pose("bust", v, group_map(v, hint), face, os.path.join(d, "emotes", side), plain=True)
    # İfadeler tek yüzden: src/poses/sd/ifade_<ad>.png (aynı büstün yalnız kaşı/gözü/ağzı/allığı SD ile değişmiş hâli),
    # böylece ifade değişince yüz zıplamaz. Göz kırpma ve konuşma ağzı ifadenin kendi karesine taşınır.
    lower = (np.mgrid[0:BH, 0:BW][0] > target[1] + 0.45 * dist0 * s0).astype(float)  # gözlerin altı (ağız)
    for e in emotes.EMOTES:
        a, g, bl, mo = base, gb, blink, mouths
        v = sd_variant("ifade_" + e)
        if v is not None:
            a = placed(v, s0, mid0, target)
            g = group_map(a, hint)
            if blink:
                bl = {k: graft(a, base, bi) for k, (bi, _) in blink.items()}
                bl = {k: (f, group_map(f, hint)) for k, f in bl.items()}
            if mouths:
                shapes, mm = mouths
                # ifadenin kendi ağzı da konuşma maskesine girer (çizilen ağız şeklinin dışında kalmasın)
                mo = (dict(shapes, a=a), np.maximum(mm, diff_mask(base, a) * lower))
        poses.emit_pose("bust", a, g, face, os.path.join(d, "emotes", e), e, plain=True, blink=bl, mouths=mo)
    for k, fr in waves.items():
        dirs = ([d] if k == "default" else []) + [os.path.join(d, "emotes", e) for e in emotes.EMOTES if (e == "nese") == (k == "nese")]
        for dd in dirs:
            for i, (f, g) in enumerate(fr):
                write_set(dd, f"wave_{i:02d}.png", f, g)
    print("büst", BW, "x", BH, "ifade sayfası:", os.path.exists(EXPR_SHEET))


def main():
    ps = poses.panels(Image.open(source("sheet")).convert("RGB"))
    full = poses.STAND_H / ps["stand"].height
    for name, img in ps.items():
        if name != "bust":
            a = shrink(cutout(img), full)
            if aksesuar.AKS and name in ("stand", "sit"):
                a = acc_pose(name, a)
            save(name, a)
    if os.path.exists(poses.WALK_SHEET):
        frames = poses.walk_sheet_frames()
        mh = sorted(f.height for f in frames)[len(frames) // 2]
        for i, f in enumerate(frames):
            save(f"wk{i}", shrink(cutout(f), full * ps["walk"].height / mh))
    desktop_bust(ps["bust"])
    poses.animate_poses(LOOK, walk=False, extra={nm: full_extras(nm, full) for nm in ("stand", "sit")})
    sit_emotes(full)
    poses.walk_frames(LOOK)
    if aksesuar.AKS in aksesuar.WALK:
        acc_walk(os.path.join(HERE, "frames", LOOK))
    final_edges(os.path.join(HERE, "frames", LOOK))
    if GREEN:
        green_finalize(os.path.join(HERE, "frames", LOOK))
    # Yerel piksel düzeltmeleri (fixes.json, sakura-piksel skill'i; pembe saç sınıflandırması içindi, yeşil modda yok)
    fix = os.path.join(os.path.expanduser("~"), ".claude", "skills", "sakura-piksel", "scripts")
    if not GREEN and os.path.exists(os.path.join(HERE, "fixes.json")) and os.path.isdir(fix):
        import sys
        sys.path.insert(0, fix)
        import sp_fix
        sp_fix.run()


def acc_pose(name, a):
    """Tam boy poza aksesuar: gözler bulunur, gerekirse üste pay eklenir (şapka/kulak sığsın)."""
    e = aksesuar.eyes_any(a)
    if e is None:
        print(name, "aksesuar: gözler bulunamadı, takılmadı")
        return a
    d = math.hypot(e[1][0] - e[0][0], e[1][1] - e[0][1])
    my = (e[0][1] + e[1][1]) / 2
    if name == "stand":
        # yürüme kareleri için baş ölçüsü: göz ortasının saç tepesine uzaklığı (d cinsinden)
        cols = slice(max(0, int(e[0][0] - d)), int(e[1][0] + d))
        top = int(np.nonzero(a[:, cols, 3].any(axis=1))[0].min())
        POSE_ACC["stand_ref"] = (d, (my - top) / d)
    pad = math.ceil(max(0.0, aksesuar.top_reach(aksesuar.AKS, d) - my + 2))
    a = aksesuar.pad_top(a, pad)
    e = [(x, y + pad) for x, y in e]
    a, m = aksesuar.wear(a, e)
    ACC_MASKS[a.shape[:2]] = m
    POSE_ACC[name] = (pad, e)
    print(name, "aksesuar:", aksesuar.AKS, "pay", pad)
    return a


# yürürken sanal göz ortası baş merkezine göre (d cinsinden) ve aynalama (berenin sarkık ucu geriye düşsün)
_WALK = {"bere": (-0.3, 0.2, True), "kedi": (0.05, 0.2, False)}.get(aksesuar.AKS, (0.0, 0.2, False))
WALK_DX = float(os.environ.get("WALK_DX", _WALK[0]))
WALK_DY = float(os.environ.get("WALK_DY", _WALK[1]))
WALK_FLIP = os.environ.get("WALK_FLIP", "1" if _WALK[2] else "0") == "1"


def acc_walk(d):
    """Yürüme kareleri yandan: gözler yerine baş tepesi ve yüz önünden sanal göz çizgisi kurulur (ayakta pozun baş
    ölçüsüyle); hepsine aynı üst pay eklenir, ayak hizası değişmez."""
    import glob
    if "stand_ref" not in POSE_ACC:
        return
    dv, ctop = POSE_ACC["stand_ref"]
    files = sorted(glob.glob(os.path.join(d, "walk_*.png")))
    reach = aksesuar.top_reach(aksesuar.AKS, dv)
    items = []
    for f in files:
        a = np.array(Image.open(f).convert("RGBA"))
        h = a.shape[0]
        band = a[int(h * 0.08):int(h * 0.20), :, 3] > 0
        ax = int(np.nonzero(band.any(axis=0))[0].max())  # yüz profili (en öndeki piksel)
        cols = slice(max(0, int(ax - 2.4 * dv)), ax + 1)
        top = int(np.nonzero(a[:, cols, 3].any(axis=1))[0].min())
        row = a[int(top + 0.3 * dv):int(top + 0.7 * dv), cols, 3].any(axis=0)
        xs = np.nonzero(row)[0] + cols.start
        xc = (xs.min() + xs.max()) / 2 if len(xs) else ax - 1.2 * dv
        my = top + ctop * dv
        cx, my = xc + WALK_DX * dv, my + WALK_DY * dv
        items.append((f, a, [(cx - dv / 2, my), (cx + dv / 2, my)]))
    pad = math.ceil(max(0.0, max(reach - e[0][1] for _, _, e in items) + 2))
    for f, a, e in items:
        a0 = aksesuar.pad_top(a, pad)
        e = [(x, y + pad) for x, y in e]
        a, m = aksesuar.wear(a0, e, flip=WALK_FLIP)
        gp = os.path.join(d, "groups", os.path.basename(f))
        g0 = aksesuar.pad_top(np.array(Image.open(gp).convert("RGB")), pad)
        g = g0.copy()
        g[m > 100] = 0
        Image.fromarray(a, "RGBA").save(f)
        Image.fromarray(g, "RGB").save(gp)
        if WALK_FLIP:
            # sola yürüme (walkl_): uygulama sağa yürümeyi aynalardı, beredeki ay-yıldız ters dönüyordu; aynalanmış
            # gövdeye katman aynasız takılır (sarkık uç yine geride, amblem düz)
            w = a0.shape[1]
            em = [(w - 1 - x, y) for x, y in reversed(e)]
            al, ml = aksesuar.wear(np.ascontiguousarray(a0[:, ::-1]), em)
            gl = np.ascontiguousarray(g0[:, ::-1])
            gl[ml > 100] = 0
            fl = os.path.join(d, os.path.basename(f).replace("walk_", "walkl_"))
            Image.fromarray(al, "RGBA").save(fl)
            Image.fromarray(gl, "RGB").save(os.path.join(d, "groups", os.path.basename(fl)))
    print("yürüme aksesuar:", len(items), "kare, pay", pad)


def full_extras(name, full):
    """Tam boy poz (stand/sit) için göz kırpma ve konuşma ağzı, büstteki gibi: src/poses/sd/<poz>_goz_kapali.png,
    <poz>_agiz_kapali|o|genis.png (sayfanın o panelinin çeyreği). Aynı kesim ve küçültmeden geçer, kare birebir hizalı."""
    base = np.array(Image.open(os.path.join(HERE, "out", f"pose_k1_{name}.png")).convert("RGBA"))
    var = {}
    for nm in ("goz_kapali", "agiz_kapali", "agiz_o", "agiz_genis"):
        v = sd_variant(f"{name}_{nm}", name)
        if v is not None:
            var[nm] = defringe(shrink(cutout(v), full))
            if name in POSE_ACC:
                pad, e = POSE_ACC[name]
                var[nm] = aksesuar.wear(aksesuar.pad_top(var[nm], pad), e)[0]
            if var[nm].shape != base.shape:
                print(name, nm, "boyut tutmadı, atlandı")
                del var[nm]
    kw = {}
    if "goz_kapali" in var:
        c = var["goz_kapali"]
        kw["blink"] = {20: (c, group_map(c)), 21: (c, group_map(c))}
    if all(k in var for k in ("agiz_kapali", "agiz_o", "agiz_genis")):
        shapes = {"k": var["agiz_kapali"], "o": var["agiz_o"], "g": var["agiz_genis"], "a": base}
        kw["mouths"] = (shapes, np.maximum.reduce([diff_mask(base, shapes[k], 1, 0.8) for k in "kog"]))
    print(name, "SD parçaları:", sorted(var))
    return kw


def sit_emotes(full):
    """Oturma pozunun ifadeleri: src/poses/sd/sit_ifade_<ad>.png (büst ifadesinin yüzü pozun yüzüne taşınmış hâli,
    sakura-araclar/scripts/tam_boy_ifade.py) → frames/<görünüm>/emotes/<ad>/sit-idle_|sit-talk_. Göz kırpma ve konuşma
    ağzı büstteki gibi ifadenin kendi karesine biner. Ayakta poz ifadesiz kalır (yüzü küçük, taşınınca bulanıktı)."""
    import emotes
    d = os.path.join(HERE, "frames", LOOK)
    base = np.array(Image.open(os.path.join(HERE, "out", "pose_k1_sit.png")).convert("RGBA"))
    gb = np.array(Image.open(os.path.join(HERE, "out", "pose_k1_sit_groups.png")))
    face, _ = poses.face_of(base, gb, "sit")
    kw = full_extras("sit", full)
    eyes = aksesuar.eyes_any(base)
    ed = eyes[1][0] - eyes[0][0] if eyes else base.shape[1] * 0.15
    ey = (eyes[0][1] + eyes[1][1]) / 2 if eyes else base.shape[0] * 0.2
    lower = (np.mgrid[0:base.shape[0], 0:base.shape[1]][0] > ey + 0.45 * ed).astype(float)  # gözlerin altı (ağız)
    n = 0
    for e in emotes.EMOTES:
        v = sd_variant("sit_ifade_" + e, "sit")
        if v is None:
            continue
        a = defringe(shrink(cutout(v), full))
        if "sit" in POSE_ACC:
            pad, pe = POSE_ACC["sit"]
            a = aksesuar.wear(aksesuar.pad_top(a, pad), pe)[0]
        if a.shape != base.shape:
            print("sit", e, "boyut tutmadı, atlandı")
            continue
        bl = mo = None
        if kw.get("blink"):
            bl = {k: graft(a, base, bi) for k, (bi, _) in kw["blink"].items()}
            bl = {k: (f, group_map(f)) for k, f in bl.items()}
        if kw.get("mouths"):
            shapes, mm = kw["mouths"]
            mo = (dict(shapes, a=a), np.maximum(mm, diff_mask(base, a, 1, 0.8) * lower))
        poses.emit_pose("sit", a, group_map(a), face, os.path.join(d, "emotes", e), e, blink=bl, mouths=mo)
        n += 1
    print("oturma ifadeleri:", n)


def final_edges(d):
    """Son geçiş, üretilen her karede: silüet kenarının 2 px içindeki açık gri/beyaz pikseller (el döndürme, yürüme
    birleştirmesi gibi adımlardan sonra kalan beyaz zemin karışımı) saydam yapılır."""
    import glob
    n = 0
    for f in glob.glob(os.path.join(d, "**", "*.png"), recursive=True):
        if os.sep + "groups" + os.sep in f:
            continue
        a = np.array(Image.open(f).convert("RGBA"))
        changed = False
        for _ in range(2):
            vis = a[..., 3] > 0
            hh, ss, vv = hsv_of(a)
            light = vis & (vv > 0.8) & (ss < 0.2)
            skin = (hh >= 5) & (hh <= 45) & (ss >= 0.07)
            # yalnız ince saçak: çevresi (5×5) çoğunlukla açık olmayan (saç, hırka) — gömlek ve el içi korunur
            lf = box_count(light, 2) / np.maximum(box_count(vis, 2), 1)
            m = light & ~skin & (lf < 0.45) & (box_count(~vis, 2) > 0)
            if not m.any():
                break
            a[m] = 0
            changed = True
        # minik açık kırıntılar (≤8 px): saydamlığa değiyorsa ya da çevresinin çoğu saçsa (yaka ucu, boyun kenarı)
        vis = a[..., 3] > 0
        hh, ss, vv = hsv_of(a)
        light = vis & (vv > 0.8) & (ss < 0.25)
        hairish = vis & ~light & (vv < 0.6)
        lab, k = label(light)
        sizes = np.bincount(lab.ravel())
        for i in range(1, k + 1):
            if sizes[i] > 8:
                continue
            m = lab == i
            ring = (neighbors4(m) > 0) & ~m
            if (ring & ~vis).any() or (ring & hairish).sum() >= 0.5 * max(int((ring & vis).sum()), 1):
                a[m] = 0
                changed = True
        if changed:
            Image.fromarray(a, "RGBA").save(f)
            n += 1
    print("kenar temizliği:", n, "kare")


# Varsayılan saç rengi (renk seçilmemişken görünen pembe): P(s) = HLS(PINK_H, min(1, s·PINK_GAIN), PINK_S).
# s = saçın yeşil kopyadaki HLS açıklığı. Sakura.cs (HairPink) ve sakura-piksel sp_common ile AYNI olmalı.
PINK_H, PINK_GAIN, PINK_S = 345 / 360, 1.45, 0.62

# ifade efektlerinin düz renkleri (emotes.py): yeşil saç ayrıştırması bunlara dokunmaz
import emotes as _emotes
FX_COLORS = [c[:3] for c in (_emotes.SPARK, _emotes.NOTE, _emotes.SWEAT, _emotes.BANG, _emotes.TEAR, _emotes.GLOOM,
                             _emotes.ZZZ, _emotes.BLUSH, *_emotes.HEART)]


def pink_of(s):
    import sys
    sys.path.insert(0, os.path.join(os.path.expanduser("~"), ".claude", "skills", "sakura-piksel", "scripts"))
    import sp_common
    return sp_common.hls_to_rgb(np.full(s.shape, PINK_H), np.clip(s * PINK_GAIN, 0, 1), np.full(s.shape, PINK_S))


def unmix_hair(a):
    """Yeşil saçlı kare → (saç oranı w 0..1, gölge s 0..1, alttaki renk). Kenar pikseli = w·saç + (1−w)·alttaki;
    alttaki renk çevredeki saç olmayan piksellerin ortalaması, saç rengi çevredeki saf saçın ortalamasıdır."""
    rgb = a[..., :3].astype(float)
    full = a[..., 3] == 255
    vis = a[..., 3] > 0
    tint = green_tint(a) & vis
    hard = tint & (green_dom(a[..., :3]) >= 0.9)
    soft = vis & ~tint & (green_dom(a[..., :3]) < 0.05)

    def lmean(mask, r):
        n = box_count(mask, r)
        sm = np.stack([box_count(np.where(mask, rgb[..., k], 0), r) for k in range(3)], -1)
        return sm / np.maximum(n, 1)[..., None], n

    B, nb = lmean(soft & full, 2)
    for r in (4, 7):
        B2, n2 = lmean(soft & full, r)
        B, nb = np.where((nb > 0)[..., None], B, B2), np.maximum(nb, n2)
    Hc, nh = lmean(hard, 2)
    for r in (4, 8):
        H2, n2 = lmean(hard, r)
        Hc, nh = np.where((nh > 0)[..., None], Hc, H2), np.maximum(nh, n2)
    band = tint & ~hard
    d = Hc - B
    wb = np.clip(((rgb - B) * d).sum(-1) / np.maximum((d * d).sum(-1), 1), 0, 1)
    # izdüşüm koyu zeminde (hırka, kontur) saç gölgesini 0 sayabiliyor: yeşil baskınlığı oranı da alt sınır
    wb = np.maximum(wb, np.clip(green_dom(a[..., :3]) / np.maximum(green_dom(Hc), 0.3), 0, 1))
    w = np.zeros(a.shape[:2])
    w[hard] = 1
    w[band] = np.where((nb[band] > 0) & (nh[band] > 0), wb[band], 1)
    src = np.where(hard[..., None], rgb, Hc) / 255
    mx, mn = src.max(-1), src.min(-1)
    s = (mx + mn) / 2  # HLS açıklığı
    under = np.where((band & (nb > 0))[..., None], B, rgb)
    w[~vis] = 0
    return w, s, under


def green_finalize(d, from_raw=False):
    """Her karede yeşil saçı ayrıştırır: kare = w·P(s) + (1−w)·alttaki (varsayılan pembe), grup PNG'si R = grup
    (saç oranı ≥ 0,5 ise 1), G = saç oranı, B = gölge. Klasöre 'hairw' işareti konur: Sakura.cs bu görünümde G/B'yi okur."""
    import glob
    import shutil
    raw = os.path.join(HERE, "out", os.path.basename(d) + "-ham")  # ayrıştırmadan önceki yeşil kareler: `python smooth.py ayristir` yalnız bu adımı yeniden çalıştırır
    if not from_raw:
        shutil.rmtree(raw, ignore_errors=True)
        shutil.copytree(d, raw)
    n = 0
    for rf in glob.glob(os.path.join(raw, "**", "*.png"), recursive=True):
        if os.sep + "groups" + os.sep in rf:
            continue
        rel = os.path.relpath(rf, raw)
        f = os.path.join(d, rel)
        a = np.array(Image.open(rf).convert("RGBA"))
        rgp = os.path.join(os.path.dirname(rf), "groups", os.path.basename(rf))
        gp = os.path.join(os.path.dirname(f), "groups", os.path.basename(f))
        g = np.array(Image.open(rgp).convert("RGB"))[..., 0] if os.path.exists(rgp) else np.zeros(a.shape[:2], np.uint8)
        w, s, under = unmix_hair(a)
        # ifade efektleri (poses.coarse_overlay, emotes.py renkleri) saç değil: parıltının sarısı zeytin tonlu
        # saç karışımı sayılıp saç oranı 1, gölge 0 alıyor ve siyaha boyanıyordu
        fx = np.zeros(a.shape[:2], bool)
        for c in FX_COLORS:
            fx |= (a[..., :3] == c).all(-1) & (a[..., 3] == 255)
        w[fx] = 0
        # silüet kenarında açık, soluk yeşil kalıntı (JPEG'li beyaz zeminle karışım): saydam
        hh, ss, vv = hsv_of(a)
        rim = (w > 0) & (vv > 0.85) & (ss < 0.35) & (box_count(a[..., 3] == 0, 1) > 0)
        a[rim] = 0
        w[rim] = 0
        m = ((w > 0) | (green_tint(a) & (a[..., 3] > 0))) & ~fx  # oranı 0 olan yeşil pus da alttaki renge döner
        out = a.copy()
        if m.any():
            p = pink_of(s[m]).astype(float)
            out[m, :3] = np.clip(w[m, None] * p + (1 - w[m, None]) * under[m], 0, 255).round().astype(np.uint8)
        gr = g.copy()
        gr[(gr == 1) & (w < 0.5)] = 0
        gr[w >= 0.5] = 1
        gr[out[..., 3] == 0] = 0
        G = np.where(out[..., 3] > 0, np.round(w * 255), 0).astype(np.uint8)
        Bc = np.where(m, np.round(np.clip(s, 0, 1) * 255), 0).astype(np.uint8)
        Image.fromarray(out, "RGBA").save(f)
        os.makedirs(os.path.dirname(gp), exist_ok=True)
        Image.fromarray(np.stack([gr, G, Bc], -1), "RGB").save(gp)
        n += 1
    with open(os.path.join(d, "hairw"), "w") as fh:
        fh.write("G = saç oranı, B = gölge (HLS açıklığı); P(s) = HLS(%.6f, min(1, s*%.3f), %.3f)\n" % (PINK_H, PINK_GAIN, PINK_S))
    print("yeşil saç ayrıştırma:", n, "kare")


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["ayristir"]:
        green_finalize(os.path.join(HERE, "frames", LOOK), from_raw=True)
    else:
        # üretim sürerken Sakura önceki hazır kareleri kullansın (Sakura.cs Sprites.FramesDir)
        import shutil
        d = os.path.join(HERE, "frames", LOOK)
        prev = d + "-onceki"
        if os.path.isdir(d) and not os.path.exists(os.path.join(d, "uretiliyor")):
            shutil.rmtree(prev, ignore_errors=True)
            shutil.copytree(d, prev)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "uretiliyor"), "w").close()
        main()
        os.remove(os.path.join(d, "uretiliyor"))
