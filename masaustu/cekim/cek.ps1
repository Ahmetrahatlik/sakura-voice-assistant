# Ekran görüntüleri: cek.ps1 <önek> <adet> <aralık sn>  → scratchpad\kare\<önek>_NN.png (yarı boy)
param([string]$on = "s", [int]$n = 10, [double]$ara = 2)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System.Runtime.InteropServices;
public static class Dpi { [DllImport("user32.dll")] public static extern bool SetProcessDPIAware(); }
"@
[Dpi]::SetProcessDPIAware() | Out-Null
$dir = Join-Path $PSScriptRoot "kare"
New-Item -ItemType Directory -Force $dir | Out-Null
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
for ($i = 0; $i -lt $n; $i++) {
    $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
    $half = New-Object System.Drawing.Bitmap $bmp, ([int]($b.Width / 2)), ([int]($b.Height / 2))
    $half.Save((Join-Path $dir ("{0}_{1:D2}.png" -f $on, $i)), [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose(); $half.Dispose()
    Start-Sleep -Milliseconds ([int]($ara * 1000))
}
