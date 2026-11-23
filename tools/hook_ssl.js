// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 HiSuite-Firmware-Research contributors
//
// hook_ssl.js —— 在 HiSuite 进程内 hook OpenSSL 3，输出 TLS 明文
//
// 用法:
//   frida -f "C:\Program Files (x86)\HiSuite\HiSuite.exe" -l tools/hook_ssl.js -o capture_out.log
//
// 说明:
//   - 不写文件，输出走 console.log，由 frida 的 -o 参数落盘
//   - libssl-3.dll 可能延迟加载，脚本每 500ms 轮询一次
//   - Frida 17 去掉了 --no-pause（默认不暂停），且 Module.prototype.findExportByName
//     被移除，这里对两种 API 都做了回退
'use strict';

function readStr(p, n) {
  var max = Math.min(n, 16384);
  // 1) 直接读 UTF-8（HTTP 是文本，最常用）
  try { var s = p.readUtf8String(max); if (s && s.length) return s; } catch (e) { }
  // 2) 静态 API
  try { var s2 = Memory.readUtf8String(p, max); if (s2) return s2; } catch (e) { }
  // 3) 兜底：hexdump
  try { return hexdump(p, { length: max, ansi: false }); } catch (e) { }
  return '<unreadable>';
}

var hooked = false;

function hookAll() {
  if (hooked) return;
  var mod = Process.findModuleByName('libssl-3.dll');
  if (!mod) return;

  function exp(nm) {
    try { return Module.getExportByName('libssl-3.dll', nm); } catch (e) { }
    try { return mod.findExportByName(nm); } catch (e) { }
    return null;
  }

  var got = [];

  var w = exp('SSL_write');
  if (w) {
    Interceptor.attach(w, {
      onEnter: function (a) {
        var n = a[2].toInt32();
        if (n > 0) console.log('\n[WRITE len=' + n + ']\n' + readStr(a[1], n));
      }
    });
    got.push('SSL_write');
  }

  var we = exp('SSL_write_ex');
  if (we) {
    Interceptor.attach(we, {
      onEnter: function (a) { this.b = a[1]; this.n = a[2].toInt32(); },
      onLeave: function (r) {
        if (r.toInt32() === 1 && this.n > 0) console.log('\n[WRITE_EX len=' + this.n + ']\n' + readStr(this.b, this.n));
      }
    });
    got.push('SSL_write_ex');
  }

  var r = exp('SSL_read');
  if (r) {
    Interceptor.attach(r, {
      onEnter: function (a) { this.b = a[1]; },
      onLeave: function (ret) {
        var n = ret.toInt32();
        if (n > 0) console.log('\n[READ len=' + n + ']\n' + readStr(this.b, n));
      }
    });
    got.push('SSL_read');
  }

  var re = exp('SSL_read_ex');
  if (re) {
    Interceptor.attach(re, {
      onEnter: function (a) { this.b = a[1]; this.o = a[3]; },
      onLeave: function (ret) {
        if (ret.toInt32() === 1) {
          var n = this.o.readU32();
          if (n > 0) console.log('\n[READ_EX len=' + n + ']\n' + readStr(this.b, n));
        }
      }
    });
    got.push('SSL_read_ex');
  }

  var sv = exp('SSL_CTX_set_verify');
  if (sv) {
    Interceptor.attach(sv, {
      onEnter: function (a) { console.log('[set_verify mode=' + a[1].toInt32() + ']'); }
    });
    got.push('SSL_CTX_set_verify');
  }

  hooked = true;
  console.log('==== HOOKED: ' + got.join(',') + ' @ ' + new Date().toISOString() + ' ====');
  console.log('==== 现在去 HiSuite 里点「系统更新」→「检查更新」 ====');
}

console.log('\n################ capture session ' + new Date().toISOString() + ' ################');
hookAll();
setInterval(hookAll, 500);
