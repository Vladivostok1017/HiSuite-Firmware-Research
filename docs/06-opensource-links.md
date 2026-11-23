# 华为开源发布中心 — Mate 40 系列（NOP / NOH / OCE）内核源码直链

采集时间：2026-11-04　｜　来源：华为官方开源发布中心后台接口 `consumer.huawei.com/cmkt/servlet/file/list`
所有直链均已实测 `HTTP 206 Partial Content`（**支持断点续传 / 多线程**）。

---

## 0. 官方页面（自己点也行）

- 入口：https://consumer.huawei.com/en/opensource/
- 直达结果表（选 Smartphones → 搜 `Mate 40`）：
  https://consumer.huawei.com/en/opensource/detail/?siteCode=worldwide&keywords=Mate%2040&fileType=openSourceSoftware&pageSize=10&curPage=1
- 后台接口（纯 JSON，可自己再查）：
  `https://consumer.huawei.com/cmkt/servlet/file/list?siteCode=worldwide&keywords=Mate%2040&fileType=openSourceSoftware&pageSize=30&curPage=1`

> 页面是 JS 渲染的，直接打开 `/en/opensource/detail/` 是空表；必须带 `siteCode/keywords/fileType/pageSize/curPage` 参数，或用上面的 JSON 接口。

## 1. 你这台机器对应的包（NOP-AN00 / NOP-AN01P = Mate 40 RS 保时捷设计）

### ★ 首选：HarmonyOS 3.0.0（最新已发布源码，Linux 5.10.43）

```
https://download-c1.huawei.com/download/downloadCenter?downloadId=320D126A8AF9B83D2AF8FD7C6B3A7147&version=D0F028EF8D7CD0CEF1DFF21521103172&siteCode=worldwide
```

| 项 | 值 |
|---|---|
| 文件名 | `NOP-AN00-AN00P-AN01P_HarmonyOS3_0_0_opensource_tar.gz` |
| 大小 | **600,392,315 字节**（572.58 MB） |
| 版本 / 发布日期 | HarmonyOS 3.0.0 / 2023-08-01 |
| 说明 | HUAWEI Mate 40 RS 保时捷设计, NoahP |
| 开源声明（Notice） | https://download-c1.huawei.com/download/downloadCenter?downloadId=C86EDED5BC57B110ED699BDC4E8DEE37&siteCode=worldwide&file=false |

### 备选：EMUI 11.0.0（更老的 11.0.0.150 基线）

```
https://download-c1.huawei.com/download/downloadCenter?downloadId=CFCDF420D9596F62734A7BCDF2FD9C44&version=C98F05DEF94AEEDFE6C1F5D267437018&siteCode=worldwide
```

| 项 | 值 |
|---|---|
| 文件名 | `NOP-AN00_Code_Opensource.rar` |
| 大小 | **588,317,299 字节**（561.06 MB） |
| 版本 / 发布日期 | 11.0.0.150 / 2021-01-19 |

## 2. 同家族其它机型（交叉对比用）

| 机型 | 包名 | 版本 | 字节数 | 直链 |
|---|---|---|---|---|
| Mate 40 Pro（NOH-AL00/AL10） | `NOH-AL00-AL10_HarmonyOS3_0_0_opensource_tar.gz` | HarmonyOS 3.0.0 / 2023-07-25 | 600,402,134 | https://download-c1.huawei.com/download/downloadCenter?downloadId=A0143E27D5527763C8B243534B725A5B&version=937502943982415E48FB20EE1EBB7736&siteCode=worldwide |
| Mate 40（OCE-AN10） | — | EMUI 11.0.0 / 2021-02-08 | 561.12 MB | 走 JSON 接口查 |
| Mate 40E（OCE-AN50） | — | HarmonyOS 2.0 / 2021-07-16 | 562.37 MB | 同上 |
| Mate 40 Pro（NOH-AN00/AN01） | — | 11.0.0.150 / 2021-01-20 | 561.06 MB | 同上 |

## 3. 下载命令（走华为 CDN，国内通常满速）

```powershell
# aria2 多线程（推荐，16 线程 + 断点续传）
aria2c -x16 -s16 -k1M --file-allocation=none `
  "https://download-c1.huawei.com/download/downloadCenter?downloadId=320D126A8AF9B83D2AF8FD7C6B3A7147&version=D0F028EF8D7CD0CEF1DFF21521103172&siteCode=worldwide" `
  -o NOP-AN00-AN00P-AN01P_HarmonyOS3_0_0_opensource_tar.gz

# 或 curl 断点续传
curl -L -C - -o NOP_HM3.tar.gz "https://download-c1.huawei.com/download/downloadCenter?downloadId=320D126A8AF9B83D2AF8FD7C6B3A7147&version=D0F028EF8D7CD0CEF1DFF21521103172&siteCode=worldwide"
```

下载后校验（可选）：`certutil -hashfile NOP-AN00-AN00P-AN01P_HarmonyOS3_0_0_opensource_tar.gz SHA256`

## 4. 解压与要看的位置

```bash
tar -xzf NOP-AN00-AN00P-AN01P_HarmonyOS3_0_0_opensource_tar.gz
# 关键文件（CVE-2026-43499 的漏洞点）
kernel/locking/rtmutex.c        # remove_waiter()
```

