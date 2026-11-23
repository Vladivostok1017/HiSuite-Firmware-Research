# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 HiSuite-Firmware-Research contributors
#
#!/usr/bin/env python3
# parse_capture.py —— 把 hook_ssl.js 抓到的日志按请求/响应切块并提取关键信息
#
# 用法:
#   python parse_capture.py ssl_capture.log                # 打印摘要
#   python parse_capture.py ssl_capture.log -o parsed.txt  # 同时写文件
#   python parse_capture.py ssl_capture.log --grep dbankcdn # 只看匹配 host 的块
#
# 输出字段: kind(WRITE/READ), len, host, 首行(请求行或状态行), 可选响应体
import sys, os, re, argparse

BLOCK = re.compile(r'\n\[(WRITE|READ)(?:_EX)? len=(\d+)\]\n')


def parse(text):
    """按 [WRITE len=N] / [READ len=N] 切块，返回 [(kind, len, body), ...]"""
    parts = BLOCK.split(text)
    out = []
    i = 1
    while i + 2 < len(parts) + 1 and i + 2 <= len(parts):
        kind = parts[i]
        ln = parts[i + 1]
        body = parts[i + 2] if i + 2 < len(parts) else ''
        # body 尾部可能粘着下一条 [set_verify mode=..] 之类，切掉
        cut = body.find('\n[set_verify')
        if cut >= 0:
            body = body[:cut]
        out.append((kind, ln, body))
        i += 3
    return out


def summarize(kind, ln, body, show_body=False, max_body=20000):
    host = ''
    m = re.search(r'^Host:\s*(\S+)', body, re.M)
    if m:
        host = m.group(1)
    first = ''
    for line in body.splitlines():
        if line.strip():
            first = line.strip()
            break
    out = [f'[{kind} {ln}] {host}',
           f'    {first}']
    if show_body:
        # 只保留 XML/JSON 主体，跳过 HTTP 头
        idx = body.find('\n\n')
        payload = body[idx + 2:] if idx >= 0 else body
        payload = payload.strip()
        if payload:
            out.append('    ' + payload[:max_body].replace('\n', '\n    '))
    return '\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('-o', '--out')
    ap.add_argument('--grep', default=None, help='只输出 host/首行匹配该正则的块')
    ap.add_argument('--body', action='store_true', help='打印响应/请求体')
    ap.add_argument('--max-body', type=int, default=20000)
    args = ap.parse_args()

    if not os.path.exists(args.log):
        print(f'[!] no such file: {args.log}')
        return 1

    text = open(args.log, encoding='utf-8', errors='replace').read()
    blocks = parse(text)
    print(f'[*] {len(blocks)} blocks parsed from {args.log}\n')

    pat = re.compile(args.grep, re.I) if args.grep else None
    lines = []
    for kind, ln, body in blocks:
        txt = summarize(kind, ln, body, args.body, args.max_body)
        if pat and not pat.search(txt):
            continue
        lines.append(txt)

    result = '\n\n'.join(lines) if lines else '(no matching blocks)'
    print(result)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'\n[*] written to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
