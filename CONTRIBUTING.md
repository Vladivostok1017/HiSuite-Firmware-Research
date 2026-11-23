# 贡献指南

## 欢迎的内容

| 类型 | 说明 |
|---|---|
| **机型 / 版本报告** | 用 [机型报告模板](../../issues/new?template=device-report.md) 提交某个 HiSuite 版本 + 设备的组合是否走得通 |
| **新 HiSuite 版本适配** | 某个版本的网络层发生变化（DLL 名、导出、是否还在用 OpenSSL）时，更新 `docs/01-architecture.md` |
| **文档订正** | 发现的错误、过时结论、更精确的证据 |
| **工具改进** | `tools/` 下的脚本更健壮、更通用 |

## 硬性要求

### 1. 必须脱敏

提交任何日志、抓包、截图前，替换掉：

- 设备序列号、UDID、IMEI
- 请求 ID、CDN 请求 ID
- 主机名、用户名、绝对路径
- CDN 路径里的 v3 token（会过期，且与账号无关，但统一替换为 `<TOKEN>`）

参考 `captures/README.md` 的脱敏规则。

### 2. 不提交版权内容

- **不要**把 OTA 包、`UPDATE.APP`、`boot.img`、内核 `Image` 传进仓库或 issue
- **不要**为这些文件提供网盘/磁力链接
- 可以提交的是：文件名、大小、MD5/SHA256、版本号、banner 文本——这些是可复现性所需的元数据

### 3. 结论要带强度标注

沿用现有文档的习惯：

- **确证** — 有二进制偏移 / 抓包原文 / 日志原文支撑
- **强推测** — 有多条间接证据，但缺直接观测
- **推测** — 单条线索
- **未解** — 如实登记，不编

`docs/02-hisuite-binary-analysis.md` §8.5 有一个"未解/存疑项"表单，照那个格式加。

## 代码风格

- `tools/*.py` — Python 3.8+，标准库优先，不引第三方依赖
- `tools/*.ps1` — PowerShell 7 优先，参数化，默认值指向项目内相对路径
- `tools/*.js` — Frida 17 兼容；对 Frida 新旧 API 差异做 try 回退

所有源码文件头部保留 `SPDX-License-Identifier: GPL-3.0-or-later`。

## 提交

```
<类型>: <一句话>

类型: docs / tools / findings / fix
```

例：

```
findings: 补充 HUAWEI XXX 的 TrustList 通过记录
tools: carve_kernel.py 支持非 gzip 内核段
```
