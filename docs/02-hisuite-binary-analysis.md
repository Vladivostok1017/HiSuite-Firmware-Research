# HiSuite 14.0.0.380 系统修复/刷机逻辑静态分析

- 分析对象：`C:\Program Files (x86)\HiSuite\`（14.0.0.380，PE32，ImageBase=0x400000）
- 用户数据：`%USERPROFILE%\AppData\Local\HiSuite\`
- 分析方式：**纯静态**。未运行 HiSuite / uninst.exe / 任何同目录可执行文件；未调用 adb / fastboot / hdc；未修改注册表、证书、hosts；未联网。
- 证据分级：**确证**（引到具体字符串 + 所在文件偏移/反汇编地址/日志原文）、**强推测**（多处间接证据一致但无直接代码确认）、**无法判断**。

---

## 0. 先给结论（TL;DR）

| 问题 | 结论 | 强度 |
|---|---|---|
| 固件下到哪 | `Documents\HiSuite\ROM\`（可被 `Setting.ini [updatefirmware] romdir` 改写），内部再挂 `...\full\cloud_rom\{lfapp,language,rom_feature,app_bundle}` | 确证 |
| 文件名/临时后缀 | 下载中为 `<最终名>.dbk`，完成后改为最终名；扩展名有 `.xml` / `.zip` / `UPDATE.APP`；**不是** `.part` | 确证（`.dbk` 来自日志，其余来自代码字符串） |
| 单包还是分片 | **多文件/多分片**：`full/filelist.xml` 描述一批文件，每个带 `spath`/`dpath`/`size`/`sha256`，逐个下载；失败会报 `Download part zip file fail.` | 确证 |
| 下完会删吗 | **会删**。存在专门的删除例程（日志 `Delete ROM [%s]`）+ 持久化删除队列 `UpdateDogDev/toDeleteROM.dat` | 确证（有删除代码与队列文件）／删除**时机**为强推测 |
| 校验失败就删？ | 代码里有 `sha256 not match.` / `md5 not match.` / `get file's sha256 fail.` 分支，但**没有证据表明校验失败会删文件** | 无法判断 |
| 能只下载不刷写吗 | **没有**“只下载”的配置项或命令行开关。但存在 `已下载完成，5秒后自动安装` 倒计时 + `立即安装` 按钮 → 下载完成到开刷之间只有约 5 秒窗口 | 确证（字符串）／窗口可操作性为强推测 |
| 日志里有 URL 吗 | **完全没有**。全部 14 个 `.log` 中 `https?://` 匹配数为 **0** | 确证 |
| 协议/鉴权 | HTTPS + 内置 CA 包（httpcomponent.dll 内嵌 30+ `-----BEGIN CERTIFICATE-----`）+ `query.hicloud.com` + `/sp_ard_common/v1|v2/*.action` + `authorize`/`updateToken`/`deviceToken` | 确证 |
| packageType | `full`=当前完整包；`full_back`=版本回退包（附 `_EmotionUI_11.0.0`）；`hfull_switch`=切换包（`isSwitchHm`） | 确证（字符串+日志）／语义细节为强推测 |

---

## 1. 目录与组件

### 1.1 安装目录顶层（只列与刷机相关）

| 文件 | 大小 | 推测职责 |
|---|---|---|
| `HiSuite.exe` | 11,054,336 | 主程序（PE32）。**sysupdate / ROM / 删除 / 下载路径逻辑全部在此** |
| `FirmwareUpdate.dll` | 3,297,536 | 固件升级底层（DUT 读写、`Read data from DUT Fail!`、`Can't Upgrade from Retail Version to Product Version!`），不含 ROM 目录字符串 |
| `CommBase.dll` | 2,804,992 | 通讯/日志框架。`CLog::GetLog`、`CLog::Success_Format` 在此，所有 `HiSuite_SystemUpdate` 日志都经它 |
| `httpcomponent.dll` | 183,552 | HTTP/HTTPS 客户端。**内嵌 CA 证书包**、`CONNECT ...:443`、`.hicloud.com`、`User-Agent: HiSuite` |
| `AppBase.dll` | 143,104 | 应用框架、`_tgetopt`（命令行解析） |
| `DuiLib_ext.dll` | 545,536 | DuiLib DirectUI 皮肤引擎（界面是 XML 皮肤，不是 Qt） |
| `minizip.dll` / `zlib.dll` | 45,824 / 83,712 | ZIP 解压（ROM 包解压用） |
| **`hwtools\fastboot.exe`** | 14,553,088 | **fastboot 工具（刷写阶段使用）** |
| **`hwtools\hdbtransport.exe`** | 14,661,688 | HDB（华为调试桥）传输 |
| **`hwtools\hwtransport.exe`** | 15,263,272 | 华为传输协议 |
| `cmddict.ini` | 22,289 | AT 命令字典（**与刷机无关**，是备份/联系人等 AT 指令模板） |
| `UrlInfo.ini` | 265 | 服务器地址表（见下） |
| `SysConfig.dat` | 528 | 安装配置（快捷方式名等），无刷机内容 |
| `checkfile.dat` | 58,987 | APK 完整性清单（`APK\HiSuite.apk=<签名哈希>`） |

> 注意：**它不是 Qt 程序**。没有 `Qt5Core.dll`/`Qt6Core.dll`，界面由 `skin\hisuite\*.xml` + DuiLib 驱动，中文文案在 `language\Language_zh-rCN.xml`。

### 1.2 `UrlInfo.ini`（确证，原文）

```ini
[setting]
bi_report=https://data.hicloud.com
club=https://club.huawei.com
main=https://www.huawei.com
consumer=https://consumer.huawei.com
consumer_download=https://consumer-tkbdownload.huawei.com
update=https://query.hicloud.com
bl_update=https://query.hicloud.com
```

`bl_update`（bootloader 更新）与 `update` **同为主机 `query.hicloud.com`** —— 说明版本查询、鉴权、BL 校验走同一台。

### 1.3 `hwtools` 的存在本身就是证据

`fastboot.exe` 与 `hdbtransport.exe` 被打包进安装目录，说明刷写阶段 HiSuite 会**调用本地 fastboot 向设备下发分区镜像**。本次未运行它们（遵守约束）。

---

## 2. 下载落地与文件命名

### 2.1 ROM 下载根目录 —— 确证

**证据链（HiSuite.exe 反汇编）：**

1. `SettingLogic::GetRomDir` 位于 `0x6527B0`。函数开头：

```
006527E1  push 0xac89f0        ; "ROM"
006527E6  mov eax,[ebp-0x264]  ; this
006527EC  add eax,0x1c
006527EF  push eax
006527F0  lea ecx,[ebp-0x230]
006527F6  call 0x560230        ; <模块默认路径> + "ROM"
0065280C  call 0x51b080        ; wstring::c_str()
00652812  call [0x914f5c]      ; SHLWAPI!PathFileExistsW
```

