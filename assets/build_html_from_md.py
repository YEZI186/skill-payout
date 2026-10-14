#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown -> 软著操作说明书 HTML 转换桥（payout 资产）

设计要点（每条都是踩过的坑，勿改回）：
  1. 封面文案一律由命令行参数提供，脚本内不得写死项目名 / 版本 / 文档类型，
     否则每换一个项目都要改脚本，而且改了会被下一次运行覆盖回来；
  2. 标题层级自适应：文档里出现多个井号开头的标题时，把井号当章（h2）；
     只有一个井号开头的标题时，当文档标题并跳过 —— 否则源文档用井号当章时会被整章丢弃；
  3. 图片两种语法都认：MarkText 的 <img ...> 与 Markdown 的 ![](path)；
  4. 图片与文字挤在同一行时，文字不被吞掉（原实现会整行丢弃）；
  5. 图注默认取紧随其后的「（页面-组件）」占位行并消费该行，避免正文重复出现；
     无占位行时不输出图注（不再出现无意义的「图N」）。

用法：
  python build_html_from_md.py <md> <template.html> <out.html> <img_dir> [选项]

  例：
  python build_html_from_md.py 说明书.md 模板.html 输出.html 说明书-截图 \
      --title "软件名称" --header "软件名称 V1.0" --cover-version V1.0 \
      --img-width 560 --caption placeholder
