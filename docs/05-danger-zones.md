# 05 · 危险面清单

以下每一条都对应一个**已确证的破坏路径**。做固件研究时只读不写，这些坑就不会踩。

---

## A. 会变砖的操作

### 1. 不要在刷写进度出现后中断

一旦 `SystemUpdate_*.log` 出现 `Enter BL SystemFull.` 且 HiSuite 界面开始走进度，此时 `hwtools\fastboot.exe` 正在向分区写镜像。断 USB、关 HiSuite、关机、断电，都会造成分区残写。

**红线判定**：日志出现 `Enter BL SystemFull.` 之前必须决定好要不要继续。

### 2. 不要在救援态执行 adb / fastboot 命令

设备处于 `FASTBOOT & RESCUE MODE` 时，连只读的 `fastboot devices` 都可能改变状态机。要退出就让 HiSuite 走完流程，或长按电源 10 秒。

### 3. 不要相信"降级无害"

`full_back` 包（回退到 EMUI / 旧 HarmonyOS）会**擦除全部用户数据**，且跨大版本回退后可能触发：
- 基带/快充/USB 异常
- 部分机型 fastboot 被禁

包里 `changelog` 自己写着：「回退操作将擦除所有用户数据」。

### 4. 不要手改包内文件

HiSuite 对已下载文件做 **SHA256 校验**（`sha256 not match.` 分支存在）。改了包等于让校验失败，是否触发删除未知。

---

## B. 会破坏 HiSuite 状态的操作

### 5. 不要手动编辑或删除 `toDeleteROM.dat`

这是 HiSuite 的**待删 ROM 清单**，纯文本、一行一个绝对路径。往里塞内容等于让它"按你给的路径去删文件"。

### 6. 不要删 `userdata\UpdateDogDev\`

里面是 `HiSuiteConfig.xml` / `UpdateInfo.dat` / `UserInfo.ini`。`[UpdateStrategy] Strategy=never` 说明它被刻意配成不自动升级，删了会触发意外行为。

### 7. 不要用 `-f` / `-L` 参数试探 `HiSuite.exe`

optstring 是 `L::f:`，语义未明（`option f value %s`）。错误参数只会打印 `Wrong Command line arg!!!` 然后继续跑，可能直接进某个自动化流程。

---

## C. 无效但常见的尝试

### 8. 装系统根证书抓包 —— 无效

`httpcomponent.dll` 内嵌 51 个 CA 且不读 Windows 证书库。装 `certmgr` 里的根证书对它不起作用。正确做法是 Frida hook（见 `04-frida-capture.md`）。

### 9. 等日志打印 URL —— 等不到

`Download url:` 这个格式串确实存在于 `HiSuite.exe`（字符串偏移 0x751B98），但走 `cloud_rom` 分片通道时不触发。日志里从头到尾没有 URL。

### 10. 试图"只查询不下载"拿到包 —— 拿不到

「系统更新」查询阶段只会打印三个 `packageType` 的版本号，不会给下载地址。`filelist.xml` 是在**下载阶段**才去请求的。所以必须让它走到下载。

---

## D. 通道选择的坑

### 11. fastboot 下抓不到固件请求

rescue 通道会先做 `TrustList` 鉴权，不在白名单就**连查询都不发**。此时抓包只能看到 `/sdkv2` 上报和 HiSuite 自身更新检查，会让人误以为"HiSuite 不查固件"。

**正确通道**：设备正常开机 + HiSuite 已识别 + 点「系统更新」。

### 12. 「系统修复」正常系统下是灰的

如果「系统修复」能点开，说明 HiSuite 认为设备处于救援态——这时它走的是 TrustList 通道。

---

## E. 数据层面的坑

### 13. 同版本号 ≠ 同构建

实测：`4.2.0.196` 在 CDN 上的 base 包内核是 `2024-04-26` 编译，而设备实跑 `2026-08-20` 编译。同版本号、同工具链、同构建机，但**是两次编译**。

拿包内内核做符号/偏移研究前，**必须先验 banner**：

```powershell
python tools/carve_kernel.py update_full_base.zip work
# 输出里的 banner 行必须与设备 `uname -a` 的构建时间一致
```

### 14. `filelist.xml` 有时效

响应头 `X-CCDN-Expires: 600`，大约 10 分钟。过期后需要重新抓一次查询。

### 15. `filelist.xml` 只是清单，不是包

它给的是 `<spath>` 文件名 + 大小 + 校验值。完整地址要按 `https://update.dbankcdn.com/download/data/pub_13/HWHOTA_hota_900_9/<xx>/v3/<token>/full/<spath>` 拼出来。`<token>` 来自抓到的 `filelist.xml` 请求路径本身。