2. 同目录下的模块默认路径表（宽字符串，偏移 0x6C7854 起）为：
   `backup` / `Screenshot` / **`ROM`** / `Download` / `ExportSMS` / `ExportContact`，由
   `SettingLogic::GetSettingModuleDefaultPath`（0x6C78A0 有对应日志串）统一定位。

3. `HiSuite.exe` 导入 `SHELL32!SHGetFolderPathW`（IAT `0x914F38`）——即用 **CSIDL_PERSONAL（“我的文档”）** 解析基目录，再拼 `HiSuite\ROM`。

4. 磁盘侧实证：`%USERPROFILE%\Documents\HiSuite\ROM\` **确实存在**（创建于 2026-11-04 15:26:16，正是第一次 ROM 查询时刻），且为空。

**结论**：默认 = `%USERPROFILE%\Documents\HiSuite\ROM`。

### 2.2 该目录可以被改写 —— 确证

`HiSuite.exe` 在 `0x652B89` 处：

```
00652B89  push 0xac8cc0   ; "romdir"
00652B8E  push 0xac8ca0   ; "updatefirmware"
00652B94  call [0x914af0] ; KERNEL32!WritePrivateProfileStringW
```

即写入 **`Setting.ini` 的 `[updatefirmware] romdir=`**。
对应 UI 文案（`language\Language_zh-rCN.xml` 第 221 行，确证）：

```xml
<item textid="IDS_SETTINGUPGRADE_ROMDIRECTORY">ROM下载目录</item>
```

而当前 `Setting.ini` 里**没有** `[updatefirmware]` 段（只有 `[system]`/`[selfupdate]`/`[SystemPrivacyStatement]`），说明用户从未改过 → 走默认路径。

### 2.3 ROM 下载子目录结构 —— 确证

`HiSuite.exe` 函数 `0x6B2FE0` 负责拼下载路径，关键序列：

```
006B3012  call 0x6a0bd0        ; 取管理器单例
006B3017  add eax,0x188        ; cloudRom 版本字段
006B301E  call 0x517350
006B3023  test eax,eax
006B302A  push 0xb648b4        ; "cloudRom baseVersion is empty"   ← 失败即返回
...
006B30A9  push &[ebp-0x40]
006B30AD  mov ecx,[ebp-0x14c]
006B30B3  call 0x6b22b0        ; ← GetRomDir()：内部依次 call 0x650e10 / 0x6527b0
006B30C6  call 0x52a360        ; 追加 baseVersion
006B30D8  call 0x549040
006B30F6  push 0xb64920        ; "\full\cloud_rom"
006B3106  call 0x528550        ; 拼接
006B311A  push 0xb64b9c        ; "\lfapp"
```

其余同级子目录字符串（确证，ASCII/宽串）：

```
\lfapp        \language        \rom_feature     \app_bundle
full/cloud_rom/lfapp/lfapp.xml
full/cloud_rom/language/language.xml
full/cloud_rom/rom_feature/rom_feature.xml
full/cloud_rom/app_bundle/app_bundle.xml
/data/update/cloud_rom/rom_feature/
/data/update/cloud_rom/app_bundle/
/data/update/cloud_rom/lfapp/
/data/update/cloud_rom/language/
```

**落地形态**（强推测，由上述字符串唯一合理的组合）：

```
%USERPROFILE%\Documents\HiSuite\ROM\
  └─ <cloudRom baseVersion>\
      └─ full\
          ├─ filelist.xml              ← 分片清单
          ├─ cloud_rom\
          │   ├─ lfapp\lfapp.xml
          │   ├─ language\language.xml
          │   ├─ rom_feature\rom_feature.xml
          │   └─ app_bundle\app_bundle.xml
          └─ ...                        ← 各分片 zip / UPDATE.APP
```

### 2.4 文件名规则与临时后缀 —— 确证

**`.dbk` 是下载中的临时后缀（确证，日志原文）**，来自 `Download_20261104_00.log`：

```
[fn=3] pTmsg=WokerThreadMsg tempPathName=%USERPROFILE%\AppData\Local\HiSuite\
        userdata\LiveUpdateHisuite\full\changelog.xml.dbk
        error_code=200 error_app=11008 httpclient_error=0 start=0 size=447 finish=447
[sn=1] Download::OnNotifySlice ... destPathName=C:\...\LiveUpdateHisuite\full\changelog.xml
        httperrorcode=200 ... errorcode=11008, m_taskid=4
[fn=6] CDownloadSegment::OnOK() ok Download::EndWithDownloadError false1 ...
[sn=2] donwload file OK , ... destPathName=...\changelog.xml
```

即：**先写 `<目标名>.dbk`，完成后落成 `<目标名>`（去掉 `.dbk`）**。这是同一个下载引擎（`downloadxx` / `CDownloadSegment` / `DownloadSlice`），ROM 下载走同一套 → ROM 分片也应是 `.dbk`。
全库检索：`.part`、`.tmp` 后缀**均无**；`.tmp` 仅出现在无关的 `%s%s%X.tmp` 格式化串。

**扩展名**（确证字符串）：
- `.zip` → `update.zip`、`full/update.zip`、`/update.zip`、`\update.zip`
- `.xml` → `changelog.xml`、`filelist.xml`、`{lfapp,language,rom_feature,app_bundle}.xml`
- `UPDATE.APP` / `\UPDATE.APP` → 华为标准固件聚合镜像名
- `changelog_base_<...>_sxk.xml` → 由 `changelog_base_` + `_sxk` + `.xml` 三段拼成
- `maxStashInfo`、`ataprecut_size`、`precut_size`、`fulldatafile`、`logfile` → 包内元数据字段

### 2.5 单文件还是多分片 —— 确证

下载清单来自 `filelist.xml`，字段（宽字符串，0x6C3AB0–0x6C3C10 与 0x764200–0x764500）：

```
components → component → file
  name, size, sha256, spath, dpath, operation, compress, versionID, version, createtime
