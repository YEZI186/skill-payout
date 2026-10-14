# -*- coding: utf-8 -*-
"""截图预处理：按需缩放 + 调色板 PNG 压缩，供说明书排版使用。

为什么需要：说明书里动辄几十张界面截图，原始 PNG 单张 150-600 KB，
    转换脚本把 45 个 <img> 一次性交给浏览器，打印 PDF 时全部要解码，
    直接决定生成速度与交付体积。

用法：
    python optimize_images.py <源图目录> <目标图目录> [--max-edge 0] [--colors 256]

说明：
    - **默认原图不处理（--max-edge 0）**：PNG 原样拷贝，不改像素、不重编码、不量化，
      画质与源图完全一致；非 PNG 转存为 PNG，保证引用扩展名统一；
    - --max-edge N（N>0）：最长边超过 N 时等比缩小，不足时不放大（分辨率上限由源图决定），
      再按 --colors 转调色板 PNG；1400px 档位对应约 243 dpi，900px 仅 156 dpi；
    - 调色板 PNG 而非 JPEG，避免界面文字出现块状伪影；
    - 幂等：每次覆盖目标目录，可反复执行。
"""
import argparse
import glob
import io
import os
import shutil
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("需要 Pillow：pip install pillow")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--max-edge", type=int, default=0,
                    help="0=原图不处理（默认，零重编码）；N>0=最长边超过 N 时等比缩小，不足时不放大")
    ap.add_argument("--colors", type=int, default=256,
                    help="调色板色数，仅 --max-edge>0 的压缩档位生效")
    ap.add_argument("--only", default=None,
                    help="只处理该清单文件里列出的图片文件名（每行一个），用于排除文档未引用的截图")
    a = ap.parse_args()

    os.makedirs(a.dst, exist_ok=True)
    files = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG"):
        files.extend(glob.glob(os.path.join(a.src, ext)))
    files = sorted(set(files))
    if a.only:
        wanted = set()
        with open(a.only, encoding="utf-8") as fh:
            for line in fh:
                n = line.strip()
                if n:
                    wanted.add(n)
        files = [f for f in files if os.path.basename(f) in wanted or os.path.splitext(os.path.basename(f))[0] + ".png" in wanted]
        missing = sorted(w for w in wanted if not any(os.path.basename(f) == w for f in files))
        if missing:
            print("警告：清单中 %d 个文件在源目录未找到：%s" % (len(missing), ", ".join(missing[:5])))
    if not files:
        sys.exit("源目录没有图片：" + a.src)

    if a.max_edge <= 0:
        # 原图不处理：PNG 原样拷贝（零重编码、不量化、不改像素）；非 PNG 转存 PNG 以统一引用扩展名
        before = sum(os.path.getsize(f) for f in files)
        for f in files:
            dst = os.path.join(a.dst, os.path.splitext(os.path.basename(f))[0] + ".png")
            if f.lower().endswith(".png"):
                shutil.copy2(f, dst)
            else:
                Image.open(f).convert("RGB").save(dst, "PNG", optimize=True)
        after = sum(os.path.getsize(os.path.join(a.dst, os.path.splitext(os.path.basename(f))[0] + ".png"))
                    for f in files)
        print("图片 %d 张（原图不处理）：%.2f MB -> %.2f MB（%.0f%%）"
              % (len(files), before / 1048576.0, after / 1048576.0, after * 100.0 / before))
        return

    before = after = 0
    for f in files:
        before += os.path.getsize(f)
        im = Image.open(f)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        w, h = im.size
        if max(w, h) > a.max_edge:
            k = a.max_edge / float(max(w, h))
            im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
        out = im.convert("P", palette=Image.ADAPTIVE, colors=a.colors)
        name = os.path.splitext(os.path.basename(f))[0] + ".png"
        dst = os.path.join(a.dst, name)
        out.save(dst, "PNG", optimize=True)
        after += os.path.getsize(dst)

    print("图片 %d 张：%.2f MB -> %.2f MB（%.0f%%）"
          % (len(files), before / 1048576.0, after / 1048576.0, after * 100.0 / before))


if __name__ == "__main__":
    main()