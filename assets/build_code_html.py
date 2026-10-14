#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源代码汇总 md -> 软著 60 行/页 HTML（payout 资产）

设计要点（每条都是踩过的坑，勿改回）：
  1. 每页 60 行靠"先切页、再强制分页"：转换桥把显示行按 rows 切成一组组，每组装进
     一个 .sheet；交给浏览器自己分页做不到精确 60 行 —— 行高与版心高相除的余量会被
     亚像素吃掉，末页常常少一行，也没法与 Word 的固定行网格对齐；
  2. 行号印在"伪页边距"里：Chromium 打印只保留 @page 内容区内的内容，行号若用负偏移
     摆到版心左侧（内容区之外）会被整体裁掉，连同行首字符一起消失。模板的
     @page 左边距 2cm 与 .sheet 的 padding-left 1.75cm 相加才是 3.75cm 视觉页边距；
  3. 折行按加权列宽算：半角 1 列、全角 1.667 列（9pt 下 Courier New 5.357pt/字符、
     宋体 8.928pt/字符）。76 列留 11pt 余量，78 列实测右界越出版心 0.5pt；
  4. 折行的续行不另给行号：行号 = 显示行序号，与 Word lnNumType 行为一致；末页补齐的
     空行不给行号，避免出现"有号无字"的尾巴；
  5. 文案一律走命令行参数，模板与脚本内不得写死项目名 —— 否则下一次运行会把人工
     改掉的页眉重新生成出来。

用法：
  python build_code_html.py <源代码汇总.md> <模板.html> <输出.html> [选项]

  例：
  python build_code_html.py out/源代码汇总.md "<skill>/assets/软著源代码-HTML模板.html" \
      "out/源代码-某某系统.html" --header "某某系统 V1.0" --header-mid "程序鉴别材料"
