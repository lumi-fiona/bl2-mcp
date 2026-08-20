param([string]$Out = "shot.png")
Add-Type @"
using System;using System.Runtime.InteropServices;using System.Text;
public class C {
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr l);
  public delegate bool EnumWindowsProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct RECT { public int L,T,R,B; }
}
"@
Add-Type -AssemblyName System.Drawing
$ids = (Get-Process Borderlands2 -ErrorAction SilentlyContinue).Id
if (-not $ids) { "no game process"; exit 1 }
$script:hwnd = [IntPtr]::Zero
$cb = [C+EnumWindowsProc]{ param($h,$l)
  $p = 0; [C]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
  if (($ids -contains $p) -and [C]::IsWindowVisible($h)) {
    $r = New-Object C+RECT; [C]::GetWindowRect($h, [ref]$r) | Out-Null
    if (($r.R - $r.L) -gt 200) { $script:hwnd = $h }
  }
  return $true
}
[C]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
if ($script:hwnd -eq [IntPtr]::Zero) { "no visible game window"; exit 1 }
$r = New-Object C+RECT; [C]::GetWindowRect($script:hwnd, [ref]$r) | Out-Null
$w = $r.R - $r.L; $h = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $h))
$g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
# how much of it is non-black, so "did we capture a black rectangle" is answerable
$dark = 0; $n = 0
for ($y = 0; $y -lt $h; $y += 37) { for ($x = 0; $x -lt $w; $x += 37) {
  $c = $bmp.GetPixel($x,$y); $n++; if (($c.R + $c.G + $c.B) -lt 24) { $dark++ } } }
"$Out  ${w}x${h}  sampled=$n  near-black=$dark"
$bmp.Dispose()
