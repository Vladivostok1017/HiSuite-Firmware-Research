# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 HiSuite-Firmware-Research contributors
#
# watch_rom.ps1 —— 盯 HiSuite 的 ROM 下载目录，出现文件立即复制到安全位置
# 用法：
#   pwsh -NoProfile -File watch_rom.ps1 -Src "$env:USERPROFILE\Documents\HiSuite\ROM" -Dst ".\captures\rom"
# 说明：
#   - 只复制，不移动、不改属性，HiSuite 的 sha256 校验不会受影响
#   - 递归监控 cloud_rom 的 lfapp / language / rom_feature / app_bundle 四个子目录
#   - 同时把 filelist.xml / changelog*.xml 优先抓出来（分片清单在里面）
param(
  [string]$Src = "$env:USERPROFILE\Documents\HiSuite\ROM",
  [string]$Dst = ".\captures\rom",
  [int]$IntervalSec = 2
)
$ErrorActionPreference = 'Continue'
if (-not (Test-Path -LiteralPath $Src)) { New-Item -ItemType Directory -Force -Path $Src | Out-Null }
New-Item -ItemType Directory -Force -Path $Dst | Out-Null
$log = Join-Path $Dst ("watch_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss'))

function Log([string]$m) {
  $line = "[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $m
  Write-Host $line
  Add-Content -LiteralPath $log -Value $line -Encoding utf8
}

Log "START  src=$Src  dst=$Dst  interval=${IntervalSec}s"
$seen = @{}
$copied = 0
while ($true) {
  try {
    $files = Get-ChildItem -LiteralPath $Src -Recurse -File -Force -ErrorAction SilentlyContinue
    foreach ($f in $files) {
      $key = $f.FullName
      $sig = "$($f.Length)|$($f.LastWriteTimeUtc.Ticks)"
      if ($seen.ContainsKey($key) -and $seen[$key] -eq $sig) { continue }
      $seen[$key] = $sig
      $rel = $f.FullName.Substring($Src.Length).TrimStart('\')
      $target = Join-Path $Dst $rel
      $tdir = Split-Path -Parent $target
      if (-not (Test-Path -LiteralPath $tdir)) { New-Item -ItemType Directory -Force -Path $tdir | Out-Null }
      try {
        Copy-Item -LiteralPath $f.FullName -Destination $target -Force -ErrorAction Stop
        $copied++
        Log ("COPY {0,12} {1}" -f $f.Length, $rel)
      } catch {
        Log ("FAIL {0} : {1}" -f $rel, $_.Exception.Message)
      }
    }
    # 单独把清单类文件再抄一次到 Dst 根，方便一眼看到
    foreach ($pat in 'filelist.xml','changelog*.xml','*.conf','*.json') {
      Get-ChildItem -LiteralPath $Src -Recurse -File -Filter $pat -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $t = Join-Path $Dst ("_manifest_" + $_.Name)
        if (-not (Test-Path -LiteralPath $t) -or (Get-Item -LiteralPath $t).Length -ne $_.Length) {
          Copy-Item -LiteralPath $_.FullName -Destination $t -Force -ErrorAction SilentlyContinue
          Log ("MANIFEST {0,10} {1}" -f $_.Length, $_.Name)
        }
      }
    }
    $st = "poll files={0} copied={1}" -f $files.Count, $copied
    if (($files.Count -gt 0) -and (Get-Random -Maximum 10 -eq 0)) { Log $st }
  } catch {
    Log ("POLL-ERR " + $_.Exception.Message)
  }
  Start-Sleep -Seconds $IntervalSec
}
