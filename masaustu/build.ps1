# Sakura.cs'i Windows'ta yerleşik .NET Framework derleyicisiyle, Sakura simgesiyle Sakura.exe'ye çevirir.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here 'Sakura.cs'
$out = Join-Path $here 'Sakura.exe'
$cp = New-Object System.CodeDom.Compiler.CompilerParameters
$cp.GenerateExecutable = $true
$cp.OutputAssembly = $out
$cp.CompilerOptions = "/target:winexe /win32icon:`"$(Join-Path $here 'sakura.ico')`""
$cp.ReferencedAssemblies.AddRange(@('System.dll', 'System.Core.dll', 'System.Windows.Forms.dll', 'System.Drawing.dll', 'System.Web.Extensions.dll', 'System.Management.dll', 'System.Security.dll'))
Add-Type -TypeDefinition (Get-Content -Raw -Encoding UTF8 $src) -CompilerParameters $cp -ErrorAction Stop
Write-Output "derlendi: $out"
