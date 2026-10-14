# skill-payout

软著申报流水线技能：**排版交付**（payout，流水线第⑦环节）。把写好的 Markdown 变成可直接申报的 PDF 与干净 HTML，分**说明书模式**与**源代码模式**，各一套模板与脚本，**不得混用**。

## 功能与特点

**产出**：

- **说明书模式**（文档鉴别材料）：干净 HTML（目录页码已回填、图片相对引用）+ 审定 PDF（A4、页眉页脚每页各一套、目录页码与正文实际分页一致）+ 渲染审校截图；
- **源代码模式**（程序鉴别材料）：每页 60 行的源代码 HTML + PDF（页眉三段「软件名 V1.0 ｜ 程序鉴别材料 ｜ 第 N 页」+ 连续行号 + 页脚 `N / M`）+ 机械校验报告。

**功能**：① 说明书模式六步——装载与资产检查 → 解析说明书结构 → 结构核对（暂停确认）→ 图片预处理与引号归一 + 生成 HTML → 渲染审校（暂停确认）→ 打印 PDF + 回填目录页码 + 校验 + 归档；② 源代码模式五步——装载与资产确认 → 读汇总 md 并统计结构 → 结构核对（暂停确认）→ 生成 HTML 与打印 PDF → 渲染审校 + 九项机械校验 + 归档（暂停确认）；③ 五个内置脚本——md→HTML 转换桥（说明书 / 源代码各一）、目录页码静态回填、截图预处理、源代码 PDF 机械校验；④ 两套 HTML 排版模板（说明书版 / 源代码版）。

**特点**：① **AI 介入监督、不裸跑脚本**——G1–G8 围栏在关键节点停下等你拍板，转换前核对结构、转换后渲染审校再回填页码；② **文案零硬编码**——封面文案与页眉一律走命令行参数，脚本与模板内不写死项目名 / 版本号 / 文档类型，避免人工改过的文案被下一次运行覆盖回去；③ **不碰源 md**——引号归一落在同目录排版态副本上（T9），源 md 的内容语义与引号字形都不动，缺陷一律回上游 `project-guide` 修复；④ **版式以 Word 为准**——页眉下横线按 Word 页眉段落的负缩进范围（2.27→19.61cm）实现，不受 LibreOffice 渲染样本误导；⑤ **机械校验挡交付**——源代码 PDF 九项判据（每页行数、行槽、版心不溢出、页眉三段、页脚 N/M、页脚字号、行号连续、字号统一、页眉横线长度）未全 PASS 不得交付；⑥ **模板是权威源**——排版口径改动须经人工裁定，不得为单个项目擅调；⑦ **踩坑固化**——九条环境坑（行号被裁、页眉两套、伪粗体 Type3、编码乱码等）连同根因与处置写入 `SKILL.md`，同类问题不再重踩。

## 安装

本仓库是标准 Agent Skills 包（根目录含 `SKILL.md`），用 [`skills` CLI](https://github.com/vercel-labs/skills) 一键安装。

### 推荐：一条命令覆盖 opencode / pi / DeepSeek Harness

```
npx skills add YEZI186/skill-payout -a opencode -a pi -g -y
```

这三个 agent 都读取**通用 skills 目录** `~/.agents/skills/`，因此一次安装三方同时生效：

| Agent | 生效路径 | 说明 |
|---|---|---|
| opencode | `~/.agents/skills/payout/` | opencode 官方支持的通用 skills 目录（项目级为 `<项目>/.agents/skills/`） |
| pi | `~/.agents/skills/payout/` | pi 的全局 skills 目录 |
| DeepSeek Harness | `~/.agents/skills/payout/` | DSH 的 `agents` skill 来源，默认启用（见 `<DSH_HOME>/skills-manager/state.json`）；DSH 另支持自有目录 `<DSH_HOME>/skills/` |

> 安装目录名取自 `SKILL.md` 的 `name` 字段（`payout`），与仓库名 `skill-payout` 不同属正常。

### 其他 agent

```
npx skills add YEZI186/skill-payout -a claude-code -g -y    # 指定单个 agent
npx skills add YEZI186/skill-payout -a cursor -g -y
npx skills add YEZI186/skill-payout --all                   # 安装到全部已探测到的 agent
npx skills ls -g                                            # 查看已安装
npx skills remove payout -g                                 # 卸载
```

### 装到 DeepSeek Harness 自有目录（可选）

只使用 DSH，或希望把 skill 放在 DSH 自有目录（便于本地改动规则）时：

```
git clone https://github.com/YEZI186/skill-payout.git "<DSH_HOME>/skills/payout"
```

`<DSH_HOME>` 默认 `~/.dsh`（Windows 为 `C:\Users\<用户名>\.dsh`），即最终路径 `~/.dsh/skills/payout/`。

## 目录结构

```
SKILL.md                                  # 规则单一来源：定位、铁律 T1–T9、围栏 G1–G8、双模式流程、环境坑、产物规范、命令速查
assets/build_html_from_md.py              # 说明书模式：md → HTML 转换桥
assets/backfill_toc.py                    # 说明书模式：目录页码静态回填（幂等，可重跑）
assets/optimize_images.py                 # 说明书模式：截图入交付目录（默认原图不处理）
assets/软著操作说明书-HTML模板.html          # 说明书版式权威源
assets/build_code_html.py                 # 源代码模式：汇总 md → 每页 60 行 HTML
assets/verify_code_pdf.py                 # 源代码模式：PDF 九项机械校验（退出码 0/1，结论可落盘）
assets/软著源代码-HTML模板.html             # 源代码版式权威源
```

## 依赖

- **Python 3.10+**：五个内置脚本仅用标准库；
- **打印 PDF**：由 AI 侧用 Playwright 的 `page.pdf()` 执行（`preferCSSPageSize: true` + `displayHeaderFooter: false`，不传 `margin`），不使用无头 Chrome 直启；
- **跨包依赖（说明书模式，只调用不复制）**：`project-guide` 的 `scripts/normalize-quotes.mjs`（引号归一，奇偶不配即阻断）与 `scripts/guide-check.mjs`（弯引号三项复核）。两者归 `project-guide` 所有，缺失时在第一步资产检查处即停。

## 不属本 skill 的事

- **说明书内容的撰写与修订**——归 `project-guide`（本 skill 在任何情况下都不修改源 md）；
- **AIGC 指纹处理与申报一致性审查**——归 `aigc-w` / `aigc-c` / `project-review`；
- **排版模板口径的自行调整**——模板是权威源，改口径须经人工裁定。

## 许可

MIT，见 [LICENSE](LICENSE)。