判定标准（已在本机做过同源对比）：

```c
raw_spin_lock(&current->pi_lock);
rt_mutex_dequeue(lock, waiter);
current->pi_blocked_on = NULL;      /* ← 漏洞形态：应为 waiter->task->pi_blocked_on */
raw_spin_unlock(&current->pi_lock);
```

## 5. 重要限制（别踩坑）

1. **华为只发布到 HarmonyOS 3.0.0**。你机器上是 `NOP-AN01P 4.2.0.196(C786E182R8P6)`（2026-08 构建），**4.x 源码从未发布**。所以这份源码只能证明「华为 5.10.43 分支在这一代没有加固这段代码」，**不能证明你手上 2026-08 的构建没有回补修复**。
2. 这份是**内核源码**（572 MB），不是 boot.img。它不含 ramdisk、不含 `System.map` 的绝对地址；要做 profile 还得从 `boot.img` 取实际 Image 与符号。
3. 《README_Version.txt》会写明"released for the phone software version YYYY-MM-DD"，下载后先看一眼确认版本。
4. 源码编译出的 zImage **不能**刷进你这台 `flash.locked=1` 的机器（README 原文：已启用 secboot 的需先解密/解锁 secboot）。

---

# 补充：关于「HM3 能不能替代 HM4」

## 事实核对

| 查询 | 结果 |
|---|---|
| 关键字 `NOP` | **totalRows = 2** —— Mate 40 RS 只有两个包：`HarmonyOS3.0.0`(2023-08-01) 与 `11.0.0.150`/EMUI11(2021-01-19) |
| 关键字 `Mate 40` | 9 个包，覆盖 NOP / NOH / OCE，**无一为 4.x** |
| 关键字 `HarmonyOS4` | **totalRows = 99** —— 华为确实发布 4.x 源码，但**不包含 Mate 40 系列** |

结论：**Mate 40 系列从来没有 4.x 源码**。4.x 只发给其它机型（Mate 60 / MatePad / nova 等）。

## 关键验证：HM3 与 HM4.2 的 rtmutex.c 完全相同

| 样本 | 来源 | MD5 | 字节 |
|---|---|---|---|
| HarmonyOS 3.0.0 | NOP-AN00 官方包 / GitHub 镜像 | `8A810CE9FFEB6D4D828311DE3C17BB04` | 53327 |
| HarmonyOS 4.2 | 麒麟 9010 MRO-W00（`HK416AAA/android_kernel_huawei_kirin9010`，2026-10-25 更新） | `8A810CE9FFEB6D4D828311DE3C17BB04` | 53327 |
| HarmonyOS 4.2 | 麒麟 9000S（`HK416AAA/HUAWEI_Kirin9000S_Kernel`） | `8A810CE9FFEB6D4D828311DE3C17BB04` | 53327 |
| vanilla 5.10.43 对照 | gregkh/linux | `9281A3E5339917B2F58788C8BDD52403` | 52091 |

→ 华为在 HM3.0 → HM4.2 之间**没有动过这个文件**；`remove_waiter()` 一直是漏洞形态。
→ 所以用 HM3 包判断**这段逻辑**是成立的；但结构体偏移、符号地址、驱动差异**不能跨版本套用**。

## 想要 HM4.x 源码的话（其它机型，仅供交叉参考）

| 机型 | 包 | 版本 | 日期 | 大小 | 直链 |
|---|---|---|---|---|---|
| Mate 60（ALN-AL00/AL10/AL80/AL10P，麒麟 9000S） | `ALN-AL00,ALN-AL80,ALN-AL10,ALN-AL10P_HarmonyOS4.2.0` | HarmonyOS 4.2.0 | 2026-10-29 | 575.17 MB | https://download-c1.huawei.com/download/downloadCenter?downloadId=7172D1AAF0FCA7881B284327AC1A6AE2&version=07635D29D2D0530FA28FDA892556CE86&siteCode=worldwide |
| SGT-LX9 | `SGT-LX9_HarmonyOS4.3.2` | HarmonyOS 4.3.2 | **2026-07-28**（最接近你内核构建日 2026-08-20） | 597.49 MB | 走 JSON 接口取 `downloadUrl` |
| MRO-W00（麒麟 9010） | GitHub 镜像，免下 575MB | HarmonyOS 4.2 opensource | 2026-10-25 | — | https://github.com/HK416AAA/android_kernel_huawei_kirin9010 |

直接看单个文件（不用下整包）：
`https://raw.githubusercontent.com/HK416AAA/android_kernel_huawei_kirin9010/master/kernel/locking/rtmutex.c`

## 一个容易误判的仓库

`yunsmall/DBY-W09_kernel_hack`（绕过 MatePad 11 / HarmonyOS 4.2 内核模块签名验证）——它做的事是 **binary patch 原版内核**（`mod_verify_sig` 直接返回 0、`is_module_sig_enforced` 改 MOV W0,#0），然后刷进去。**前提是能刷内核 = 已解锁 BL**。你这台 `flash.locked=1`，用不上；但它的 patch 点清单说明了华为的签名链在哪几个函数上，做分析时可以参考。