"""
import argparse
import html as html_mod
import re
import sys
from pathlib import Path

# 统计输出含中文，PowerShell 下按 locale 编码写字节会乱码（2026-10-13 统一加固）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_IMG_WIDTH = 560
BT = chr(96)
CODE_RE = re.compile(BT + "([^" + BT + "]+)" + BT)
BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
PLACEHOLDER_RE = re.compile(r"^（[^）]+）$")
MD_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_IMG_RE = re.compile(r"<img[^>]*>")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
# 文档类型副标题词表：源 md 常写成「软件名」+「操作说明书」两行标题，
# 后一行是文档类型而非章，须并入封面类型行，不能进正文与目录（否则多出一个空章）。
DOCTYPE_WORDS = ("操作说明书", "用户操作手册", "使用说明书")


def strip_doc_subtitle(lines):
    """剔除 H1 之后紧邻的文档类型副标题行，返回 (新行列表, 副标题文本)。

    只在同时满足三条时剔除，避免误删真有内容的章：
      1. 该行是 H2 且标题恰为文档类型词；
      2. 它位于全文首个 H1 之后（允许中间隔空行）；
      3. 它之后（跳过空行）是下一个标题或文件末尾，即该行下没有正文。
    """
    h1 = [i for i, l in enumerate(lines) if re.match(r"^#\s", l)]
    if not h1:
        return lines, ""
    i = h1[0] + 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return lines, ""
    m = re.match(r"^##\s+(.*)$", lines[i].strip())
    if not m or m.group(1).strip() not in DOCTYPE_WORDS:
        return lines, ""
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines) or re.match(r"^#{1,6}\s", lines[j].strip()):
        return lines[:i] + lines[i + 1:], m.group(1).strip()
    return lines, ""


class TocItem(object):
    def __init__(self, level, hid, title):
        self.level = level
        self.id = hid
        self.title = title


def esc(text):
    return html_mod.escape(text, quote=False)


def inline(text):
    text = CODE_RE.sub(lambda m: "<code>" + esc(m.group(1)) + "</code>", text)
    text = BOLD_RE.sub(lambda m: "<strong>" + esc(m.group(1)) + "</strong>", text)
    return text


def parse_img_attrs(tag):
    src = re.search('src="([^"]+)"', tag)
    w = re.search(r'width="(\d+)"', tag)
    return (src.group(1) if src else ""), (int(w.group(1)) if w else None)


def img_ref(md_cwd, img_dir, uri):
    if uri.startswith("file:///"):
        p = Path(uri[8:])
    elif Path(uri).is_absolute():
        p = Path(uri)
    else:
        p = Path(md_cwd) / uri
    return img_dir.name + "/" + p.name


def render_table(lines):
    def cell(c):
        return inline(esc(c))

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    head = cells(lines[0])
    body = [cells(x) for x in lines[2:] if x.strip()]
    out = ["<table><thead><tr>"]
    out += ["<th>" + cell(h) + "</th>" for h in head]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join("<td>" + cell(c) + "</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def parse(lines, md_cwd, img_dir, opt):
    body, toc = [], []
    stats = {"img": 0, "caption": 0, "split": 0}
    chap = sec = fig = 0
    n = len(lines)

    h1_idx = [i for i, l in enumerate(lines) if re.match(r"^#\s", l)]
    multi_h1 = len(h1_idx) >= 2
    offset = 1 if multi_h1 else 0

    i = 0
    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if "<img" in line or MD_IMG_RE.search(line):
            tags = HTML_IMG_RE.findall(line)
            if not tags:
                tags = ['<img src="%s" width="%d" data-align="center">'
                        % (u, opt.img_width) for u in MD_IMG_RE.findall(line)]
            rest = MD_IMG_RE.sub("", HTML_IMG_RE.sub("", line)).strip()
            if rest:
                stats["split"] += 1
                body.append("<p>" + inline(esc(rest)) + "</p>")

            cap = None
            if opt.caption == "placeholder":
                j = i + 1
                while j < n and not lines[j].strip():
                    j += 1
                if j < n and PLACEHOLDER_RE.match(lines[j].strip()):
                    cap = lines[j].strip()
                    i = j
            fig += 1
            if opt.caption == "figure":
                cap_html = '<div class="fig-caption">图%d</div>' % fig
            elif cap:
                cap_html = '<div class="fig-caption">%s</div>' % esc(cap)
            else:
                cap_html = ""
            if cap:
                stats["caption"] += 1

            if len(tags) >= 2:
                items = []
                for t in tags:
                    src, w = parse_img_attrs(t)
                    ref = img_ref(md_cwd, img_dir, src)
                    items.append('<div class="img-inline"><img src="%s" style="max-width:%dpx"></div>'
                                 % (ref, w or opt.img_width))
                body.append('<div class="img-row">' + "".join(items) + "</div>" + cap_html)
            else:
                src, w = parse_img_attrs(tags[0])
                ref = img_ref(md_cwd, img_dir, src)
                body.append('<div class="img-center"><img src="%s" style="max-width:%dpx"></div>'
                            % (ref, w or opt.img_width) + cap_html)
            stats["img"] += 1
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        m = HEAD_RE.match(stripped)
        if m:
            lvl = len(m.group(1)) + offset   # 多个井号时整体下移一层：# 当章、## 当节
            title = m.group(2).strip()
            if lvl == 2:
                chap += 1
                hid = "chap%d" % chap
                body.append('<h2 id="%s">%s</h2>' % (hid, esc(title)))
                toc.append(TocItem(1, hid, title))
            elif lvl == 3:
                sec += 1
                hid = "sec%d" % sec
                body.append('<h3 id="%s">%s</h3>' % (hid, esc(title)))
                toc.append(TocItem(2, hid, title))
            elif lvl >= 4:
                body.append("<h4>%s</h4>" % esc(title))
            i += 1
            continue

        if stripped.startswith("**") and stripped.endswith("**") and len(stripped) > 4:
            body.append("<h4>%s</h4>" % esc(stripped.strip("*").strip()))
            i += 1
            continue

        if stripped.startswith(">"):
            q = []
            while i < n and lines[i].strip().startswith(">"):
                q.append(lines[i].strip().lstrip("> ").strip())
                i += 1
            body.append("<blockquote><p>" + inline(esc("".join(q))) + "</p></blockquote>")
            continue

        if stripped.startswith("|"):
            tbl = []
            while i < n and lines[i].strip().startswith("|"):
                tbl.append(lines[i])
                i += 1
            body.append(render_table(tbl))
            continue

        if re.match(r"^[-*+]\s", stripped) or re.match(r"^\d+\.\s", stripped):
            is_ul = not re.match(r"^\d+\.\s", stripped)
            items = []
            while i < n:
                mm = re.match(r"^([-*+]|\d+\.)\s+(.*)$", lines[i].strip())
                if not mm:
                    break
                items.append("<li><p>" + inline(esc(mm.group(2))) + "</p></li>")
                i += 1
            tag = "ul" if is_ul else "ol"
            body.append("<" + tag + ">" + "".join(items) + "</" + tag + ">")
            continue

        body.append("<p>" + inline(esc(stripped)) + "</p>")
        i += 1

    return "\n".join(body), toc, stats, multi_h1


def build_html(body, toc, css, opt, title):
    css = css.replace('"【系统名 V1.0】"', '"%s"' % esc(opt.header))
    parts = ['<div class="toc-page"><div class="toc-title">目　录</div><div class="toc">']
    for it in toc:
        cls = "toc-l1" if it.level == 1 else "toc-l2"
        parts.append('<div class="toc-item %s"><a href="#%s" class="t">%s</a>'
                     '<span class="dots"></span><span class="pg">【】</span></div>'
                     % (cls, it.id, esc(it.title)))
    parts.append("</div></div>")

    h1 = "<h1>%s</h1>" % esc(title)
    if opt.cover_sub:
        h1 = "<h1>%s<br>%s</h1>" % (esc(title), esc(opt.cover_sub))
    cover = '<div class="cover">' + h1
    if opt.cover_version:
        cover += '<div class="version">%s</div>' % esc(opt.cover_version)
    if opt.cover_doctype:
        cover += '<div class="doctype">%s</div>' % esc(opt.cover_doctype)
    cover += "</div>"

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>%s-操作说明书</title>
<style>
%s

/* ===== 图片排版 ===== */
.img-center { text-align: center; margin: 10pt 0 2pt; }
.img-center img { max-width: 12cm; height: auto; border: 0.3pt solid #ccc; }
.img-row { display: flex; gap: 12pt; justify-content: center; align-items: flex-start; margin: 10pt 0 2pt; flex-wrap: wrap; }
.img-inline { flex: 1 1 auto; text-align: center; }
.img-inline img { max-width: 8.5cm; height: auto; border: 0.3pt solid #ccc; }
.fig-caption { text-align: center; font-size: 11pt; color: #333; margin: 2pt 0 14pt; }
</style>
</head>
<body>
<div class="page">
%s
%s
%s
</div>
</body>
</html>""" % (esc(title), css, cover, "\n".join(parts), body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("template")
    ap.add_argument("out")
    ap.add_argument("img_dir")
    ap.add_argument("--title", default="", help="封面软件名；留空则取文档唯一 H1，再退回文件名")
    ap.add_argument("--header", default="", help="页眉文字；留空则为「软件名 V1.0」")
    ap.add_argument("--cover-sub", default="", help="封面副标题，默认不显示")
    ap.add_argument("--cover-version", default="V1.0", help="封面版本行，传空字符串则不显示")
    ap.add_argument("--cover-doctype", default=None, help="封面文档类型行；不传时取源 md 的文档类型副标题，再退回「用户操作手册」；传空字符串则不显示")
    ap.add_argument("--img-width", type=int, default=DEFAULT_IMG_WIDTH)
    ap.add_argument("--caption", choices=["placeholder", "figure", "none"], default="placeholder")
    a = ap.parse_args()

    md_path = Path(a.md).resolve()
    lines = md_path.read_text(encoding="utf-8").splitlines()
    lines, sub = strip_doc_subtitle(lines)
    if a.cover_doctype is None:
        a.cover_doctype = sub or "用户操作手册"
    tpl = Path(a.template).read_text(encoding="utf-8")
    m = re.search(r"<style>(.*?)</style>", tpl, re.S)
    css = m.group(1) if m else ""

    h1s = [l for l in lines if re.match(r"^#\s", l)]
    title = a.title or (h1s[0][2:].strip() if len(h1s) == 1 else md_path.stem)
    a.header = a.header or (title + " V1.0")

    body, toc, stats, multi_h1 = parse(lines, md_path.parent, Path(a.img_dir).resolve(), a)
    Path(a.out).write_text(build_html(body, toc, css, a, title), encoding="utf-8")

    print("OK %s" % a.out)
    print("  封面: %s | 版本行: %s | 类型行: %s"
          % (title, a.cover_version or "(不显示)", a.cover_doctype or "(不显示)"))
    print("  文档类型副标题: %s"
          % (sub + "（已并入封面，未进正文与目录）" if sub else "(源 md 无)"))
    print("  标题层级: %s | 章 %d / 节 %d | 目录条目 %d"
          % ("多个 # 视为章" if multi_h1 else "单 # 视为文档标题",
             len([t for t in toc if t.level == 1]), len([t for t in toc if t.level == 2]), len(toc)))
    print("  图片 %d 处 | 带图注 %d 处 | 图文同行已拆分 %d 处"
          % (stats["img"], stats["caption"], stats["split"]))


if __name__ == "__main__":
    main()