```

分片语义由下列日志串确认（确证）：

```
Download part zip file fail.
Download all zip file suc.
start downcloudrom taskId: %d
DownloadFileEnd get taskid: %d
Already Finish FileSize %llu, Alread Report Progress is %d
```

`Download all zip file suc.` 这一句直接证明：**是“一包多 zip”分片下载，全部完成后才报整体成功。**

### 2.6 预计多大 —— 部分无法判断

- 版本查询日志里每次都有 `SaleInfo:|cn|porsche|N|EmotionUI_14.2.0|**8.6 GB**||8_3.1GHz`（**确证，日志原文**）。该字段含义未在代码中定位到解析逻辑，**不能确证它就是包体大小**（也可能是机型规格位）。→ **无法判断**。
- 代码里存在 `romsize` 字段（0x762E88，与 `partitionName`、`value`、`packagetype` 相邻）与 `rom_feature` 清单，说明真实大小由服务端 XML 下发，静态无法预知。
- 参考：本次日志显示 C: 剩余 118 GB（`Free Disk:118001MB`），HiSuite 已做磁盘余量检查（`IDS_SYSTEMUPDATE_COMPUTERDISKSPACESHORTAGE`=电脑磁盘空间不足、`IDS_UPDATE_LACKOFSPACEFREESOMESTORAGESPACETRYAGAIN`）。

---

## 3. 缓存生命周期：何时删、删什么

### 3.1 存在一个专门的“删 ROM”例程 —— 确证

**日志格式串（确证）**：`HiSuite.exe` 文件偏移 `0x763428`：

```
Delete ROM [%s]
```

**引用它的代码（确证）**：VA `0x6B48BD` → `push 0xb64e28 ; "Delete ROM [%s]"`。

该函数起始于 `0x6B47B0`，结构（反汇编节选）：

```
006B47DE  mov ecx,[ebp-0x74]
006B47E1  call 0x6b4770        ; ← 前置守卫（见 3.3）
006B47EB  je 0x6b4956          ;   守卫为假 → 整个删除流程直接跳过
006B47F1  call 0x650e10
006B47F8  call 0x6527b0        ; ← SettingLogic::GetRomDir()，取 ROM 根目录
...
006B4846  mov ecx,[ebp-0x74]
006B4849  add ecx,0x4c8        ; 待删清单容器
006B484F  call 0x6bd450        ;   at(i)
006B4854  add eax,0x30         ;   元素里的 wstring（文件名）
006B4870  call 0x528380        ;   [romdir] + [name] → 完整路径
006B48BD  push 0xb64e28        ;   "Delete ROM [%s]"
006B490F  call [0x91410c]      ;   CLog::Success_Format(...)   ← 打印被删路径
006B4921  push ecx
006B4922  call 0x69d080        ;   ← 真正执行删除
```

**要点**：删除是**按 `GetRomDir()` 拼出的绝对路径逐个文件进行**，且每个被删文件都会以 `Delete ROM [<路径>]` 写入 `SystemUpdate` 日志。也就是说——**如果你打开 `SystemUpdate_*.log` 搜 `Delete ROM`，就能直接看到被删文件的完整路径。** 本次日志里搜索结果为 0 条，说明本次会话**从未删除过任何 ROM 文件**（与 ROM 目录为空一致）。

### 3.2 持久化删除队列 `toDeleteROM.dat` —— 确证

磁盘实证：

```
%USERPROFILE%\AppData\Local\HiSuite\userdata\UpdateDogDev\toDeleteROM.dat
  长度 0 字节，LastWriteTime 2026-11-04 18:14:41
