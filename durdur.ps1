# Sakura sesli asistanını kapatır (masaüstü Sakura açık kalır).
# kapali.flag: Dino kendisi susturdu, bekçi asistanı yeniden açmasın (baslat.ps1 kaldırır).
New-Item -ItemType File -Force (Join-Path $PSScriptRoot 'kapali.flag') | Out-Null
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*sakura_asistan.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output "kapatıldı: $($_.ProcessId)" }
# 5 Kas: asistanın açtığı arama tüneli (cloudflared) de kapansın, yoksa her yeniden başlatmada bir tane birikiyor
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" |
    Where-Object { $_.CommandLine -like '*127.0.0.1:47622*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
