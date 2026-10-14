#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源代码 PDF 机械校验（payout 资产）

检查项（全部可复跑，结论落盘留证）：
  1. 页数自洽：非末页每页行号数恰好等于 --rows，末页 1..rows，且总行号数 → 页数换算一致；
  2. 行槽不越界：每页正文文本按 y 归并到"行槽"，槽位必须落在 0..rows-1（防止某页多塞一行）；
  3. 版心不溢出：正文文本右界 ≤ 版心右界、末行 y ≤ 版心底（防止长行折行没折到位）；
  4. 页眉 3 段（左 / 中 / 右齐全，右侧"第 N 页"与页序一致）；
  5. 页脚 1 行，格式 "N / M"，N 与页序一致、M 等于总页数，且字号与正文一致（页脚与页眉同源）；
  6. 行号全文连续递增（跨页不重号、不漏号）；
  7. 正文字号与 --font-size 一致；
  8. 页眉下横线长度 = Word 页眉段落的负缩进范围（默认 2.27→19.61cm，比版心宽、两端伸进页边距）。
     这条线最容易回退：改回 .sheet 的 border-top 会退化成"打印内容区"宽（16.5cm）且整体偏左；
     按 LibreOffice 渲染值做成版心宽（14.75cm）会被判"长度不够"（2026-10-13 两次人工复审）。

用法：
  python verify_code_pdf.py <pdf> [--rows 60] [--report build/code-verify.txt]
