# HiSuite Firmware Research

逆向 **Huawei HiSuite**（华为手机助手）的固件分发链路，目标是**绕过 HiSuite 的刷机流程，直接从华为 CDN 拿到官方 OTA 包**。

不刷机、不碰设备分区、不依赖第三方固件站——所有 URL 和校验值都来自华为自己的服务器。

> 状态：**2026-11-06 实测通过**
> 测试环境：HiSuite `17.0.0.100` / Windows 11 22H2 / HUAWEI `NOP-AN01P`（Mate RS 保时捷设计）/ HarmonyOS `4.2.0.196`

---

## 核心结论

| # | 结论 | 强度 |
|---|---|---|
| 1 | HiSuite 的网络层是 `httpcomponent.dll` + **OpenSSL 3**（`libssl-3.dll`），**内嵌 51 个 CA**，不读系统证书库 | 实测 |
| 2 | 因此装系统证书抓不到包，但**在进程内 hook `SSL_read`/`SSL_write` 可以直接拿到明文**，无需证书、无需代理 | 实测 |
| 3 | 固件清单走 **`update.dbankcdn.com`** 的明文 `filelist.xml`，路径形如 `/download/data/pub_13/HWHOTA_hota_900_9/<xx>/v3/<token>/full/filelist.xml` | 实测 |
| 4 | `filelist.xml` 里有**文件名、大小、MD5、SHA256**，可据此拼出完整下载地址并校验 | 实测 |
| 5 | 官方 OTA 是**三包制**：`base` + `cust` + `preload`，必须全部下载才能组成完整系统 | 实测 |
| 6 | HiSuite 的"系统修复"（rescue/fastboot 通道）会撞 `The device is not in the TrustList.`；**"系统更新"（正常系统 + adb 通道）不校验 TrustList**，能直接查到包 | 实测 |
| 7 | 抓到明文 ≠ 能自动下载：HiSuite 的业务上报（`/sdkv2`）是 `{"ed":…,"ek":…}` 二次加密，但固件清单是明文 | 实测 |

---

## 快速开始

### 1. 抓包（拿到 URL）

```powershell
# 前置：Python + frida
pip install frida-tools

# 杀掉已有 HiSuite，然后带 hook 启动
Stop-Process -Name HiSuite -Force -ErrorAction SilentlyContinue
frida -f "C:\Program Files (x86)\HiSuite\HiSuite.exe" -l tools/hook_ssl.js -o capture_out.log
```

启动后**在 HiSuite 里进入「系统更新」并点「检查更新」**，日志会实时打印所有 HTTP 请求/响应明文，同时写入 `tools/ssl_capture.log`。

### 2. 解析抓包

```powershell
python tools/parse_capture.py tools/ssl_capture.log
```

输出每个请求的 Host、URL、响应体。关注 `update.dbankcdn.com` 的 `filelist.xml`。

### 3. 下载并解出内核

```powershell
# 按 filelist.xml 里的地址下载三段包，然后：
python tools/carve_kernel.py update_full_base.zip work
```

`carve_kernel.py` 会：解 zip → 定位 `UPDATE.APP` → 流式扫 `ANDROID!` → 抠 boot → 解 gzip → 输出 ARM64 `Image` + banner。

---

## 关键数据结构

### 固件清单（filelist.xml）

```xml
<root>
  <vendorInfo name="base" logfile="changelog_base.xml" package="update_full_base.zip"/>
  <GROUP version="G6.0"/>
  <files>
    <file>
      <spath>update_full_base.zip</spath>
      <md5>13AE2CC8B1347248D094D8F473BFD119</md5>
      <sha256>5B285878B0217E866E21B4E14B617A60160082EC6F35BB29BAFBE37D522759BD</sha256>
      <size>5683825610</size>
    </file>
  </files>
</root>
```

完整地址 = `https://update.dbankcdn.com/download/data/pub_13/HWHOTA_hota_900_9/<xx>/v3/<token>/full/<spath>`

### 三段包（实测，NOP-AN01P / 4.2.0.196 / porsche_cn）

| 段 | 文件名 | 大小 | 内容 |
|---|---|---|---|
| base | `update_full_base.zip` | 5,683,825,610 | 系统主体，**含内核 Image** |
| cust | `update_full_cust_NOP-AN01P_porsche_cn.zip` | 241,982,039 | 定制层 |
| preload | `update_full_preload_NOP-AN01P_porsche_cn_R8.zip` | 1,229,169,548 | 预装应用 |

