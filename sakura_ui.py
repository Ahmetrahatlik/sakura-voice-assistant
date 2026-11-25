# Masaüstü Sakura'ya (Sakura.exe, pencere "SakuraPet") WM_COPYDATA ile olay gönderir.
# Biçim Sakura.cs Event.Encode ile aynı: alanlar \n ile birleşir, UTF-8, base64 (+ → -, / → _).
import base64, ctypes
from ctypes import wintypes

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.FindWindowW.restype = wintypes.HWND
u32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [("dwData", ctypes.c_size_t), ("cbData", wintypes.DWORD), ("lpData", ctypes.c_void_p)]


def gonder(durum, metin="", ifade="mutlu", saniye=0.0):
    alanlar = ["jarvis", durum, metin, "%.2f" % saniye, ifade, "", "idle_", "", ""]
    s = "\n".join(a.replace("\n", " ") for a in alanlar)
    b64 = base64.b64encode(s.encode("utf-8")).decode().replace("+", "-").replace("/", "_").encode("utf-8")
    h = u32.FindWindowW(None, "SakuraPet")
    if not h:
        return False
    buf = ctypes.create_string_buffer(b64, len(b64))
    cds = COPYDATASTRUCT(0, len(b64), ctypes.cast(buf, ctypes.c_void_p))
    sonuc = ctypes.c_size_t()
    u32.SendMessageTimeoutW(h, 0x004A, 0, ctypes.addressof(cds), 0x0002, 2000, ctypes.byref(sonuc))  # SMTO_ABORTIFHUNG
    return True
