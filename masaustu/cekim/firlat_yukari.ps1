# Sentetik fırlatma: (x, y)'den tutup hızla yukarı çeker, hareket ederken bırakır. Her olay arası süreyi ölçer.
param([int]$x, [int]$y, [int]$dy = 500, [int]$adim = 10)
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class M {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(int f, int dx, int dy, int d, IntPtr e);
}
"@
[M]::SetProcessDPIAware() | Out-Null
[M]::SetCursorPos($x, $y); Start-Sleep -Milliseconds 300
$sw = [Diagnostics.Stopwatch]::StartNew()
[M]::mouse_event(2, 0, 0, 0, [IntPtr]::Zero)  # sol bas
Start-Sleep -Milliseconds 120
$t = @()
for ($i = 1; $i -le $adim; $i++) {
    $a = $sw.ElapsedMilliseconds
    [M]::SetCursorPos($x, $y - [int]($dy * $i / $adim))
    Start-Sleep -Milliseconds 15
    $t += ($sw.ElapsedMilliseconds - $a)
}
[M]::mouse_event(4, 0, 0, 0, [IntPtr]::Zero)  # bırak
"adım süreleri (ms): " + ($t -join ",") + "  toplam " + $sw.ElapsedMilliseconds
