---
name: 机型 / 版本报告
about: 报告一个 HiSuite 版本 + 设备的组合是否走得通
title: "[device] HUAWEI XXX / HarmonyOS X.X.X / HiSuite X.X.X"
labels: device-report
---

## 设备与软件

| 项 | 值 |
|---|---|
| HiSuite 版本 | |
| 设备型号 | |
| HarmonyOS / EMUI 版本 | |
| 内核 `uname -r` | |
| 抓包时的设备状态 | 正常系统 / fastboot&rescue / eRecovery |

## 结果

- [ ] 「系统更新」能查到 `packageType:full`（抓到 filelist.xml）
- [ ] 「系统更新」能点，但抓不到 filelist
- [ ] 「系统修复」报 `The device is not in the TrustList.`
- [ ] 其他（下面说明）

## 关键日志

`SystemUpdate_*.log` 里这几行（**请先脱敏：序列号、UDID、请求 ID**）：

```
（贴 IsRescueMode / fb success / packageType / FirmWare_Base / TrustList / invalid 等关键行）
```

## 抓到的 filelist（如果拿到了）

```xml
（贴 filelist.xml 内容；把 v3 token 替换成 <TOKEN>）
```

## 其他说明

<!-- 遇到过什么坑、试过什么方案 -->
