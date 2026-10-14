#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""目录页码静态回填（payout 资产）

设计要点（每条都是踩过的坑）：
  1. 幂等：直接按 toc-item 块重写页码，不依赖【】占位符 ——
     原实现只匹配【】，对已回填过的 HTML 第二次运行会 0 命中，
     导致「改了分页却回填不上」，必须先重新生成 HTML 才行；
  2. 按行聚合 span 再整行匹配：PyMuPDF 会把中文标题逐字拆成多个 span；
  3. 正文起始页自动判定：找含「目录」的那一页，从其后一页起搜标题；
     找不到时退回 --body-start（默认 3，即封面 1 + 目录 1 之后的第 3 页）。

用法：
  python backfill_toc.py <pdf> <html> [--body-start 3] [--report 输出.txt]
"""
import argparse
import re
import sys

try:
    import fitz
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")

# 回填日志含中文，PowerShell 下按 locale 编码写字节会乱码（2026-10-13 统一加固）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

TOC_ITEM_RE = re.compile(
    r'(<div class="toc-item (toc-l[12])"><a href="#([a-z]+\d+)" class="t">(.*?)</a>'
    r'<span class="dots"></span><span class="pg">)(.*?)(</span></div>)')


def norm(s):
    return re.sub(r"\s+", "", s)


def page_rows(doc):
    pages = []
    for pno in range(doc.page_count):
        rows = []
        for b in doc[pno].get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                rows.append((round(spans[0]["size"], 1),
                             "".join(s["text"] for s in spans).strip()))
        pages.append(rows)
    return pages


def find_body_start(pages, fallback):
    for pno, rows in enumerate(pages):
        if any(norm(t) in ("目录", "目　录") for _sz, t in rows):
            return pno + 1
    return fallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("html")
    ap.add_argument("--body-start", type=int, default=3)
    ap.add_argument("--report", default="")
    a = ap.parse_args()

    doc = fitz.open(a.pdf)
    pages = page_rows(doc)
    body_start = find_body_start(pages, a.body_start - 1)
    html = open(a.html, encoding="utf-8").read()

    log = ["PDF %d 页 | 正文起始页 %d（1-based）" % (doc.page_count, body_start + 1)]
    state = {"hit": 0, "miss": 0}

    def repl(m):
        pre, cls, hid, title_html, _old, post = m.groups()
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        target = norm(title)
        found = None
        for pno in range(body_start, len(pages)):
            if any(norm(t) == target for _sz, t in pages[pno]):
                found = pno + 1
                break
        if found is None:
            state["miss"] += 1
            log.append("  !! 正文未找到: " + title)
            return m.group(0)
        state["hit"] += 1
        log.append("  %-18s -> %d" % (title, found))
        return pre + str(found) + post

    new_html = TOC_ITEM_RE.sub(repl, html)
    open(a.html, "w", encoding="utf-8").write(new_html)

    log.append("回填 %d 条，未命中 %d 条" % (state["hit"], state["miss"]))
    text = "\n".join(log)
    if a.report:
        open(a.report, "w", encoding="utf-8").write(text)
    print(text)


if __name__ == "__main__":
    main()