base 包内 `UPDATE.APP` 约 6.78 GB，含 8 处 `ANDROID!` 命中，其中 3 处是完整 boot（同一 kernel 的三个副本）。

---

## 工具

| 文件 | 作用 |
|---|---|
| `tools/hook_ssl.js` | Frida 脚本，hook OpenSSL 3 的 `SSL_read`/`SSL_write`/`SSL_CTX_set_verify`，输出明文 |
| `tools/parse_capture.py` | 把抓包日志按请求/响应切块，提取 Host、URL、响应体 |
| `tools/carve_kernel.py` | OTA zip → `UPDATE.APP` → boot → gzip kernel → ARM64 Image + banner |
| `tools/watch_rom.ps1` | 盯 HiSuite 的 ROM 下载目录，出现文件立即复制到安全位置（只复制不移动） |
| `tools/tail_sysupdate.ps1` | 实时 tail `SystemUpdate_*.log`，按判定线着色（含"即将刷写"的红线告警） |

---

## 文档

| 文件 | 内容 |
|---|---|
| [`docs/01-architecture.md`](docs/01-architecture.md) | HiSuite 组件、网络层、证书体系 |
| [`docs/02-hisuite-binary-analysis.md`](docs/02-hisuite-binary-analysis.md) | 固件下载逻辑静态分析（目录、落盘、缓存删除、阶段划分、packageType、危险面、证据附录） |
| [`docs/03-ota-package-structure.md`](docs/03-ota-package-structure.md) | OTA 包解剖、`UPDATE.APP`、boot/kernel 提取流程 |
| [`docs/04-frida-capture.md`](docs/04-frida-capture.md) | 用 Frida 在进程内抓 TLS 明文的完整方法 |
| [`docs/05-danger-zones.md`](docs/05-danger-zones.md) | 会变砖的操作清单 |
| [`docs/06-opensource-links.md`](docs/06-opensource-links.md) | 华为开源发布页索引 |
| [`findings/2026-11-06-nop-an01p.md`](findings/2026-11-06-nop-an01p.md) | 本次完整实证记录（含失败路径） |

---

## 适配性说明

**能拿到什么**：只要设备在 HiSuite 的支持范围内（能被「系统更新」识别），就能拿到它当前版本的官方完整包地址与校验值。

**拿不到什么**：

- 设备不在 HiSuite 支持列表里 → 「系统更新」阶段就会被拒，抓不到固件清单
- 目标版本 = 当前版本时，"系统修复"通道会以 `invalid` 中止（因为无更新必要），但「系统更新」通道仍能查出包（只是 HiSuite 不下载）
- 抓到的 `filelist.xml` 有时效（响应头 `X-CCDN-Expires: 600`，10 分钟量级），过期需重新抓

**已知版本差异**：同一个版本号可能对应多次编译。例如 `4.2.0.196` 在 CDN 上的 base 包内核是 `2024-04-26` 构建，而设备实跑的是 `2026-08-20` 构建——**同版本号、同工具链、不同构建期**。用包内内核做符号/偏移研究时必须先验 banner。

---

## 免责

- 本项目仅用于**固件取证、版本对比、逆向研究**。
- 下载的固件受华为最终用户许可协议约束，请自行确认你的使用场景。
- **不要**用本项目的产出走 HiSuite 的刷写流程：`docs/05-danger-zones.md` 列了会变砖的操作。
- 作者不对任何设备损坏、数据丢失、保修失效负责。

---

## 致谢

- [NebuSec](https://github.com/NebuSec) 等公开内核研究社区（提供了"从官方 OTA 反推偏移"的方法论参考）
- Frida 项目（进程内 TLS 明文抓取）
- 所有在 issue 里贡献机型/版本组合的人

## License

**GNU General Public License v3.0 or later**（GPL-3.0-or-later）— 全文见 [LICENSE](LICENSE)。

```
Copyright (C) 2026 HiSuite-Firmware-Research contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
```

衍生作品须以同等条款开放（含通过网络分发的修改版）。源码文件头部统一带 `SPDX-License-Identifier: GPL-3.0-or-later`。