```

代码实证：宽字符串 `UpdateDogDev/toDeleteROM.dat` 在 `HiSuite.exe` 中出现 **13 处**（偏移 0x6C3A74、0x6C44A4、0x6FA0CC、0x730604、0x73AF10、0x7424A8、0x748CC8、0x74F7CC、0x75A7B8、0x7612FC、0x76A190、0x799B20、0x8B4D70），其中 `0x7612FC` 被代码在 **VA `0x4150D4`** 处引用（`push 0xb62cfc`），属于文件路径类构造。

读取侧实证（VA `0x69D080`，被 `0x6B4922` 与 `0x7422CF` 调用）：

```
0069D103  lea ecx,[ebp-0x440]
0069D10A  lea ecx,[ebp-0x678]
0069D110  call 0x69d660        ; ifstream 构造
0069D136  call 0x4e40d0        ; 清空结果容器
0069D145  push 0
0069D147  push 0x400
0069D14C  lea eax,[ebp-0x410]
0069D152  push eax
0069D159  call [0x914e58]      ; std::istream::getline(char*, 1024)
0069D17F  test eax,eax
0069D181  je 0x69d1bc          ; 读完退出
0069D1A6  call 0x5256d0        ; 每行 push_back
```

**结论（确证）**：`toDeleteROM.dat` 是一个**纯文本、一行一个绝对路径**的“待删 ROM 文件清单”。文件 0 字节＝清单为空。

> 实现细节（强推测）：它放在 `UpdateDogDev\`（本是 HiSuite 自升级的 dogfood 目录）而非 ROM 目录，属于复用同一个 `userdata` 路径助手的写法。

### 3.3 删除的前置守卫 —— 强推测

`0x6B47B0` 开头调用 `0x6B4770`：

```
006B4770  push ebp / mov ebp,esp / sub esp,8
006B4779  mov ecx,[ebp-8]      ; this
006B477C  add ecx,0x298
006B4782  call 0x517350        ; 取某个 bool 成员
006B478A  test eax,eax
006B478C  jne 0x6b4797
006B478E  mov [ebp-4],1        ; 返回 true
...
006B4797  mov [ebp-4],0        ; 返回 false
```

同一形状的守卫在 `0x6B301E` 也出现，并在下一句就打印 `cloudRom baseVersion is empty`。因此 `0x517350` 极可能是**“该字段是否非空/是否有效”的布尔判定**。→ 删除只在“ROM 记录有效”时执行。**强推测**。

### 3.4 删除用到的 Win32 API —— 确证（导入表）

```
0x914B4C  KERNEL32.dll!DeleteFileW
0x914B0C  KERNEL32.dll!RemoveDirectoryW
0x914F30  SHELL32.dll!SHFileOperationW     ← 递归删除用
0x914AD8  KERNEL32.dll!SetFileAttributesW  ← 删前清只读属性
0x914B24  KERNEL32.dll!GetFileAttributesW
```

---

### 3.5 **明确回答：“下完就删还是会留？”**

- **会删**（确证）：有 `Delete ROM [%s]` 专用日志、有 `toDeleteROM.dat` 持久删除队列、有 `DeleteFileW`/`RemoveDirectoryW`/`SHFileOperationW`。
- **删除发生在哪个阶段** → **强推测：刷写结束之后**。依据：
  1. 删除函数位于 SystemUpdate 模块，与 `Enter BL SystemFull` 流程同处一片代码（0x6B3xxx–0x6B4xxx）。
  2. UI 文案顺序为 `解压`(IDS_ROMUPDATE_UNZIP) → `安装`(IDS_ROMUPDATE_INSTALLATION) → `刷机完成`(IDS_ROMUPDATE_BRUSHCOMPLETION)，删除不在这些文案里，说明是**后台收尾动作**而非用户可见步骤。
  3. `toDeleteROM.dat` 是“延迟删除”队列 —— 这种设计的典型用途是：**刷写/重启阶段文件被占用，先记下来，下次启动或本进程稍后统一删**。这解释了为什么它落在 `userdata` 而不是 ROM 目录。
- **“校验失败就删”有没有？** → **无法判断**。代码里确实有校验分支（确证）：
  ```
  Check MD5 suc. / Check MD5 fail.
  md5 match. / md5 not match. / get file's md5 fail.
  sha256 match. / sha256 not match. / get file's sha256 fail.
  ```
  但我没有在反汇编中证明“校验失败 → 调用删除”。从设计直觉上更可能是“校验失败 → 重下/报错”，不做过度断言。

---

## 4. 下载 → 刷写的阶段划分

### 4.1 阶段全景（按字符串与日志重建）

| # | 阶段 | 确证依据 |
|---|---|---|
| 1 | 取设备信息（udid/IMEI/deviceId/plmn/C_Version/D_version/DashBoard/DeviceName） | 日志 `GetInfoPKI=true`；字段串 `imei`/`deviceId`/`udid`/`plmn`/`deviceCertificate`/`keyAttestation` |
| 2 | 向 `query.hicloud.com` 查版本 | `Host: `、`/sp_ard_common/v2/onestopCheck.action?latest=true&verType=true`、`Content-Type:application/json;charset=UTF-8` |
| 3 | BL 鉴权 | `/BL/v1/VersionCheck`、`/BL/v1/Authorize`、`/BL/v1/CheckAndAuthorize`、`/sp_ard_common/v1/authorize.action`、`updateToken`/`deviceToken`/`authorizeResult` |
| 4 | 解析 `versionList` / `updatePackages` / `versionPackageType` | 日志 `reader parse format ok.` / `Parse versionList ok.` / `ValidBlVersionCheckResult ok.` |
| 5 | 取 `filelist.xml` 与 `changelog.xml` | 串 `full/filelist.xml`、`changelog.xml`、`GetHmOSXmlInfo [%s]`；日志 `full_back have new version.` |
| 6 | **下载分片**（`.dbk` → 正式名） | `start downcloudrom taskId: %d`、`Download part zip file fail.`、`Download all zip file suc.` |
| 7 | **MD5/SHA256 校验** | `Check MD5 suc.`/`fail.`、`sha256 match.`/`not match.` |
| 8 | 解压 | `UpZipUpdateFile`、`UnzipReadOneFileValue`、`UPDATE.APP`、`\UPDATE.APP` |
| 9 | 进 bootloader / 刷写 | 日志 `Enter BL SystemFull.`；`hwtools\fastboot.exe`；`ROM\boot_asi.bin`、`bootAsi result failed`、`GetAsiEnable=[0]`、`asi off, not asi version` |
| 10 | 提示重启 | `IDS_SYSUP_SUCCESS`=升级完成，是否重启手机切换到新系统？；`IDS_SYSTEMUPDATE_DEVICEISRESTARTED`=设备正在重启... |
| 11 | 删除缓存 | `Delete ROM [%s]`、`toDeleteROM.dat` |

### 4.2 “只下载不刷写”的卡点 —— 有，但很窄（确证 + 强推测）

**存在明确倒计时（确证字符串，`language\Language_zh-rCN.xml`）：**

```xml
第 227 行 <item textid="IDS_UPDATE_DOWNLOADISCOMPLETEDAUTOMATICINSTALLATIONAFTER5SECONDS">已下载完成，5秒后自动安装</item>
第 228 行 <item textid="IDS_UPDATE_INSTALLNOW">立即安装</item>
第 236 行 <item textid="IDS_UPDATE_DOWNLOAD_IS_COMPLETED_AUTOINSTALL">下载完成，%1秒后自动安装</item>
第 1168-1172 行 同名 _ZERO/_TWO/_MANY/_FEW/_OTHER 复数变体（均为 %1 秒）
```

说明：**下载完成后不是立刻开刷，而是有一个可被“立即安装”提前触发的自动倒计时**（默认 5 秒，因存在 `%1` 变体故秒数可被代码传入）。

**但“只下载不刷写”的开关并不存在（确证）：**

- 命令行只有 getopt 的两个选项。`HiSuite.exe` 内 optstring 字面量为 **`L::f:`**（VA `0x5D9724`），配套日志串：
  ```
  option L value %s
  option f value %s
  HiSuite30: Wrong Command line arg!!!
  non-option ARGV-elements:
  ```
  即只有 `-L <可选值>` 与 `-f <值>`，**没有任何 `--download-only`、`/rom`、`-rom` 之类开关**。
- 检索 `onlydownload|OnlyDownload|downloadonly|DownloadOnly|autoinstall|AutoInstall|autoupdate|silent` → **0 命中**。
- `Setting.ini` 现有段仅 `[system] autolaunch`、`[selfupdate] visible/version`、`[SystemPrivacyStatement]`。**没有**“只下载”“自动安装”之类的键。

**唯一可用的配置面（确证）**：`Setting.ini` 的 `[updatefirmware] romdir` —— 能改**下到哪**，不能改**下完干什么**。

**其他用户可见的“中断点”（确证）+ 风险（强推测）：**

```xml
IDS_SYSTEMUPDATE_SWITCH_WARNING      此操作可能会清除手机数据，是否继续？
IDS_SYSTEMUPDATE_SWITCH_WARNING_TITLE 温馨提示
IDS_SYSTEMUPDATE_SD_ENCRYPT_WARNING  此操作可能会清除手机数据，并导致本手机加密过的SD卡上的文件无法使用，是否继续？
IDS_ROMUPDATE_WARRING                请确保所刷的ROM为华为官方版本，否则有可能导致手机损坏或数据丢失的风险！
IDS_ROMUPDATE_WARNINGVERSION         刷机前请检查更新详情，以免ROM版本不匹配，导致更新失败。
IDS_ROMUPDATE_CANCEL                 退出刷机？
IDS_SYSTEMUPDATE_EXIT                退出系统更新?
IDS_ROMUPDATE_NOTFOUNDROM            未发现适用于设备的ROM！
```

→ 在真正下发镜像前，UI 有确认弹窗（`是否继续？`）。这是**唯一语义上安全的“卡点”**：在弹窗处不点“继续”，此时包已落盘、尚未刷写。

**另有“本地 ROM”入口（确证）**：

```xml
IDS_ROMUPDATE_LOCATIONROM   打开本地ROM>>
IDS_ROMUPDATE_ROM           ROM包
IDS_ROMUPDATE_DOWNLOADLOCATION  下载位置：
```

说明 HiSuite 支持**从本地选择一个已存在的 ROM 包**（再解压→安装）。这是把“拿到包”和“刷机”解耦的官方途径。

---

## 5. URL 可观测性

### 5.1 日志里有没有 URL —— 确证：**没有**

对 `%USERPROFILE%\AppData\Local\HiSuite\log\` 下全部 14 个 `.log`（含 `Adb.log` 1.74 MB / 67,720 行、`SystemUpdate_20261104_00.log` 382 行、`Download_20261104_00.log`）做 `https?://[^\s\]]+` 全量匹配：

