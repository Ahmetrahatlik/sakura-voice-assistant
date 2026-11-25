# Tam çözünürlükte bölge görüntüleri: bolge.ps1 <önek> <adet> <aralık sn> <x> <y> <g> <y>
param([string]$on = "b", [int]$n = 10, [double]$ara = 2, [int]$x = 1400, [int]$y = 0, [int]$w = 520, [int]$h = 700)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System.Runtime.InteropServices;
public static class Dpi2 { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }
"@
[Dpi2]::SetProcessDPIAware() | Out-Null
$dir = Join-Path $PSScriptRoot "kare"
New-Item -ItemType Directory -Force $dir | Out-Null
for ($i = 0; $i -lt $n; $i++) {
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size $w, $h))
    $bmp.Save((Join-Path $dir ("{0}_{1:D2}.png" -f $on, $i)), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    Start-Sleep -Milliseconds ([int]($ara * 1000))
}
