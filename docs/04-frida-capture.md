# 04 · 用 Frida 抓 HiSuite 的 TLS 明文

HiSuite 用 OpenSSL 3 + 内嵌 CA 做 TLS，装系统证书没用。但既然 TLS 在**进程内**解密，直接 hook OpenSSL 的读写函数就能拿到明文——不碰证书、不搭代理、不改任何文件。

---

## 原理

```
HiSuite.exe
  └─ httpcomponent.dll           ← 发起请求
       └─ libssl-3.dll           ← ★ TLS 加解密在这一层
            ├─ SSL_write(buf, n)  ← 明文从这里进 TLS
            └─ SSL_read(buf, n)   ← 明文从这里出 TLS
```

在 `SSL_write` 的 `onEnter` 读 `buf`，在 `SSL_read` 的 `onLeave` 读 `buf`，拿到的都是**已解密/未加密的 HTTP 原文**。

---

## 用法

```powershell
# 1. 装 Frida
pip install frida-tools

# 2. 杀掉已有 HiSuite（否则 -f spawn 会失败）
Stop-Process -Name HiSuite -Force -ErrorAction SilentlyContinue

# 3. 带 hook 启动
cd <本项目目录>
frida -f "C:\Program Files (x86)\HiSuite\HiSuite.exe" -l tools/hook_ssl.js -o capture_out.log
```

启动后手动操作 HiSuite（比如进「系统更新」点「检查更新」），流量会实时打印并落盘。

**成功标志**（第一行输出）：

```
==== HOOKED: SSL_write,SSL_write_ex,SSL_read,SSL_read_ex,SSL_CTX_set_verify @ ... ====
[set_verify mode=1]
[WRITE len=1256]
POST /sdkv2 HTTP/1.1
...
```

---

## Frida 17 的坑

### 1. `--no-pause` 已被移除

旧教程里的 `frida -f ... --no-pause` 在 Frida 17 会报：

```
frida: error: unrecognized arguments: --no-pause
```

新版默认**不暂停**（spawn 后自动 resume），只有显式加 `--pause` 才停在入口。所以直接去掉该参数即可。

### 2. `Memory.readByteArray` 返回的 ArrayBuffer 不能直接 `new Uint8Array()`

会抛 `TypeError: not a function`。改用：

```js
// 首选：直接读 UTF-8 字符串（HTTP 是文本）
ptr.readUtf8String(size)

// 兜底：Frida 内置 hexdump
hexdump(ptr, { length: size, ansi: false })
```

`tools/hook_ssl.js` 里已经做了三层回退（`readUtf8String` → `Memory.readUtf8String` → `hexdump`）。

### 3. 模块可能延迟加载

`libssl-3.dll` 不一定在进程启动瞬间就在。脚本用 `setInterval(hookAll, 500)` 轮询，且用 `hooked` 标志防止重复 attach（否则每秒打一行 `HOOKED`，日志会被刷爆）。

### 4. 动态库地址要用 `Module.getExportByName`

Frida 17 移除了 `Module.prototype.findExportByName`。脚本里对两种写法都做了 try 回退：

```js
try { Module.getExportByName('libssl-3.dll', nm); }
catch (e) { mod.findExportByName(nm); }
```

---

## 实测输出样例

完整样本见 [`../captures/sample-20261106.txt`](../captures/sample-20261106.txt)。核心片段：

```http
[WRITE len=698]
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

[READ len=396]
HTTP/1.1 200 OK
Content-Type: application/xml; charset=utf-8

<?xml version="1.0" encoding="UTF-8"?>
<root><status>1</status></root>
```

以及关键的固件清单请求：

```http
[WRITE len=285]
GET /download/data/pub_13/HWHOTA_hota_900_9/<xx>/v3/<token>/full/filelist.xml HTTP/1.1
Host: update.dbankcdn.com

[READ len=1983]
HTTP/1.1 200 OK
Content-Type: application/xml
Content-Length: 1182
Last-Modified: ...
Accept-Ranges: bytes

<?xml version="1.0" encoding="utf-8"?>
<root>
<vendorInfo name="base" logfile="changelog_base.xml" package="update_full_base.zip" precut_size="0"/>
<GROUP version="G6.0"/>
<files>
<file>
<spath>update_full_base.zip</spath>
<md5>13AE2CC8B1347248D094D8F473BFD119</md5>
<sha256>5B285878B0217E866E21B4E14B617A60160082EC6F35BB29BAFBE37D522759BD</sha256>
<size>5683825610</size>
</file>
...
```

注意响应头里有 `Accept-Ranges: bytes` —— 说明 CDN 支持断点续传，大包可以分段下载。

---

## 触发要点

抓不到固件清单，通常是这两个原因：

1. **设备在 fastboot** → 走 rescue 通道 → TrustList 拒 → 查询请求根本没发出去
   - 解决：让设备回正常系统，HiSuite 重新识别后再点「系统更新」
2. **点的是「系统修复」而不是「系统更新」** → 同一条 rescue 通道
   - 解决：正常系统下「系统修复」通常是灰的，能点开就说明设备处于 rescue 态

判据：抓包/s 日志里出现 `packageType:full` 就说明通道对了。

---

## 替代方案对比

| 方案 | 是否可用 | 原因 |
|---|---|---|
| **Frida hook OpenSSL** | ✅ | 进程内明文，无需证书 |
| 装系统根证书 + mitmproxy | ❌ | 内嵌 51 个 CA，不读系统库 |
| DLL 劫持 `libssl-3.dll` | ✅（较重） | 转发全部导出 + hook，需枚举导出表 |
| patch `httpcomponent.dll` 的 `SSL_CTX_set_verify` | ✅（需改文件） | 改 `mode=1` → `0`，但改动官方 DLL |
| Wireshark / pcap | ⚠️ 部分 | 只能看到域名/SNI/字节数，看不到内容 |
| 替换内嵌 CA bundle | ✅（需改文件） | 51 段 PEM 是明文，可注入自己的 CA |