```
Adb.log                              → 0 处
SystemUpdate_20261104_00.log         → 0 处
Download_20261104_00.log             → 0 处
（其余 11 个 .log）                   → 0 处
合计                                  → 0 处
```

`Adb.log` 对 `ROM` / `packageType` / `rescue` / `SystemFull` / `hfull` / `full_back` / `.zip` / `.dbk` / `cloud_rom` / `UPDATE.APP` 的**大小写敏感**匹配同样是 **0 处**（`Adb.log` 全是 AT 命令与传输层流水，与刷机无关）。

`Download_*.log` 里唯一的地址是**本地路径**：

```
localPath=%USERPROFILE%\AppData\Local\HiSuite\userdata\LiveUpdateHisuite\full\changelog.xml
tempPathName= ...\changelog.xml.dbk
destPathName= ...\changelog.xml
```

——而且那是 **HiSuite 自身升级**（`taskType=202`，`LiveUpdateHisuite`），**不是设备固件**。

### 5.2 代码里存在“打印 URL”的日志串，但不在本次走的路径上

确证（宽字符串）：

```
Download url:                       (0x751B98)
Http Request value=[%s]             (0x751A9C)
%s result body=[%s]                 (0x751A04)
IsConnectHttp.Info,s:[%s]p=[%d]     (0x75193C)
push "                              (0x751C1C)
Download System Update Package Failed,the error code is %d
```

这一片的邻居是 `UpdateDev\full\`、`update.zip`、`Check MD5 suc./fail.` —— 属于**旧版 `update.zip` 系统更新通道**。
结论：**若走 `update.zip` 通道，URL 会以 `Download url:` 打到 `HiSuite_SystemUpdate` 日志；本次走的是 `cloud_rom` 分片通道，日志中没有 URL。** → **强推测**：cloud_rom 通道不记录 URL。

### 5.3 协议与鉴权 —— 确证

**主机与端点（确证字符串）：**

```
query.hicloud.com                                              (HiSuite.exe 0x702FC4)
/sp_ard_common/v1/authorize.action
/sp_ard_common/v2/onestopCheck.action?latest=true&verType=true
/sp_ard_common/v2/CheckAndAuthorize.action?latest=true&verType=true
/sp_ard_common/v2/CouplingReport.action
/sp_ard_common/v2/UpdateReport.action
/BL/v1/VersionCheck
/BL/v1/Authorize
/BL/v1/CheckAndAuthorize
```

**HTTPS + 内嵌信任锚（确证，`httpcomponent.dll`）：**

```
0x00022654  Host:
0x00022638  CONNECT 
0x00022644  :443 HTTP/1.1              ← 使用 CONNECT 隧道 = TLS
0x00022884  https://
0x00022890  HTTPS://
0x00022838  .hicloud.com               ← 域名后缀白名单
0x00022794  User-Agent: HiSuite
0x000147F0  -----BEGIN CERTIFICATE-----   （>30 段内嵌 CA 证书）
```

`httpcomponent.dll` 自带 CA 包意味着 **HiSuite 用内置信任锚校验 `*.hicloud.com`，不依赖系统证书库**（这也解释了“装证书”类操作对它是无效的）。

**设备侧签名/鉴权字段（确证字符串）：**

```
authorize, authorizeResult, updateToken, deviceToken, keyAttestation,
deviceCertificate, authVendor, reserveUrl, storageType, nonce, Read nonce:
/BL/v1/CheckAndAuthorize  → authorizeResult
QueryResponseParse::SetBlHttpsHeader _snprintf_s failed   ← "Bl"=BootLoader 专用 HTTPS 头
```

**判断**：请求是 **HTTPS + 设备证书 + 服务端下发的临时 `updateToken`/`authorizeResult` 双因子**；`reserveUrl` 表明真实下载地址由服务端在响应里给出（因此大概率是**短时效直链**，静态抓不到、也难长期复用）。→ 协议本身**确证**；“短时效直链”为**强推测**。

---

## 6. `packageType` 含义（full / hfull_switch / full_back）

### 6.1 三种包在日志中的原文对照（确证）

同一次查询会对**同一设备连续查 3 次，每次带不同 `packageType`**（`SystemUpdate_20261104_00.log` 第 6–81 行）：

```text
************************* full *************************
*    VendorCountry:porsche-cn
*    C_Version:C786          D_version:D000
*    DashBoard:41.003.53.00.06
*    DeviceName:NOP-AN01P
*    packageType:full
*    FirmWare_Base:NOP-LGRP1-CHN 104.2.0.196
*    FirmWare_Cust:NOP-AN01P-CUST 104.2.0.182(C786)
*    FirmWare_Preload:NOP-AN01P-PRELOAD 104.0.0.6(C786R8)
*    SaleInfo:|cn|porsche|N|EmotionUI_14.2.0|8.6 GB||8_3.1GHz

************************* hfull_switch *************************
*    packageType:hfull_switch
*    FirmWare_Base:NOP-LGRP1-CHN 104.2.0.196
*    FirmWare_Cust:NOP-AN01P-CUST 104.2.0.182(C786)
*    FirmWare_Preload:NOP-AN01P-PRELOAD 104.0.0.6(C786R8)     ← 与 full 完全相同

************************* full_back *************************
*    packageType:full_back
*    FirmWare_Base:NOP-LGRP1-CHN 104.2.0.196_EmotionUI_11.0.0
*    FirmWare_Cust:NOP-AN01P-CUST 104.2.0.182(C786)_EmotionUI_11.0.0
*    FirmWare_Preload:NOP-AN01P-PRELOAD 104.0.0.6(C786R8)_EmotionUI_11.0.0
                                                            ↑ 独有后缀
