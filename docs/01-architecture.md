# 01 · HiSuite 架构与网络层

> 对象：HiSuite `17.0.0.100`，安装路径 `C:\Program Files (x86)\HiSuite`
> 方法：静态扫描（字符串/导入表）+ 运行时 hook（Frida）

---

## 1. 目录与关键组件

```
HiSuite/
├── HiSuite.exe              12,863,216   主程序（PE32/x64，Qt）
├── httpcomponent.dll           201,968   ★ 网络层：内嵌 CA + OpenSSL
├── libssl-3.dll              1,054,960   OpenSSL 3（TLS）
├── libcrypto-3.dll           4,106,480   OpenSSL 3（密码学）
└── hwtools/
    ├── hwtransport.exe      15,263,272   华为自有传输（自带 OpenSSL）
    ├── hdbtransport.exe     14,661,688   HDB 传输
    ├── hdc.exe               4,891,520   HarmonyOS 调试桥
    └── fastboot.exe         14,573,256   刷写工具
```

`hwtools/` 的存在本身就说明 HiSuite 具备完整刷机能力——它会调用这些工具进 fastboot 读写分区。

---

## 2. 网络层：为什么装系统证书抓不到包

对 `httpcomponent.dll` 的字符串扫描：

| 特征 | 计数 | 含义 |
|---|---|---|
| `-----BEGIN CERTIFICATE-----` | **51** | 内嵌 CA bundle，明文 PEM |
| `SSL_CTX_set_verify` | 1 | 证书校验入口 |
| `SSL_get_verify_result` | 1 | 校验结果读取 |
| `hicloud` | 2 | 华为云域名 |
| `libssl` | 1 | 动态链接 OpenSSL |

运行时 hook 确认：

```
[SSL_CTX_set_verify mode=1]      ← SSL_VERIFY_PEER，校验证书链
```

**结论**：TLS 校验用的是 OpenSSL + 内嵌 51 个 CA，**不读 Windows 证书库**（`certmgr.msc` 里装的根证书对它无效），所以 mitmproxy/Fiddler 的常规套路（装系统 CA）行不通。

可行路径见 [`04-frida-capture.md`](04-frida-capture.md)：直接 hook OpenSSL 的读写函数，绕开证书问题。

---

## 3. 已观测到的接口

全部来自一次「系统更新 → 检查更新」的完整抓包（2026-11-06）。

| 方法 | Host | 路径 | 内容形态 | 用途 |
|---|---|---|---|---|
| POST | `data.hicloud.com:6447` | `/sdkv2` | `{"vs":"1.0","ed":"<hex>","ek":"<hex>"}` **二次加密** | 行为/设备信息上报 |
| POST | `query.hicloud.com` | `/sp_dashboard_global/UrlCommand/CheckNewVersion.aspx?latest=true` | **明文 XML** | HiSuite 自身版本检查 |
| POST | `query.hicloud.com` | `/sp_ard_common/v2/CheckAndAuthorize.action?latest=true&verType=true` | 加密 | ★ 设备固件查询 |
| POST | `query.hicloud.com` | `/BL/v1/CheckAndAuthorize` | 加密 | bootloader 授权（rescue 通道） |
| GET | `update.dbankcdn.com` | `/download/data/pub_13/HWHOTA_hota_900_9/<xx>/v3/<token>/full/filelist.xml` | **明文 XML** | ★ 固件清单 |
| GET | 同上 | `.../full/changelog_base.xml` | **明文 XML** | 更新说明 / 版本描述 |

**关键点**：查询接口的请求体是加密的（`ed`+`ek`），但**响应的清单是明文 XML**。所以只需要看到响应，不需要解密请求。

### 请求样例（HiSuite 自身更新检查，明文）

```http
POST /sp_dashboard_global/UrlCommand/CheckNewVersion.aspx?latest=true HTTP/1.1
Host: query.hicloud.com
Content-Type: application/x-www-form-urlencoded

<?xml version="1.0" encoding="UTF-8"?>
<root>
    <rule name="DashBoard">54</rule>
    <rule name="DeviceName">HiSuiteConfig</rule>
    <rule name="FirmWare">Hisuite_17.0.0.100</rule>
    <rule name="OS"> Windows 10 Enterprise 6.3 </rule>
    <rule name="PackageType">China</rule>
</root>
```

响应：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<root><status>1</status></root>
```

---

## 4. TrustList：两条通道的分水岭

同一台设备，两条入口的结果完全不同：

| 通道 | 触发条件 | 日志特征 | 结果 |
|---|---|---|---|
| **系统修复**（rescue / fastboot） | 设备在 `FASTBOOT & RESCUE MODE` | 有 `IsRescueMode rescue0.8` + `fb success oem getencryptudid` | ❌ `The device is not in the TrustList.` |
| **系统更新**（正常系统 / adb） | 设备正常开机、HiSuite 已识别 | **没有** `IsRescueMode`、**没有** `fb` 命令 | ✅ 直接返回 `packageType: full / hfull_switch / full_back` |

所以：

- 走 rescue 通道 → 先做 TrustList 鉴权 → 不在白名单就**连查询请求都不发**
- 走正常通道 → 不做 TrustList → 直接查 → 能拿到清单

**这也是为什么在 fastboot 下抓不到任何固件请求**：它在发请求前就被本地逻辑拦住了。

---

## 5. 本地配置面

`%LOCALAPPDATA%\HiSuite\userdata\Setting.ini`：

```ini
[system]
autolaunch=1
[selfupdate]
visible=1
version=14.0.0.380
[SystemPrivacyStatement]
IsAuthorized=1
AuthorizedDate=...
UpdateDate=2022-07-15
```

- `[selfupdate] version` 记录的是**曾经自更新过的版本**，不代表当前实际版本（实际版本看 `SystemUpdate_*.log` 头部的 `[HiSuite version: ...]`）
- 固件下载目录由 `[updatefirmware] romdir` 控制（默认 `%USERPROFILE%\Documents\HiSuite\ROM`），该键默认不存在，写入即生效

---

## 6. 日志体系

```
%LOCALAPPDATA%\HiSuite\log\
├── SystemUpdate_YYYYMMDD_NN.log    ★ 固件更新全流程（含 packageType / FirmWare / Enter BL）
├── Adb.log                          设备检测（hwtransport devices / hdb / hdc / rndis）
├── DataCollection_*.log             数据采集
├── PhoneHomeUI_*.log                主界面
└── Adb*.zip                         日志轮转归档
```

`SystemUpdate_*.log` 是最有价值的一份：它会把三个 packageType 的完整 `FirmWare_Base` / `FirmWare_Cust` / `FirmWare_Preload` 三段版本号逐行打出来，即使抓不到网络包，也能据此确认目标固件版本。

日志级别字段 `Current Log Level: S3_DEFAULT_KEY`，调到更详细也不会打印 URL（`Download url:` 这个格式串存在，但 cloud_rom 分片通道不触发它）。