"""
import argparse
import re
import sys
from pathlib import Path

try:
    import fitz
except ImportError:
    sys.exit("需要 PyMuPDF：pip install pymupdf")

# 校验结论含中文，且运行环境是 PowerShell；不改 stdout 编码时中文会乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

CM = 28.3465
HEAD_ZONE = 55          # y < 55 判为页眉区（实测页眉文字 y≈43）
FOOT_ZONE = 795         # y > 795 判为页脚区（实测页脚文字 y≈812）
PAGE_FOOT_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$")
PAGE_HEAD_RE = re.compile(r"^第\s*(\d+)\s*页$")


def collect(page):
    """取一页的文本，按 y 分成页眉 / 页脚 / 正文三组。

    页眉返回的是 **span 级**列表而非 line 级：左段文字较长时，PyMuPDF 会把
    "页眉左 + 页眉中"并进同一个 line（两段 x 相邻），按 line 计数会误判成
    "页眉只有两段"。判定按 x 分桶，与 PyMuPDF 的分行策略无关。
    """
    head, foot, body = [], [], []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            y0 = min(s["bbox"][1] for s in spans)
            if y0 < HEAD_ZONE or y0 > FOOT_ZONE:
                for s in spans:
                    item = {"y": s["bbox"][1], "x0": s["bbox"][0], "x1": s["bbox"][2],
                            "text": s["text"].strip(), "size": round(s["size"], 1)}
                    (head if y0 < HEAD_ZONE else foot).append(item)
                continue
            body.append({
                "y": y0,
                "x0": min(s["bbox"][0] for s in spans),
                "x1": max(s["bbox"][2] for s in spans),
                "text": "".join(s["text"] for s in spans).strip(),
                "size": round(spans[0]["size"], 1),
            })
    return head, foot, body


def split_header(head, center):
    """页眉按 x 中心分左 / 中 / 右三桶。"""
    left = [h for h in head if (h["x0"] + h["x1"]) / 2 < center - 60]
    mid = [h for h in head if abs((h["x0"] + h["x1"]) / 2 - center) <= 60]
    right = [h for h in head if (h["x0"] + h["x1"]) / 2 > center + 60]
    return left, mid, right


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--rows", type=int, default=60)
    ap.add_argument("--font-size", type=float, default=9.0)
    ap.add_argument("--line-height", type=float, default=12.0)
    ap.add_argument("--margin-top-cm", type=float, default=2.0)
    ap.add_argument("--margin-bottom-cm", type=float, default=2.0)
    ap.add_argument("--margin-left-cm", type=float, default=3.75, help="视觉页边距（版心左界）")
    ap.add_argument("--margin-right-cm", type=float, default=2.5)
    ap.add_argument("--line-left-cm", type=float, default=2.27,
                    help="页眉下横线左端（Word 页眉负缩进范围，默认 -1.48cm 相对版心左界）")
    ap.add_argument("--line-right-cm", type=float, default=19.61,
                    help="页眉下横线右端（默认版心右界 +1.11cm）")
    ap.add_argument("--report", default="", help="校验结论落盘路径")
    ap.add_argument("--expect-pages", type=int, default=0)
    a = ap.parse_args()

    doc = fitz.open(a.pdf)
    page_w, page_h = doc[0].rect.width, doc[0].rect.height
    left, right = a.margin_left_cm * CM, page_w - a.margin_right_cm * CM
    line_left, line_right = a.line_left_cm * CM, a.line_right_cm * CM
    bottom = page_h - a.margin_bottom_cm * CM

    log, fails = [], []
    log.append("PDF %s" % a.pdf)
    log.append("  页数 %d | 页面 %.1f x %.1f pt | 版心 x %.1f–%.1f, 底 %.1f"
               % (doc.page_count, page_w, page_h, left, right, bottom))

    lineno_seq, per_page_no = [], []
    max_x1, max_y = 0.0, 0.0
    bad_size, bad_slot, head_bad, foot_bad = [], [], [], []
    foot_size_bad, line_bad = [], []

    for pno in range(doc.page_count):
        head, foot, body = collect(doc[pno])
        idx = pno + 1

        # 行号列：位于版心左界之外的 span，且内容是纯数字
        nums = [int(b["text"]) for b in body
                if b["x0"] < left - 2 and b["text"].isdigit()]
        nums.sort()
        per_page_no.append(len(nums))
        lineno_seq.extend(nums)

        # 行槽：以该页最靠上的正文行为基准归并，防某页多塞一行
        if body:
            y_top = min(b["y"] for b in body)
            slots = {int(round((b["y"] - y_top) / a.line_height)) for b in body}
            if min(slots) != 0 or max(slots) > a.rows - 1:
                bad_slot.append("p%d 槽位 %d..%d" % (idx, min(slots), max(slots)))
            max_y = max(max_y, max(b["y"] for b in body))
            for b in body:
                if b["x0"] >= left - 2:      # 只算代码文本，不算行号
                    max_x1 = max(max_x1, b["x1"])
                    if abs(b["size"] - a.font_size) > 0.15:
                        bad_size.append("p%d %.1fpt %s" % (idx, b["size"], b["text"][:24]))

        # 页眉：左 / 中 / 右 三段齐全，右段"第 N 页"与页序一致
        leftseg, midseg, rightseg = split_header(head, (left + right) / 2)
        m = PAGE_HEAD_RE.match("".join(h["text"] for h in rightseg)) if rightseg else None
        if not leftseg or not midseg or not m or int(m.group(1)) != idx:
            head_bad.append("p%d 页眉段异常 左%d/中%d/右%d %s"
                            % (idx, len(leftseg), len(midseg), len(rightseg),
                               [h["text"] for h in head]))

        # 页脚：只有一行，且为 "N / M"；字号与正文同源（页脚不再单独放大加粗）
        foot_line = "".join(f["text"] for f in foot)
        multiline = foot and max(f["y"] for f in foot) - min(f["y"] for f in foot) > 3
        m = PAGE_FOOT_RE.match(foot_line) if foot else None
        if not m or multiline or int(m.group(1)) != idx or int(m.group(2)) != doc.page_count:
            foot_bad.append("p%d 页脚 %r（多行=%s）" % (idx, foot_line, bool(multiline)))
        elif abs(foot[0]["size"] - a.font_size) > 0.15:
            foot_size_bad.append("p%d 页脚 %.1fpt" % (idx, foot[0]["size"]))

        # 页眉下横线：长度必须等于 Word 页眉负缩进范围（默认 2.27→19.61cm），抽首页、中间页、末页
        if pno in (0, doc.page_count // 2, doc.page_count - 1):
            segs = [d["rect"] for d in doc[pno].get_drawings()
                    if d["rect"].height < 2 and d["rect"].width > 100]
            if not segs:
                line_bad.append("p%d 未找到横线" % idx)
            else:
                r = segs[0]
                if abs(r.x0 - line_left) > 2 or abs(r.x1 - line_right) > 2:
                    line_bad.append("p%d 横线 %.1f–%.1f（应在 %.1f–%.1f）"
                                    % (idx, r.x0, r.x1, line_left, line_right))

    # 判据 1：每页行数（非末页满页）
    short = [i + 1 for i, n in enumerate(per_page_no[:-1]) if n != a.rows]
    if short:
        fails.append("非末页行数不足 %d：第 %s 页" % (a.rows, short[:8]))
    if per_page_no and not (1 <= per_page_no[-1] <= a.rows):
        fails.append("末页行号数 %d 越界" % per_page_no[-1])
    total = sum(per_page_no)
    expect_pages = -(-total // a.rows) if total else 0
    if expect_pages != doc.page_count:
        fails.append("页数与行数不符：%d 行 / 每页 %d = 应 %d 页，实 %d 页"
                     % (total, a.rows, expect_pages, doc.page_count))
    if a.expect_pages and a.expect_pages != doc.page_count:
        fails.append("页数 %d ≠ 期望 %d" % (doc.page_count, a.expect_pages))

    # 判据 6：行号连续
    gaps = [(lineno_seq[i], lineno_seq[i + 1]) for i in range(len(lineno_seq) - 1)
            if lineno_seq[i + 1] != lineno_seq[i] + 1]
    if lineno_seq and lineno_seq[0] != 1:
        fails.append("行号未从 1 起：首号 %d" % lineno_seq[0])

    def report(ok, title, detail):
        log.append("  [%s] %s：%s" % ("PASS" if ok else "FAIL", title, detail))
        if not ok:
            fails.append(title)

    report(not short, "每页行数", "非末页均 %d 行；末页 %d 行（共 %d 行 / %d 页）"
           % (a.rows, per_page_no[-1] if per_page_no else 0, total, doc.page_count))
    report(not bad_slot, "行槽不越界", "每页槽位落在 0..%d" % (a.rows - 1)
           if not bad_slot else "；".join(bad_slot[:6]))
    report(max_x1 <= right + 1.0 and max_y <= bottom + 2.0, "版心不溢出",
           "最右 %.1f ≤ %.1f；末行 y %.1f ≤ %.1f" % (max_x1, right, max_y, bottom))
    report(not head_bad, "页眉三段", "%d 页均左/中/右齐全，右页码与页序一致" % doc.page_count
           if not head_bad else "；".join(head_bad[:6]))
    report(not foot_bad, "页脚一行", "N / M 格式、M = %d" % doc.page_count
           if not foot_bad else "；".join(foot_bad[:6]))
    report(not gaps, "行号连续", "连续 %d–%d（共 %d 行号）"
           % (lineno_seq[0], lineno_seq[-1], len(lineno_seq)) if not gaps
           else "断号 %s" % gaps[:6])
    report(not bad_size, "字号统一", "正文均 %.1fpt" % a.font_size
           if not bad_size else "；".join(bad_size[:6]))
    report(not foot_size_bad, "页脚字号", "与正文同为 %.1fpt（页脚与页眉同源）" % a.font_size
           if not foot_size_bad else "；".join(foot_size_bad[:6]))
    report(not line_bad, "页眉横线长度",
           "端点 %.1f–%.1f（Word 页眉负缩进范围，抽首页/中间页/末页）" % (line_left, line_right)
           if not line_bad else "；".join(line_bad[:6]))

    log.append("  结论：%s" % ("全部通过" if not fails else "未通过 %d 项 —— %s"
                              % (len(fails), "；".join(dict.fromkeys(fails)))))
    text = "\n".join(log)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text, encoding="utf-8")
    print(text)
    doc.close()
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