```

以及最关键的一行（第 96–97 行，确证）：

```
[DATA1: full_back have new version.]
[DATA1: Enter BL SystemFull.]
```

### 6.2 逐一定义

| packageType | 含义 | 证据强度 |
|---|---|---|
| **`full`** | **完整包（当前系统版本的完整镜像）**。Base/Cust/Preload 三段版本号齐全，无后缀。这是“完整包”的正解 | **确证**（字符串 `full`、`pkgtype`/`full`、`full/filelist.xml`、`full_back need three version info.` 反证） |
| **`hfull_switch`** | **“切换包”**：`h` = hybrid/切换，与 `full` 的**目标固件完全相同**（三个版本号逐字一致），差别在于用途是**跨大类切换**（HarmonyOS ↔ EMUI）而非版本升级。代码里的判定标志位是 **`isSwitchHm`**（0x763798），UI 文案对应 `IDS_SYSTEMUPDATE_SWITCHVERSIONALREADYPAGE`=切换到其他版本 | 版本一致=**确证**；语义=**强推测**（`isSwitchHm` + UI 文案高度一致） |
| **`full_back`** | **版本回退包**（`back` = 回退）。三段版本号带 `_EmotionUI_11.0.0` 后缀，明确指向回退到 EMUI 11 基线。UI 文案 `IDS_SYSTEM_VERSIONBACK_*`=回退完成/回退提示，`FirmWare:NOP-AN01P 4.2.0.196(C786E182R8P6)` 出现在 full_back 记录里 | **确证**（后缀 + UI 文案 + 日志 `full_back have new version.`） |

### 6.3 相关但不同的类型（确证字符串，说明类型是个开放枚举）

```
full_recovery            → "full_recovery need three version info."（三分量恢复包）
rollback                 → 回滚
recovery                 → 恢复
restrictedRecovery       → 受限恢复
notify_custom_001.xml    → 定制提示
```

→ **`full_recovery` 才是“救援模式”真正对应的包类型**（本次日志的 `IsRescueMode return rescue_version: rescue0.8` 说明设备处于救援态，但查询返回的仍是 `full/full_back`，未出现 `full_recovery`）。

---

## 7. 可执行建议

> 前提：**在不刷机、不变砖的前提下，把 4.2.0.196 完整包拿到手**。

### 7.1 最短路径（推荐顺序）

**方案 A —— 改 ROM 下载目录 + 下载完成瞬间截获（最稳，不改任何程序）**

1. 不启动 HiSuite。先手工在 `%USERPROFILE%\AppData\Local\HiSuite\userdata\Setting.ini` 里写入**新的**下载目录（此键已被代码确证存在）：
   ```ini
   [updatefirmware]
   romdir=D:\hisuite_rom
   ```
   （不写也可以，默认就是 `Documents\HiSuite\ROM`，同样有效。）
2. 用**文件系统监控**盯住该目录（PowerShell `FileSystemWatcher` 或轮询），一旦出现 `<name>.dbk` 立即 `Copy-Item` 到另一个盘的独立目录，**复制不是移动**，不改动任何原文件、不改属性。
3. 在 UI 出现 `是否继续？` / `请确保所刷的ROM为华为官方版本…` 弹窗时**点“取消/否”**，然后正常退出 HiSuite（**不要**在刷写进度条出现后中断）。
4. 拿到的可能就是 `.dbk` 形态的分片；先按 `filelist.xml` 里的 `name`/`size`/`sha256` 逐个改名与校验。

**方案 B —— 用官方“本地 ROM”入口（最安全，但需要先有包）**

`IDS_ROMUPDATE_LOCATIONROM`=“打开本地ROM>>” 说明 HiSuite 可以加载用户指定的本地包。这条路径的价值是：**包一旦拿到，后续“解压→安装”可以完全由你控制节奏，不依赖下载阶段**。

**方案 C —— 只观察不取包（零风险）**

把 `log\SystemUpdate_*.log` 的日志级别调到最详细后跑一次查询（不下载）。查询阶段就会打印三个 packageType 的完整 FirmWare 三段版本号与 `SaleInfo`，这已经能确认“4.2.0.196 完整包”的目标标识；`changelog.xml` 里通常含 `romsize`。**不产生任何刷写风险。**

### 7.2 性能/成本提示

- 包体疑似接近 `8.6 GB` 量级（**未确证**），请预留 ≥20 GB 目标盘空间；HiSuite 自身会检查磁盘余量。
- ROM 是**一包多 zip 分片**，截获要盯整个目录树，不能只盯一个文件名。

### 7.3 **绝对不要做**（每条都对应一个确证的危险面）

1. **不要运行 `HiSuite.exe` 时加 `-f` / `-L` 参数去“试探”**。optstring 是 `L::f:`，语义未知（`option f value %s`）；乱传参可能直接进入某个自动化流程。日志串 `HiSuite30: Wrong Command line arg!!!` 说明它对错误参数只是报警告，不会安全退出。
2. **不要在刷写进度出现后中断 HiSuite / 拔 USB / 关电脑**。此时 `hwtools\fastboot.exe` 正在向分区写镜像，中断即变砖高风险。
3. **不要手动删除或编辑 `toDeleteROM.dat`**。它是 HiSuite 的删除队列；往里塞内容等于让它“按你给的路径去删文件”，是明确的破坏面。
4. **不要修改 `Documents\HiSuite\ROM` 里已下载的文件**。存在 `sha256 not match.` 校验分支，改动会让包作废（是否触发删除未知）。
5. **不要试图用“装 CA 证书”来抓包**。`httpcomponent.dll` 内嵌了自己的 CA 包（30+ 段 `-----BEGIN CERTIFICATE-----`），**不读系统证书库**，装证书既无效也违反本次约束。
6. **不要执行 adb / fastboot / hdc 任何命令**，包括只读的 `fastboot devices`——设备当前处于救援态，tool 与设备握手本身就可能改变状态机。
7. **不要删 `userdata\UpdateDogDev\` 目录**。除删除队列外，`HiSuiteConfig.xml`/`UpdateInfo.dat`/`UserInfo.ini` 也在这里，`[UpdateStrategy] Strategy=never` 说明它被刻意配成不自动升级，删了可能触发意外行为。

---

## 8. 证据附录

### 8.1 关键字符串（文件偏移为 HiSuite.exe 内偏移；VA = 0x400000 + RVA）

| 字符串 | 文件偏移 | 类型 | 意义 |
|---|---|---|---|
| `Delete ROM [%s]` | 0x763428 | A | 删除 ROM 的日志格式串 |
| `UpdateDogDev/toDeleteROM.dat` | 0x7612FC 等 13 处 | W | 待删 ROM 清单文件 |
| `SettingLogic::GetRomDir memcpy_s failed` | 0x6C7050 / 0x6C7440 | W | ROM 目录读取函数 |
| `SettingLogic::SetRomDir wcscpy_s failed` | 0x6C7528 | W | ROM 目录写入函数 |
| `romdir` | 0x6C72C0 / 0x6C7404 | W | **Setting.ini 键名** |
| `updatefirmware` | 0x6C72A0 / 0x6C73E4 | W | **Setting.ini 段名** |
| `Setting.ini` | 0x6C70A0 / 0x6C73CC | W | 配置文件 |
| `ROM` | 0x6C6FF0 / 0x6C7854 | W | 默认目录名 / 模块名 |
| `SettingLogic::GetSettingModuleDefaultPath memcpy_s failed` | 0x6C78A0 | W | 模块默认路径 |
| `\full\cloud_rom` | 0x762F20 | A | ROM 下载子路径 |
| `\lfapp` / `\rom_feature` / `\app_bundle` | 0x76319C / 0x7631B0 / 0x7631C0 | A | cloud_rom 子目录 |
| `\language` | 0x7631A4 | A | cloud_rom 子目录 |
| `full/filelist.xml` | 0x762E50 | A | 分片清单 |
| `changelog.xml` | 0x761AB0 | A | 变更日志/版本描述 |
| `changelog_base_` / `_sxk` / `.xml` | 0x763418 / 0x7633FC / 0x76340C | A | 拼接式文件名 |
| `UPDATE.APP` / `\UPDATE.APP` | 0x76448C / 0x764604 | W | 固件聚合镜像名 |
| `update.zip` / `/update.zip` / `\update.zip` | 0x751998(W) / 0x751D54(W) / 0x752334(W) | W | 旧系统更新包名（另有 A 副本 0x751C44/0x751C54） |
| `Download part zip file fail.` | 0x7631CC | W | 分片下载失败 |
| `Download all zip file suc.` | 0x763508 | W | 全部分片成功 |
| `start downcloudrom taskId: %d` | 0x763394 | W | ROM 下载任务启动 |
| `Download url:` | 0x751B98 | W | **URL 日志格式串（本次路径未触发）** |
| `Check MD5 suc.` / `Check MD5 fail.` | 0x751B0C / 0x751D34 | W | MD5 校验结果 |
| `sha256 match.` / `sha256 not match.` | 0x7643A8 / 0x7642D0 | W | SHA256 校验结果 |
| `get file's sha256 fail.` | 0x76434C | W | 校验计算失败 |
| `md5 match.` / `md5 not match.` | 0x76428C / 0x764574 | W | MD5 比对 |
| `cloudRom baseVersion is empty` | 0x762EB4 | W | 版本缺失即中止 |
| `romsize` `partitionName` `value` `packagetype` | 0x762E88–0x762EA8 | A | 包元数据字段 |
| `components` `component` `file` `name` `size` `sha256` `spath` `dpath` `operation` `compress` | 0x6C3ABC–0x6C3C10 | A | **下载清单字段（spath=源, dpath=目标）** |
| `isSwitchHm` | 0x763798 | A | hfull_switch 判定 |
| `full_back` / `V1.0` / `V1.1` | 0x763A90 / 0x763D00 | A | 回退包标识 |
| `full_recovery need three version info.` | 0x764048 | A | 恢复包需三分量 |
| `maxStashInfo` `ataprecut_size` `precut_size` `fulldatafile` `logfile` | 0x7635AC–0x7644D0 | A | 包内/日志元数据 |
| `Enter BL SystemFull.` | 日志串 | W | 进入 bootloader 全量刷写 |
| `ROM\boot_asi.bin` | 0x6E7C0C | W | ASI 引导文件（本地） |
| `bootAsi result failed` / `bootAsi_fb result failed` | 0x6E7D1C / 0x6E7D34 | A | ASI 引导结果 |
| `GetAsiEnable=[%s]` | 0x6E7D7C | A | ASI 开关查询 |
| `asi off, not asi version` | 日志串 | W | ASI 未启用 |
| `Read nonce:` / `nonce_fb result failed` | 0x6E7E64 / 0x6E7E70 | A | 挑战-应答 |
| `query.hicloud.com` | 0x702FC4 | A | **更新服务器** |
| `/BL/v1/VersionCheck` `/BL/v1/Authorize` `/BL/v1/CheckAndAuthorize` | 0x761AC0–0x76247C | A | BL 鉴权端点 |
| `/sp_ard_common/v1/authorize.action` | 0x761930 | A | 授权端点 |
| `/sp_ard_common/v2/onestopCheck.action?latest=true&verType=true` | 0x7618F0 | A | 一站式版本查询 |
| `/sp_ard_common/v2/CheckAndAuthorize.action?latest=true&verType=true` | 0x762498 | A | 校验并授权 |
| `/sp_ard_common/v2/CouplingReport.action` | 0x76148C | A | 耦合关系上报 |
| `/sp_ard_common/v2/UpdateReport.action` | 0x7618C0 | A | 升级结果上报 |
| `updateToken` / `deviceToken` / `authorizeResult` / `reserveUrl` / `storageType` | 0x76240C / 0x761F24 / 0x762418 / 0x761AE8 | A | 鉴权与下载地址字段 |
| `QueryResponseParse::SetBlHttpsHeader _snprintf_s failed` | 0x7031F8 | W | BL 专用 HTTPS 头 |
| `UpdateDev\full\` / `UpdateDev/full/` | 0x7519B8 / 0x751C24 | W | 旧 update.zip 工作目录 |
| `GetSystemUpdateDevicePath set_required_size = %I64d` | 0x752070 | W | 空间需求日志 |
| `L::f:` | 0x5D9724 | W | **命令行 optstring（仅 -L/-f）** |
| `HiSuite30: Wrong Command line arg!!!` | 0x5D97D8 | W | 参数错误提示 |
| `MODULE_ROM` | CommBase.dll 0x18AC91 | A | 模块名 |
| `.hicloud.com` / `hicloud` | httpcomponent.dll 0x22838 / 0x22854 | A | 域名后缀白名单 |
| `CONNECT ` / `:443 HTTP/1.1` | httpcomponent.dll 0x22638 / 0x22644 | A | TLS 隧道 |
| `-----BEGIN CERTIFICATE-----` | httpcomponent.dll 0x147F0 起 30+ 处 | A | **内嵌 CA 信任锚** |

### 8.2 关键代码位置（HiSuite.exe，ImageBase=0x400000，PE32）

| VA | 内容 |
|---|---|
| `0x6527B0` | `SettingLogic::GetRomDir` —— `push "ROM"` → 拼默认路径 → `PathFileExistsW` |
| `0x652B89` / `0x652B8E` | `push "romdir"` / `push "updatefirmware"` → `call [0x914AF0]` = `WritePrivateProfileStringW` |
| `0x6534BC` | `push "ROM"`（模块默认路径版本） |
| `0x6B2FE0` | cloud_rom 路径构造函数；`0x6B302A` 打印 `cloudRom baseVersion is empty`；`0x6B30F6` 拼 `\full\cloud_rom`；`0x6B311A` 拼 `\lfapp` |
| `0x6B22B0` | 取 ROM 根目录（内部 `call 0x650e10` → `call 0x6527B0`） |
| **`0x6B47B0`** | **删 ROM 主函数**：`0x6B47E1` 守卫 → `0x6B47F8` GetRomDir → 循环 → `0x6B48BD` 打印 `Delete ROM [%s]` → `0x6B4922` 执行删除 |
| `0x6B4770` | 删除前置布尔守卫（读 `this+0x298`） |
| `0x69D080` | 读 `toDeleteROM.dat`（ifstream + `getline` 循环，每行入容器） |
| `0x69D660` | ifstream 构造 |
| `0x4150D4` | `push "UpdateDogDev/toDeleteROM.dat"` |
| `0x7422CF` | UI_handler 内调用 `0x69D080`（DuiLib `itemclick` 通知上下文，`0x7422A9` `SendNotify`） |
| `0x6E7C0C` | `ROM\boot_asi.bin`（ASI 引导） |
| `0x7031F8` | `SetBlHttpsHeader` |
| `0x5D9730`–`0x5D9870` | `CommandLineToArgvW` + getopt 参数解析 |

### 8.3 导入表关键项（HiSuite.exe）

```
0x914ADC  KERNEL32!GetPrivateProfileStringW
0x914AF0  KERNEL32!WritePrivateProfileStringW     ← romdir 读写
0x914B4C  KERNEL32!DeleteFileW
0x914B0C  KERNEL32!RemoveDirectoryW
0x914AD8  KERNEL32!SetFileAttributesW
0x914B24  KERNEL32!GetFileAttributesW
0x914B3C  KERNEL32!GetFileAttributesExW
0x914AC8  KERNEL32!FindFirstFileA
0x914AEC  KERNEL32!FindFirstFileW
0x914B98  KERNEL32!CopyFileW
0x914B20  KERNEL32!CreateFileW
0x914F30  SHELL32!SHFileOperationW                ← 递归删除
0x914F38  SHELL32!SHGetFolderPathW                ← Documents 定位
0x914F5C  SHLWAPI!PathFileExistsW
0x914188  CommBase!CLog::GetLog
0x91410C  CommBase!CLog::Success_Format
0x91419C  CommBase!CLog::Success_Format（wchar 变体）
0x914334  DuiLib_ext!CDuiString::operator=
0x914744  DuiLib_ext!CPaintManagerUI::SendNotify
```

### 8.4 日志时间线（2026-11-04，`SystemUpdate_20261104_00.log`，GBK 编码）

| 时间 | 事件 |
|---|---|
| 15:00:19 | `GetInfoPKI=true`，输出 `packageType:full` 全量设备信息 |
| 15:02:07 | `WaitForMultipleObjects` / `IsRescueMode return`（**空**，未进救援态） |
| 15:26:14 | 第二次查询：`full` |
| 15:26:14 | → `hfull_switch` |
| 15:26:15 | → `full_back`（带 `_EmotionUI_11.0.0`） |
| 15:26:15 | `GetAsiEnable=[0]` → `bootAsi result failed` → `asi off, not asi version` |
| 15:26:15 | `devD[s_xxx_n],devM[NOP-AN01P],req[B01767C2ABD54077A4837370B2DB2777]` |
| 15:26:15–16 | `reader parse format ok.` / `Parse versionList ok.` / `ValidBlVersionCheckResult ok.` / `parse TargetBlComponents ok.` / `Parse blVersionCheckResults ok.` / `status ok` |
| 15:26:16 | `localFullBase is:G6.0 localFullCust is:G6.0 localFullPreload is:G6.0`；`localPartBaseGbc is:NA`；`localPartBaseGbp is:NA` |
| 15:26:16 | **`Documents\HiSuite\ROM` 目录被创建**（文件系统时间） |
| 15:26:17 | **`full_back have new version.`** → **`Enter BL SystemFull.`** |
| 15:26:18 | 第二次 `req[7FF806953010BD9A5469B8198C482F7A]` → `reader parse format ok.` → **`invalid`** |
| 17:54:14 | `full_back have new version.` / `Enter BL SystemFull.` |
| 17:55:24 | `GetInfoPKI=false`；`GetDeviceFileContent msg == nullptr.`；`GetSupplementPreloadBatch msg == nullptr.`；`GetProbufPKI pMsg == nullptr.`；`GetUpdateAuthInfo msg == nullptr.` |
| 17:55:26 | `localFullBase is:G6.0…` → **`full_back have new version.`** → **`Enter BL SystemFull.`** |
| 17:55:30 | `bootAsi message = nullptr` → `asi off, not asi version` |
| **18:14:41** | **`userdata\UpdateDogDev\toDeleteROM.dat` 被写为 0 字节**（删除队列被清空/初始化） |
| 18:14:43 | `IsRescueMode return rescue_version: rescue0.8` + `Finished. Total time: 0.068s`（**此时确认处于救援模式**） |

`Download_20261104_00.log`（14:58:42–14:58:43）只有一条 HiSuite **自身升级**下载任务：

```
taskid=4  taskType=202  LiveUpdateHisuite\full\changelog.xml
  tempPathName=...changelog.xml.dbk   (447 字节)
  destPathName=...changelog.xml       httperrorcode=200  errorcode=11008
  → donwload file OK
