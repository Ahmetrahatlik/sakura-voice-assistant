# Sakura sesli asistanı arka planda başlatır (pencere açmaz, Claude oturumu kapansa da yaşar).
# "Sustur" işaretini de kaldırır: masaüstü Sakura'nın bekçisi asistanı yine açık tutar.
$kok = $PSScriptRoot
Remove-Item (Join-Path $kok 'kapali.flag') -ErrorAction SilentlyContinue
$py = Join-Path (Split-Path $kok) 'ses\venv_xtts\Scripts\pythonw.exe'
$komut = "`"$py`" `"$(Join-Path $kok 'sakura_asistan.py')`""
Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $komut; CurrentDirectory = $kok } | Out-Null
Write-Output "Sakura asistanı başlatılıyor (yaklaşık 1,5 dk sonra hazır)."
