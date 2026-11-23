# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 HiSuite-Firmware-Research contributors
#
# tail_sysupdate.ps1 —— 实时盯 HiSuite 的 SystemUpdate 日志，并给出"停手"判定
# 用法：pwsh -NoProfile -File tail_sysupdate.ps1
# 判定线：
#   packageType:full        → 服务器给了包（这一行出现就说明通道对了）
#   Enter BL SystemFull.    → 即将进入 bootloader 全量刷写（此之前必须点取消）
#   Download / url / cloud_rom → 进入下载阶段（这时去开 watch_rom.ps1）
#   invalid / CAUSE:        → HiSuite 自己中止了
$ErrorActionPreference = 'Continue'
$logDir = "$env:LOCALAPPDATA\HiSuite\log"
if (-not (Test-Path $logDir)) { Write-Host "no log dir: $logDir"; exit 1 }

$latest = Get-ChildItem $logDir -Filter 'SystemUpdate_*.log' -File -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $latest) { Write-Host "no SystemUpdate log yet"; exit 1 }

Write-Host "==== tailing: $($latest.Name) ===="
Write-Host "（Ctrl+C 退出；下面每条按判定线着色）`n"
$pos = $latest.Length

$color = @{
  'packageType'   = 'Cyan'
  'FirmWare'      = 'Cyan'
  'SaleInfo'      = 'DarkCyan'
  'Enter BL'      = 'Red'
  'Download'      = 'Yellow'
  'url'           = 'Yellow'
  'cloud_rom'     = 'Yellow'
  'invalid'       = 'DarkRed'
  'CAUSE'         = 'Magenta'
  'TrustList'     = 'Magenta'
  'IsRescueMode'  = 'Green'
  'req\['         = 'Gray'
}
while ($true) {
  try {
    $fs = [System.IO.File]::Open($latest.FullName, 'Open', 'Read', 'ReadWrite')
    if ($fs.Length -gt $pos) {
      $fs.Seek($pos, 'Begin') | Out-Null
      $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)
      $chunk = $sr.ReadToEnd()
      $pos = $fs.Position
      $sr.Close(); $fs.Close()
      foreach ($line in ($chunk -split "`r?`n")) {
        if (-not $line.Trim()) { continue }
        $c = 'White'
        foreach ($k in $color.Keys) { if ($line -match $k) { $c = $color[$k]; break } }
        $short = $line -replace '^\[\d{4}-\d\d-\d\d [\d:]+\]\[[^\]]+\]\[[^\]]+\]\[[^\]]+\]', ''
        Write-Host $short -ForegroundColor $c
      }
    } else {
      $fs.Close()
    }
  } catch { }
  Start-Sleep -Milliseconds 500
}
