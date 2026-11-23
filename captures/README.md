# captures/

抓包样本目录。

## 文件

| 文件 | 说明 |
|---|---|
| `sample-20261106.txt` | HiSuite 17.0.0.100 一次完整「系统更新 → 检查更新」的 TLS 明文（已脱敏） |

## 脱敏规则

上传的样本经过以下处理，**结构完整、内容可复现**，但设备标识已移除：

| 原始字段 | 替换为 |
|---|---|
| 设备序列号 | `<DEVICE_SERIAL>` |
| UDID | `<UDID>` |
| `/sdkv2` 的 `ed` / `ek` 长 hex | `<ENCRYPTED_DATA>` / `<ENCRYPTED_KEY>` |
| CDN 路径中的 v3 token | `<TOKEN>` |
| 请求 ID `req[...]` | `<REQ_ID>` |
| `x-amz-request-id` / `X-Cdn-Request-ID` | `<CDN_REQ_ID>` |
| 主机名 / 用户名 / 绝对路径 | 已移除 |

保留原文的部分：HTTP 方法、路径、Host、响应头结构、`filelist.xml` 全部内容（文件名/大小/MD5/SHA256）、内核 banner —— 这些是可复现性所需，且不随设备变化。

## 自己抓一份

```powershell
frida -f "C:\Program Files (x86)\HiSuite\HiSuite.exe" -l ../tools/hook_ssl.js -o my_capture.log
# 在 HiSuite 里点「系统更新」→「检查更新」
python ../tools/parse_capture.py my_capture.log --grep dbankcdn --body
```

拿到 `filelist.xml` 后按 README 里的规则拼出下载地址。

**注意**：`filelist.xml` 的 CDN 响应头带 `X-CCDN-Expires: 600`，约 10 分钟过期，过期需重新抓。
