# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 HiSuite-Firmware-Research contributors
#
#!/usr/bin/env python3
# carve_kernel.py —— 从华为 update_full_base.zip 里抠出 kernel Image
# 用法: python carve_kernel.py <update_full_base.zip> <workdir>
# 步骤: zip 定位 UPDATE.APP → 流式扫 ANDROID! → 按 boot header 抠 kernel → 解 gzip → 校验 ARMd
import sys, os, struct, zlib, zipfile

def find_all(hay_path, needle, chunk=8 << 20):
    """流式找出所有 needle 偏移（按 chunk 重叠扫描）"""
    hits = []
    ln = len(needle)
    with open(hay_path, 'rb') as f:
        base = 0
        prev = b''
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            data = prev + buf
            start = 0
            while True:
                i = data.find(needle, start)
                if i < 0:
                    break
                hits.append(base - len(prev) + i)
                start = i + 1
            prev = data[-(ln - 1):] if ln > 1 else b''
            base += len(buf)
    return hits

def parse_boot_header(blob):
    """Android boot header v0/v1/v2"""
    if blob[:8] != b'ANDROID!':
        return None
    magic, kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size, second_addr, \
        tags_addr, page_size, header_version, os_version = struct.unpack_from('<8sIIIIIIIIII', blob, 0)
    if page_size not in (2048, 4096, 8192, 16384, 65536):
        return None
    rec = dict(page_size=page_size, kernel_size=kernel_size, ramdisk_size=ramdisk_size,
               header_version=header_version)
    if header_version >= 2:
        # v2: 额外字段后才是内容
        rec['kernel_offset'] = page_size
    else:
        rec['kernel_offset'] = page_size
    return rec

def main():
    if len(sys.argv) < 3:
        print(__doc__); return 1
    src, work = sys.argv[1], sys.argv[2]
    os.makedirs(work, exist_ok=True)

    # 1) 在 zip 里找 UPDATE.APP
    print(f'[*] open zip {src}')
    app_path = None
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        print(f'[*] entries: {len(names)}')
        for n in names:
            if n.upper().endswith('UPDATE.APP'):
                app_path = os.path.join(work, 'UPDATE.APP')
                print(f'[+] extracting {n} ({z.getinfo(n).file_size:,} bytes) -> {app_path}')
                with z.open(n) as fi, open(app_path, 'wb') as fo:
                    while True:
                        b = fi.read(8 << 20)
                        if not b: break
                        fo.write(b)
                break
    if not app_path:
        print('[!] UPDATE.APP not found in zip; entries:')
        with zipfile.ZipFile(src) as z:
            for n in z.namelist(): print('    ', n, z.getinfo(n).file_size)
        return 2

    # 2) 扫 ANDROID!
    print('[*] scanning ANDROID! ...')
    hits = find_all(app_path, b'ANDROID!')
    print(f'[+] {len(hits)} hits: {[hex(h) for h in hits[:10]]}')

    ok = 0
    with open(app_path, 'rb') as f:
        for idx, h in enumerate(hits):
            f.seek(h)
            hdr = f.read(8192)
            rec = parse_boot_header(hdr)
            if not rec:
                print(f'[-] hit {idx} @{h:#x} bad header, skip'); continue
            total = rec['page_size'] + rec['kernel_size']
            print(f'[+] hit {idx} @{h:#x} page={rec["page_size"]} kernel={rec["kernel_size"]:,} ramdisk={rec["ramdisk_size"]:,} hv={rec["header_version"]}')
            f.seek(h + rec['kernel_offset'])
            kern = f.read(rec['kernel_size'])
            packed = os.path.join(work, f'kernel_{idx}.gz')
            with open(packed, 'wb') as o: o.write(kern)
            print(f'    kernel blob -> {packed} ({len(kern):,})')
            # 3) 解 gzip / 直接判 ARMd
            raw = None
            if kern[:2] == b'\x1f\x8b':
                try:
                    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    raw = d.decompress(kern) + d.flush()
                    print(f'    gzip ok -> {len(raw):,} bytes')
                except Exception as e:
                    print('    gzip fail:', e)
            else:
                raw = kern
            if raw and len(raw) > 0x100 and raw[0x38:0x3c] == b'ARMd':
                out = os.path.join(work, f'Image_{idx}.bin')
                with open(out, 'wb') as o: o.write(raw)
                print(f'    [OK] ARM64 Image -> {out}')
                # banner
                b = raw.find(b'Linux version ')
                if b >= 0:
                    print('    banner:', raw[b:b+220].decode('latin1', 'replace'))
                ok += 1
            else:
                head = raw[:0x40].hex() if raw else ''
                print(f'    not ARMd, head={head}')
    print(f'[*] done, {ok} kernel image(s) extracted')
    return 0 if ok else 3

if __name__ == '__main__':
    sys.exit(main())
