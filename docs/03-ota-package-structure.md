# OTA 包解析结果 —— NOP-AN00 / HarmonyOS 2.0.0

## 结论先说：包是对的机型，但**内核版本不对**，不能用来判定你机器

| | 你给的这个包 | 你机器实际在跑 |
|---|---|---|
| 型号 | NOP-AN00 / AN00P / AN01P ✓ | NOP-AN00 ✓ |
| 版本 | `102.0.0.165(C00E160R8P2)`，**HarmonyOS 2.0.0**（base `NOP-LGRP1-CHN 11.0.0.176`） | `4.2.0.196(C786E182R8P6)`，**HarmonyOS 4.2**（base `NOP-LGRP1-CHN 4.2.0.196`） |
| 内核 | **Linux 4.14.116**（clang 9.0.3，r353983c） | **Linux 5.10.43**（clang 12.0.7，r416183b1，2026-08-20 构建） |
| 内核构建日期 | 2021 年 | 2026-08-20 |

内核串原文（从 Image 里抠出来的，非推测）：

```
Linux version 4.14.116 (HarmonyOS@localhost) (Android (27847 based on r353983c) clang version 9.0.3 ...
```

华为在 HarmonyOS **3.0** 才把 NOP 平台切到 5.10.43（HM3 源码包 Makefile 即 `VERSION=5 PATCHLEVEL=10 SUBLEVEL=43`）。所以 2.0 的包分析不到 5.10.43 的任何东西。

---

## 但整条链路已经跑通了（这才是这次的价值）

包的解剖结构（实测）：

```
NOP-AN00_102.0.0.165(...)_Firmware_HarmonyOS_2.0.0_05016QDY.zip   5.88 GB
└── Software/dload/update_sd_base.zip                             4.84 GB
    ├── UPDATE.APP                                                5.93 GB   ← HWOTA 容器
    ├── PTABLE.APP / ptable.img
    ├── META-INF/... (update-binary, CERT.SF, CERT.RSA)
    └── packageinfo.mbn / BOARDID_LIST.mbn / SOFTWARE_VER_LIST.mbn
```

`UPDATE.APP` 里内嵌的包元数据（容器头部明文可见）：

```
deviceModel=NOP-AN00;NOP-AN00P;NOP-AN01P
versionCode=10200165
BASE_VER NOP-LGRP1-CHN 11.0.0.176
TIME:2021-07-30 12:16:40
```

抠内核的过程（**没有逆向 HWOTA 私有结构**，直接按魔数扫）：

1. 流式扫 `UPDATE.APP`（5.93 GB）找 `ANDROID!` 魔数 → 命中 3 处（三份相同 boot 镜像）
2. 用 Android boot header 自带的 `kernel_size/ramdisk_size/page_size` 算出镜像总长，整块抠出
3. 结果：`page_size=2048`，`header_version=2`，`kernel=19.65 MB`，`ramdisk=0`
4. kernel 段是 **gzip** → 解压得 `Image.raw`，**51.01 MB**，偏移 `0x38` 处魔数 `0x644D5241`（`ARMd`）→ 确认是合法 ARM64 Image
5. 在 `Image.raw` 里读出 `Linux version 4.14.116 ...`

产物：
```
D:\ota_work\Software\dload\update_sd_base.zip   5.19 GB
D:\ota_work\boot0.img                          19.66 MB   （carve 出的 boot 镜像）
D:\ota_work\boot0.img.kernel                   19.65 MB   （gzip 压缩的 kernel 段）
D:\ota_work\Image.raw                          51.01 MB   （解压后的 ARM64 内核）
```

脚本：`diag/tools/identify_ota.py`（识别包格式）、`diag/tools/carve_boot.py`（扫魔数 + 抠镜像 + 拆 kernel）

---

## 下一步需要哪个包

| 优先级 | 目标 | 为什么 |
|---|---|---|
| ★★★ | `NOP-AN01P 4.2.0.196(C786E182R8P6)` / base `NOP-LGRP1-CHN 4.2.0.196` / incremental `104.2.0.196C786` | 你机器原样，唯一能给出确定答案的样本 |
| ★★ | 任意 **HarmonyOS 3.0.x** 的 NOP 包 | 已经是 5.10.43；可以先用它验证「源码 ↔ 出厂二进制」是否一致，等于把方法学先校准 |
| ★ | 4.2.0.x 其它小版本（如 4.2.0.1xx） | 同内核分支，风险只在补丁级差异 |

搜的时候关键词直接用 build 号：
`NOP-LGRP1-CHN 4.2.0.196`、`C786E182R8P6`、`104.2.0.196C786`、`NOP-AN01P 4.2.0.196 固件`

---

## 拿到 5.10.43 的 Image 之后要做什么（工具已就绪一半）

1. 同样的 `carve_boot.py` 抠出 boot → `Image.raw`
2. 需要在新 Image 上定位 `remove_waiter()`。两条路：
   - **a. kallsyms 提取**：华为 image 里保留了 kallsyms 表（运行时被 `HUAWEI_HIDESYMS` 隐藏，但镜像里有），解出来就有精确符号地址 → Capstone 反汇编目标函数 → 看 `pi_blocked_on` 那条 STR 的基址是 `current`（sp_el0 派生）还是 `waiter->task`
   - **b. 特征码匹配**：拿 HM3 源码编译出参考 vmlinux（clang 12.0.7 与出厂编译版本一致，指令序列大概率逐字节可比），提 `remove_waiter` 的字节特征去扫 Image
3. 判定：`str xzr, [x?, #<pi_blocked_on>]` 的基址寄存器来自 `current` → **未修**（GhostLock 可用）；若是从 `waiter` 结构里再取的 task 指针 → **已修**（该路线终止）

> 注：4.14.116 那份 Image 属于另一条分支，即使现在分析出"有洞"，也**不能**外推到 5.10.43。