"""
import argparse
import html as html_mod
import re
import sys
from pathlib import Path

# 统计输出含中文，且运行环境是 PowerShell；不改 stdout 编码时中文会乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_ROWS = 60
DEFAULT_COLS = 76
DEFAULT_FONT_PT = 9
DEFAULT_LINE_PT = 12
DEFAULT_TAB = 4
# 全角字符折算成半角列数：宋体 9pt 单字 8.928pt ÷ Courier New 单字符 5.357pt
CJK_WEIGHT = 1.667
LEGACY_FIRST_LINE = "# 软件著作权源代码文档"
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def read_source(path):
    """读汇总 md：去 BOM、换行归一，末尾换行不计一行。"""
    text = Path(path).read_bytes().decode("utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def drop_fences(lines):
    """剔除 Markdown 代码围栏行（``` / ~~~）。汇总 md 默认没有围栏，容错用。"""
    kept, dropped = [], 0
    for line in lines:
        if FENCE_RE.match(line):
            dropped += 1
            continue
        kept.append(line)
    return kept, dropped


def drop_legacy_header(lines, max_scan=12):
    """剔除 project-critical 旧版头部：# 软件著作权源代码文档 … --- 共 8 行。

    只在首行（跳过前导空行）命中标题、且 max_scan 行内出现 --- 结束线时才剔除；
    否则原样返回，避免把正文里恰好出现的同名行当成头部切掉。
    """
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != LEGACY_FIRST_LINE:
        return lines, 0
    end = None
    for j in range(i, min(len(lines), i + max_scan)):
        if lines[j].strip() == "---":
            end = j
            break
    if end is None:
        return lines, 0
    return lines[:i] + lines[end + 1:], end + 1 - i


def expand_tabs(line, tab):
    """Tab 展开到下一个制表位；中文按 2 列推进，保证展开后缩进对齐。"""
    if "\t" not in line:
        return line
    out, col = [], 0
    for ch in line:
        if ch == "\t":
            step = tab - (col % tab)
            out.append(" " * step)
            col += step
        else:
            out.append(ch)
            col += 2 if ord(ch) > 0x2E80 else 1
    return "".join(out)


def wrap_line(text, cols):
    """按加权列宽折行，返回显示行列表；空行返回单个空串。"""
    if not text:
        return [""]
    rows, cur, width = [], [], 0.0
    for ch in text:
        cw = CJK_WEIGHT if ord(ch) > 0x2E80 else 1.0
        if cur and width + cw > cols:
            rows.append("".join(cur))
            cur, width = [], 0.0
        cur.append(ch)
        width += cw
    rows.append("".join(cur))
    return rows


def paginate(display_lines, rows):
    """按 rows 行一页切分；末页补空行，保证每页行槽数一致。"""
    pages = [display_lines[i:i + rows] for i in range(0, len(display_lines), rows)]
    if not pages:
        pages = [[]]
    return [p + [""] * (rows - len(p)) for p in pages]


def esc(text):
    return html_mod.escape(text, quote=False)


def render_sheets(pages, real_lines, lineno):
    """每个 .sheet 一页；补齐行不给行号（real_lines 之后的行属补齐）。"""
    out = []
    number = 0
    for page in pages:
        rows = []
        for text in page:
            if number < real_lines:
                number += 1
                mark = "<i>%d</i>" % number if lineno else ""
            else:
                mark = "<i></i>" if lineno else ""
            body = esc(text) if text else " "
            rows.append('<div class="ln">%s<code>%s</code></div>' % (mark, body))
        out.append('<section class="sheet">%s</section>' % "".join(rows))
    return "\n".join(out)


def apply_style(css, header, header_mid, font_pt, line_pt):
    """模板里的占位替换；引号必须转义，否则 CSS content 会被截断。"""
    quoted = header.replace("\\", "\\\\").replace('"', '\\"')
    mid = header_mid.replace("\\", "\\\\").replace('"', '\\"')
    return (css.replace("【软件名 V1.0】", quoted)
               .replace("【页眉中间词】", mid)
               .replace("【字号】", str(font_pt))
               .replace("【行高】", str(line_pt)))


def build_html(title, css, sheets):
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>%s-源代码</title>
<style>
%s
</style>
</head>
<body>
%s
</body>
</html>""" % (esc(title), css, sheets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md", help="源代码汇总 md（纯源码正文，或带路径注释行）")
    ap.add_argument("template", help="软著源代码-HTML模板.html")
    ap.add_argument("out", help="输出 HTML")
    ap.add_argument("--header", default="", help="页眉左文字；留空则取 md 文件名 + V1.0")
    ap.add_argument("--header-mid", default="程序鉴别材料", help="页眉中间文字")
    ap.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="每页行数")
    ap.add_argument("--cols", type=int, default=DEFAULT_COLS, help="每行最多半角列数")
    ap.add_argument("--font-size", type=int, default=DEFAULT_FONT_PT, help="代码字号 pt")
    ap.add_argument("--line-height", type=int, default=DEFAULT_LINE_PT, help="行高 pt")
    ap.add_argument("--tab", type=int, default=DEFAULT_TAB, help="Tab 展开的空格数")
    ap.add_argument("--lineno", choices=["on", "off"], default="on", help="是否打印行号")
    ap.add_argument("--keep-legacy-header", action="store_true", help="保留旧版 8 行头部")
    ap.add_argument("--keep-fences", action="store_true", help="保留 Markdown 代码围栏行")
    a = ap.parse_args()

    md_path = Path(a.md).resolve()
    lines = read_source(md_path)

    dropped_fences = dropped_header = 0
    if not a.keep_fences:
        lines, dropped_fences = drop_fences(lines)
    if not a.keep_legacy_header:
        lines, dropped_header = drop_legacy_header(lines)

    # 空源料不许静默出一份"只有行号框、没有代码"的文档 —— 那会当成交付物交出去
    if not any(line.strip() for line in lines):
        sys.exit("汇总 md 没有可排版内容：%s（检查路径、剥离规则或源文件是否为空）" % md_path)

    display, wrapped_rows, longest = [], 0, 0.0
    for line in lines:
        expanded = expand_tabs(line, a.tab)
        rows = wrap_line(expanded, a.cols)
        if len(rows) > 1:
            wrapped_rows += 1
        longest = max(longest, max(sum(CJK_WEIGHT if ord(c) > 0x2E80 else 1.0 for c in r)
                                   for r in rows))
        display.extend(rows)

    pages = paginate(display, a.rows)
    css = re.search(r"<style>(.*?)</style>",
                    Path(a.template).read_text(encoding="utf-8"), re.S).group(1)
    title = a.header or (md_path.stem + " V1.0")
    html = build_html(title, apply_style(css, title, a.header_mid, a.font_size, a.line_height),
                      render_sheets(pages, len(display), a.lineno == "on"))
    Path(a.out).write_text(html, encoding="utf-8")

    padded = a.rows * len(pages) - len(display)
    print("OK %s" % a.out)
    print("  页眉: 左「%s」| 中「%s」| 右「第 N 页」" % (title, a.header_mid))
    print("  版式: 每页 %d 行 | %dpt / 行高 %dpt | 每行最多 %d 加权列 | 行号 %s"
          % (a.rows, a.font_size, a.line_height, a.cols,
             "连续" if a.lineno == "on" else "关闭"))
    print("  源 md: %d 行（跳过 围栏 %d / 旧版头部 %d）| 参与排版 %d 行"
          % (len(read_source(md_path)), dropped_fences, dropped_header, len(lines)))
    print("  折行: 显示行 %d（被折行 %d 行）| 最长显示行 %.1f 列"
          % (len(display), wrapped_rows, longest))
    print("  分页: %d 页 | 末页补齐 %d 空行（补齐行不编号）" % (len(pages), padded))


if __name__ == "__main__":
    main()
