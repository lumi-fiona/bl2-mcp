# Is Borderlands 2 showing a crash dialog, and what does it say?
#
# WHY THIS EXISTS. On 2026-08-20 Lumi asked whether I could see a crash box by myself. I could
# see THAT one existed - stress-travel.sh already watches for a window titled "Message" - but not
# what it said, which is the difference between "it crashed" and "it crashed inside Python with
# this call stack". During an unattended run that difference is the whole diagnosis.
#
# A Windows message box keeps its text in a child control, not in the window title, so the title
# alone says nothing. This walks the children and reads them.
#
# Prints: STATE=<running|crashdialog|gone>, then the dialog text if there is one.

Add-Type @"
using System;using System.Runtime.InteropServices;using System.Text;
public class CW {
  [DllImport("user32.dll")] public static extern bool EnumWindows(Cb cb, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr h, Cb cb, IntPtr l);
  public delegate bool Cb(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@

function Text-Of([IntPtr]$h) {
  $sb = New-Object System.Text.StringBuilder 8192
  [CW]::GetWindowTextW($h, $sb, 8192) | Out-Null
  return $sb.ToString()
}

$procs = Get-Process Borderlands2 -ErrorAction SilentlyContinue | Where-Object { -not $_.HasExited }
if (-not $procs) { "STATE=gone"; exit 0 }
$ids = $procs | ForEach-Object { $_.Id }

$script:dialogs = @()
$cb = [CW+Cb]{
  param($h, $l)
  $p = 0; [CW]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
  if (($ids -contains $p) -and [CW]::IsWindowVisible($h)) {
    $cls = New-Object System.Text.StringBuilder 256
    [CW]::GetClassNameW($h, $cls, 256) | Out-Null
    $title = Text-Of $h
    # A crash box is class #32770 (the dialog class Windows uses for message boxes). The game's
    # own window is not that class, so this does not fire on a healthy game.
    if ($cls.ToString() -eq "#32770") {
      $parts = @()
      $child = [CW+Cb]{
        param($ch, $cl)
        $t = Text-Of $ch
        if ($t -and $t -ne "OK" -and $t -ne "Cancel") { $script:parts += $t }
        return $true
      }
      $script:parts = @()
      [CW]::EnumChildWindows($h, $child, [IntPtr]::Zero) | Out-Null
      $script:dialogs += ,@($title, ($script:parts -join "`n"))
    }
  }
  return $true
}
[CW]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null

if ($script:dialogs.Count -eq 0) { "STATE=running"; exit 0 }

"STATE=crashdialog"
foreach ($d in $script:dialogs) {
  "TITLE=$($d[0])"
  "----- text -----"
  $d[1]
  "----- end -----"
}
