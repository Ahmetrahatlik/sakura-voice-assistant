# Sakura'nın gözü: tüm ekranların görüntüsünü beyin\ekran.png'ye kaydeder.
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
# Ekran ölçekliyse (ör. %125) DPI farkında olmayan süreç ekranın yalnızca sol üst kısmını yakalar.
Add-Type -Namespace Sakura -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[Sakura.Dpi]::SetProcessDPIAware() | Out-Null
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$out = Join-Path $PSScriptRoot 'beyin\ekran.png'
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output $out