```

### 8.5 未解/存疑项（如实登记）

| 项 | 状态 |
|---|---|
| ROM 包实际大小 | **无法判断**（`SaleInfo` 的 `8.6 GB` 含义未在代码中定位） |
| 删除是否仅发生在刷写成功之后 | **强推测**（无直接分支证明） |
| “校验失败即删除” | **无法判断**（有校验分支，无删除关联证据） |
| `hfull_switch` 的精确语义 | **强推测**（`isSwitchHm` + UI “切换到其他版本” + 与 full 版本号完全一致） |
| `-f` / `-L` 参数的具体作用 | **无法判断**（只确证存在这两个选项） |
| 5 秒倒计时的实际取值 | **强推测**（默认 5 秒；存在 `%1` 变体说明可被配置） |
| cloud_rom 通道是否记录 URL | **强推测为“不记录”**（日志 0 命中，但 `Download url:` 串存在于另一通道） |

---

## 附：本次使用的自建工具（可重复运行）

均位于 `%USERPROFILE%\Downloads\22\20261104\diag\tools\`，纯只读、静态：

| 脚本 | 用途 |
|---|---|
| `strx.py` | 任意文件 ASCII + UTF-16LE 可打印字符串提取，带文件偏移（`--min/--enc/--grep/--out`） |
| `sfind.py` | 对提取结果做**大小写敏感**正则检索（`--dir/--regex/--enc/--max/--only-files`） |
| `peutils.py` | 最小 PE 解析（PE32/PE32+、节表、`off_to_va` / `va_to_off`） |
| `pexref.py` | 定位指向某 VA 的代码引用（PE32 绝对寻址 + PE32+ RIP 相对） |
| `pfindcall.py` | 定位指向某函数的直接 `call`/`jmp` 站点 |
| `pdis.py` | 反汇编指定 VA 区间，自动注解 IAT 导入与字符串 |
| `peimports.py` | 解析导入表，输出 `IAT VA → DLL!函数名` 映射 |

复现示例：

```powershell
$py="F:\python313\python.exe"; $t="...\diag\tools"
$exe="C:\Program Files (x86)\HiSuite\HiSuite.exe"
& $py "$t\pdis.py"   $exe 6B47B0 6B4970        # 看删 ROM 函数
& $py "$t\pexref.py" $exe B64E28               # 找 "Delete ROM [%s]" 引用点
& $py "$t\peimports.py" $exe --what 914AF0     # 确认 romdir 写入用的是 WritePrivateProfileStringW
& $py "$t\strx.py" $exe --min 2 --enc both --out dump.txt
& $py "$t\sfind.py" --dir . --regex "toDeleteROM|cloud_rom" --enc AW
```
