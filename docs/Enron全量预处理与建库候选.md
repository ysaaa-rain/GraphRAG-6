# Enron 全量预处理与建库候选

> 记录日期：2026-09-08
>
> 当前状态：全量预处理已完成；California Power Crisis 的 66 封受控分母已经确定。上一轮 GraphRAG 建库已生成核心中间表但未出现最终完成标记，当前需恢复/验收；Vector baseline 尚未开始。

## 1. 输入与输出

| 项目 | 路径或结果 |
|---|---|
| 原始输入 | `data/raw/enron/source/maildir` |
| 规范化输出 | `data/processed/enron/full/messages.jsonl` |
| 预处理统计 | `data/processed/enron/full/preprocessing_stats.json` |
| 文件夹统计 | `data/processed/enron/full/folder_stats.json` |
| 解析异常 | `data/processed/enron/full/parse_errors.jsonl` |
| 输入邮件文件 | 517,401 |
| 成功规范化记录 | 517,401 |
| 解析失败 | 0 |
| 原始邮件字节数 | 1,421,183,736 |
| 正文字符数（清洗前） | 950,698,858 |
| 正文字符数（清洗后） | 903,113,805 |
| 清洗减少字符 | 47,585,053，约 5.0% |
| 规范化 JSONL 大小 | 2,516,875,780 bytes |

## 2. 处理规则

- 解析 MIME 邮件并单独保存 `From`、`To`、`Cc`、`Date`、`Subject`、`Message-ID` 和原始文件夹路径。
- 解码 MIME 标题和正文，优先使用 `text/plain`，没有纯文本时将 HTML 转换为文本。
- 统一换行、水平空白和空行，移除 NUL 字符。
- 跳过附件正文，但保留 `attachment_count`，避免把附件编码内容送入检索。
- 保留引用邮件行，不删除可能包含上下文的历史回复。
- 根据去除 `Re/Fw/Fwd` 前缀后的主题生成确定性的启发式 `thread_id`。
- 不重新命名主题、不重新分配文件夹、不把关键词命中当作主题标签。
- 每条记录保留 `source_path`，后续答案证据可以回到原始邮件。

## 3. California energy crisis 建库候选

### 建议候选：暂定 66 封

| 原始文件夹 | 文件数 | 日期范围 | 关键词邮件数 | 选择理由 |
|---|---:|---|---:|---|
| `maildir/dasovich-j/california_crisis` | 20 | 2000-08-04 至 2001-02-01 | California 8，energy 3，power 4 | 文件夹名称直接指向 California crisis；主题包含供需、FERC、政策、证券化、州长和 Direct Access 等连续议题。 |
| `maildir/dasovich-j/california_crisis__press` | 46 | 2000-08-09 至 2000-11-02 | crisis 8，California 34，energy 19，power 36 | 文件夹名称直接指向 California crisis；包含 blackout、power issue、deregulation、FERC、州长措施、媒体 talking points 等多封连续邮件。 |
| **合计** | **66** | **2000-08-04 至 2001-02-01** | — | **两个相邻主题文件夹，规模落在 50–100 封范围内。** |

这 66 封邮件共有约 53 个启发式主题线程，时间跨度约 6 个月；最终问题的“涉及邮件数”仍需人工阅读后按答案贡献确定，不能把 66 封全部自动宣称为必需证据。

### 暂不纳入的相邻文件夹

| 文件夹 | 文件数 | 暂不纳入理由 |
|---|---:|---|
| `maildir/kean-s/pr_crisis_management` | 92 | 虽然名称含 crisis，但内容主要混有 Teesside 爆炸、9/11、Enron 破产和媒体危机，不是同一个 California energy crisis 事件簇。 |
| `maildir/kean-s/crisis` | 1 | 只有一封 Emergency Callout List，不能形成跨邮件证据链。 |
| `maildir/kean-s/california` | 682 | 规模过大且主题混杂；可作为后续扩展候选，不作为当前 50–100 封分母。 |
| `maildir/shapiro-r/california` | 181 | 规模超出当前范围，且需要进一步确认是否与目标事件簇重合。 |

### 当前建库决定

已经确定本轮使用以下两个原始文件夹作为建库分母，不重新整理邮件主题，也不把关键词命中重新命名为主题：

```text
maildir/dasovich-j/california_crisis/        20 封
maildir/dasovich-j/california_crisis__press/ 46 封
合计                                          66 封
```

建库输入为 `data/processed/enron/california_crisis_66/documents.jsonl`，由全量规范化结果筛选而来；对应范围清单为 `data/processed/enron/california_crisis_66/scope_manifest.json`。上一轮 GraphRAG 索引只包含这 66 封，不是 30 封 S0，也不是 517,401 封全量邮件；当前已有部分核心产物但尚未验收。Vector baseline 必须在同一 66 封输入和同一配置下另行运行。

日志已经出现社区报告 JSON 控制字符警告，导致部分社区报告未生成；上一轮日志最后停在 text-unit embedding，`context.json` 为空，不能把现有 parquet/LanceDB 中间产物当作已验收结果。需要恢复或重跑索引，确认所有工作流有完成标记，并检查异常是否影响查询。

题目设计已完成：主问题 CA01 直接贡献 25 封唯一邮件，另有 CC01、CC02、CC03 三道同一 66 封分母下的辅助题。详细问题、证据和展示顺序见[项目当前状态与 Enron 展示交接](./项目当前状态与Enron展示交接.md)与[CA01 题目设计](../experiments/enron_california_crisis/question_design_CA01.md)。

## 4. 下一步验收

1. 等当前 66 封 GraphRAG 索引完成，核验所有输出表、向量库、日志和社区报告异常。
2. 从同一 66 封分母运行 CA01、CC01、CC02、CC03 的 GraphRAG 与 Vector 对照。
3. 保存每题两种方法的检索内容、答案、引用、source path、证据召回、路径覆盖、延迟和 token/cost。
4. 以 CA01 为主案例，结合 CC02 的关系链和 CC03 的图帮助有限/持平候选制作展示；CC01 视结果作为补充。
