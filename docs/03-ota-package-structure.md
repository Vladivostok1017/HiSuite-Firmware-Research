# 03 · OTA 包结构

从华为 CDN 拿到的 `update_full_base.zip` 是一个**多层封装的容器**。本文说明每层的格式，以及如何从中提取出 `boot` → 内核 `Image`。

所有尺寸与偏移均来自实测样本（HiSuite `17.0.0.100` / `NOP-AN01P` / HarmonyOS `4.2.0.196` / `porsche-cn`）。

---

## 1. 封装层次

```
update_full_base.zip                     5,683,825,610
└── UPDATE.APP                           6,778,714,684   ← 包内第一个条目，偏移 0x110
     ├── ANDROID! ×8（3 处为完整 boot，5 处为伪命中）
     └── boot: page_size=2048, header_version=2
          ├── kernel  24,729,818 (gzip)
          └── ramdisk 504
```

外层是标准 ZIP（`PK\x03\x04`），`META-INF/` 与常规 Android 包一致。真正的固件全部在 `UPDATE.APP` 里——**它不是 ZIP，也不是 tar，而是一个平铺的二进制容器**，内部按固定页对齐依次存放各个分区镜像。

`UPDATE.APP` 头部有一段明文元数据，可直接读出机型与版本：

```
deviceModel=NOP-AN00;NOP-AN00P;NOP-AN01P
versionCode=10200165
BASE_VER NOP-LGRP1-CHN 11.0.0.176
TIME:2021-07-30 12:16:40
```

> 上例来自另一个版本（HarmonyOS 2.0.0）的包，用来展示字段格式。

---

## 2. 定位 boot 镜像

不需要逆向 `UPDATE.APP` 的私有索引表，直接**按魔数扫描**即可：

1. 流式扫全文件找 `ANDROID!`（8 字节）
2. 对每个命中，按 Android boot header 读取头字段
3. 用 `page_size` + `kernel_size` 算出 kernel 段位置

`tools/carve_kernel.py` 就是这套流程的实现，扫描时按 8 MiB 分块并保留边界重叠，适用于数 GB 级文件。

### boot header 关键字段（v0–v2 通用）

| 偏移 | 字段 | 说明 |
|---|---|---|
| 0x00 | magic | `ANDROID!` |
| 0x08 | kernel_size | kernel 段字节数 |
| 0x0C | kernel_addr | 加载地址（可忽略） |
| 0x10 | ramdisk_size | ramdisk 字节数 |
| 0x14 | ramdisk_addr | |
| 0x18 | second_size | |
| 0x24 | page_size | 2048 / 4096 / 8192 / 16384 |
| 0x28 | header_version | 2 |
| 0x2C | os_version | |

kernel 段起始 = `page_size`（v0/v1/v2 均为页对齐），长度 = `kernel_size`。

### 实测中的伪命中

一次扫描命中 8 处 `ANDROID!`，只有 3 处是真 boot。其余是：

- `kernel_size=0` + 巨大的 `ramdisk_size`（header 字段被随机数据凑巧对上）
- `page_size` 不在合法枚举内

**判据**：`page_size ∈ {2048, 4096, 8192, 16384, 65536}` 且 `kernel_size` 非零且不超出文件尾。

三处真 boot 内容完全相同（同一 kernel 的三个副本，对应 A/B 槽或不同刷写路径），无需去重，取任一份即可。

---

## 3. 从 boot 到内核 Image

kernel 段通常是 **gzip**（魔数 `1f 8b`）：

```
kernel 段 24,729,818 字节  →  gzip 解压  →  73,521,236 字节
偏移 0x38 处为 b'ARMd'  ← 合法 ARM64 Image 的标识
```

ARM64 Linux Image 的头部布局：

| 偏移 | 字段 |
|---|---|
| 0x00 | code0（`b primary_entry`） |
| 0x08 | text_offset |
| 0x10 | image_size |
| 0x18 | flags |
| 0x38 | magic `ARMd`（0x644D5241 小端） |

`image_size` 应与实际文件长度一致；不一致说明解压不完整或载体被裁剪。

### 验证解出来的是不是目标版本

Image 里有两处必查字符串：

```powershell
# 1) 版本串（含编译器与构建主机）
Linux version 5.10.43 (HarmonyOS@localhost) (Android (7485623, based on r416183b1) clang version 12.0.7 ...)

# 2) 构建时间戳（★ 判版本的关键）
#1 SMP PREEMPT Fri Apr 26 13:47:07 CST 2024
```

**同版本号 ≠ 同二进制**。实测中 `4.2.0.196` 在 CDN 上对应 `2024-04-26` 构建，而另一台设备实跑的是 `2026-08-20` 构建——版本号、编译器、构建主机全部相同，只是两次编译。

所以比对时：

- 只比 `5.10.43` 这类版本号 → 可能误判为"同一内核"
- 必须比 `#1 SMP PREEMPT <日期>` → 才能确认是不是同一份二进制

`tools/carve_kernel.py` 提取后会直接打印这两段，方便核对。

---

## 4. 三段包的关系

base 包之外还有 `cust` 与 `preload`：

| 段 | 内容 | 是否含内核 |
|---|---|---|
| base | 系统主体、`boot`、`vbmeta`、system/vendor 等 | ✅ |
| cust | 运营商/销售区域定制层 | ❌ |
| preload | 预装应用 | ❌ |

研究内核只需 base。三段各自的 `filelist.xml` 独立，路径里的 v3 token 不同。

---

## 5. 产物校验

CDN 给的 `filelist.xml` 里有完整校验值，下载后应对齐：

```
MD5    13AE2CC8B1347248D094D8F473BFD119
SHA256 5B285878B0217E866E21B4E14B617A60160082EC6F35BB29BAFBE37D522759BD
size   5683825610
```

```powershell
Get-FileHash update_full_base.zip -Algorithm MD5
Get-FileHash update_full_base.zip -Algorithm SHA256
```

CDN 响应头带 `Accept-Ranges: bytes`，支持断点续传；`X-CCDN-Expires: 600` 表示清单本身约 10 分钟过期，包体地址不受影响。
