# Sahneyi kaydeder: kaydet.ps1 <sahne> <saniye> <çıktı.mp4>
# Tüm ekran kaydedilir; kayıt boyunca Sakura'nın penceresi (balon dahil) 10 kez/sn <çıktı>.iz.csv'ye yazılır.
# Dikey kadraj sonra bu ize göre seçilir (kurgu.py): fırlatınca nereye düşerse düşsün balon kadrajda kalır.
param([string]$klasor = "Ödevler", [int]$sure = 48, [string]$cikti, [switch]$dekorsuz)
$m = "$env:USERPROFILE\.claude\sakura"
$ff = "ffmpeg"
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class KW { [StructLayout(LayoutKind.Sequential)] public struct R { public int L, T, Ri, B; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out R r);
 public delegate bool EP(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] public static extern bool EnumWindows(EP f, IntPtr l);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
 public static IntPtr Pet(uint pid) { IntPtr f = IntPtr.Zero; EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); var t = new System.Text.StringBuilder(32); GetWindowText(h, t, 32); if (p == pid && t.ToString() == "SakuraPet") { f = h; return false; } return true; }, IntPtr.Zero); return f; } }
"@
[KW]::SetProcessDPIAware() | Out-Null
Start-Process -Wait -FilePath "$m\Sakura.exe" -ArgumentList $(if ($dekorsuz) { @('dekor', 'kur', 'bos') } else { @('dekor', 'kur') }) -WorkingDirectory $m
$shell = New-Object -ComObject Shell.Application
$shell.MinimizeAll()
Start-Sleep -Seconds 2
$pid0 = (Get-CimInstance Win32_Process -Filter "Name='Sakura.exe'" | Where-Object { $_.CommandLine -like '*host*' } | Select-Object -First 1).ProcessId
$h = [KW]::Pet([uint32]$pid0)
$t0 = Get-Date
$p = Start-Process -PassThru -WindowStyle Hidden -RedirectStandardError "$cikti.ff.log" -FilePath $ff -ArgumentList @('-hide_banner', '-loglevel', 'info', '-y', '-f', 'gdigrab', '-framerate', '30', '-t', "$sure", '-i', 'desktop', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-pix_fmt', 'yuv420p', $cikti)
$iz = New-Object System.Collections.Generic.List[string]
$basladi = $false
while (-not $p.HasExited) {
    $t = ((Get-Date) - $t0).TotalSeconds
    if (-not $basladi -and $t -ge 4) { & "$m\Sakura.exe" sahnetest $klasor; $basladi = $true }
    $r = New-Object KW+R
    [KW]::GetWindowRect($h, [ref]$r) | Out-Null
    $iz.Add(("{0:F2},{1},{2},{3},{4}" -f $t, $r.L, $r.T, $r.Ri, $r.B))
    Start-Sleep -Milliseconds 100
}
# ffmpeg gorunteyi komuttan ~2 sn sonra almaya baslar: gercek ilk kare ani ffmpeg gunlugundeki "start:" degeridir
$bas = $t0
$m0 = Select-String -Path "$cikti.ff.log" -Pattern 'start: (\d+\.\d+)' | Select-Object -First 1
if ($m0) { $bas = ([DateTimeOffset]::FromUnixTimeMilliseconds([long]([double]::Parse($m0.Matches[0].Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture) * 1000))).LocalDateTime }
else { Write-Warning "ffmpeg baslangic ani okunamadi, ses kayabilir" }
$fark = ($bas - $t0).TotalSeconds
$izYeni = $iz | ForEach-Object { $f = $_ -split ','; if ($f.Count -eq 6) { $f = @(($f[0] + '.' + $f[1])) + $f[2..5] }; "{0:F2},{1},{2},{3},{4}" -f ([double]::Parse($f[0], [Globalization.CultureInfo]::InvariantCulture) - $fark), $f[1], $f[2], $f[3], $f[4] }
[IO.File]::WriteAllLines("$cikti.iz.csv", $izYeni)
"kayit_basi " + $bas.ToString("HH:mm:ss.fff")
$shell.Windows() | Where-Object { $_.Document.Folder.Self.Path -like "*\$klasor" } | ForEach-Object { $_.Quit() }
Start-Sleep -Seconds 1
Start-Process -Wait -FilePath "$m\Sakura.exe" -ArgumentList @('dekor', 'geri') -WorkingDirectory $m
$shell.UndoMinimizeALL()
