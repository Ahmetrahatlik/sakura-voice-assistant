# Windows arka plan sürecini güç kısıtlamasından (EcoQoS) çıkarır: Sakura dinlerken/konuşurken yavaşlamasın.
import ctypes
from ctypes import wintypes


def hizlandir():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    class PPT(ctypes.Structure):
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]
    s = PPT(1, 0x1 | 0x4, 0)  # EXECUTION_SPEED + IGNORE_TIMER_RESOLUTION: kısıtlama yok
    k.SetProcessInformation(k.GetCurrentProcess(), 4, ctypes.byref(s), ctypes.sizeof(s))  # ProcessPowerThrottling
    ctypes.WinDLL("winmm").timeBeginPeriod(1)
