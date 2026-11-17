# Capture one window by title (PrintWindow works even when it is behind other windows).
param([string]$Out, [string]$Title = "Angry Birds Space (")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W { [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
 public struct RECT { public int L, T, R, B; } }
"@
$p = Get-Process | Where-Object { $_.MainWindowTitle -like "$Title*" } | Select-Object -First 1
if (-not $p) { throw "no window titled $Title" }
$h = $p.MainWindowHandle; $r = New-Object W+RECT; [W]::GetWindowRect($h, [ref]$r) | Out-Null
$bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
$g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
[W]::PrintWindow($h, $dc, 2) | Out-Null; $g.ReleaseHdc($dc); $bmp.Save($Out)
"$($p.MainWindowTitle) $($bmp.Width)x$($bmp.Height)"
