# Enron 数据预处理与建库范围

> 当前状态：全量邮件预处理已完成，California Power Crisis 66 封索引已完成并通过检查，GraphRAG/Vector 首轮对照已运行。

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

## 3. California Power Crisis 建库范围

### 受控语料：66 封

| 原始文件夹 | 文件数 | 日期范围 | 关键词邮件数 | 选择理由 |
|---|---:|---|---:|---|
| `maildir/dasovich-j/california_crisis` | 20 | 2000-08-04 至 2001-02-01 | California 8，energy 3，power 4 | 文件夹名称直接指向 California crisis；主题包含供需、FERC、政策、证券化、州长和 Direct Access 等连续议题。 |
| `maildir/dasovich-j/california_crisis__press` | 46 | 2000-08-09 至 2000-11-02 | crisis 8，California 34，energy 19，power 36 | 文件夹名称直接指向 California crisis；包含 blackout、power issue、deregulation、FERC、州长措施、媒体 talking points 等多封连续邮件。 |
| **合计** | **66** | **2000-08-04 至 2001-02-01** | — | **两个相邻主题文件夹，规模落在 50–100 封范围内。** |

这 66 封邮件共有约 53 个启发式主题线程，时间跨度约 6 个月；每道问题的必需证据按人工标注的答案贡献确定，不能把 66 封全部自动宣称为必需证据。

### 未纳入的相邻文件夹

| 文件夹 | 文件数 | 排除理由 |
|---|---:|---|
| `maildir/kean-s/pr_crisis_management` | 92 | 虽然名称含 crisis，但内容主要混有 Teesside 爆炸、9/11、Enron 破产和媒体危机，不是同一个 California energy crisis 事件簇。 |
| `maildir/kean-s/crisis` | 1 | 只有一封 Emergency Callout List，不能形成跨邮件证据链。 |
| `maildir/kean-s/california` | 682 | 规模较大且主题混杂，不属于当前受控分母。 |
| `maildir/shapiro-r/california` | 181 | 规模超出当前范围，且需要进一步确认是否与目标事件簇重合。 |

### 建库输入与产物

已经确定本轮使用以下两个原始文件夹作为建库分母，不重新整理邮件主题，也不把关键词命中重新命名为主题：

```text
maildir/dasovich-j/california_crisis/        20 封
maildir/dasovich-j/california_crisis__press/ 46 封
合计                                          66 封
```

建库输入为 `data/processed/enron/california_crisis_66/documents.jsonl`，由全量规范化结果筛选而来；对应范围清单为 `data/processed/enron/california_crisis_66/scope_manifest.json`。GraphRAG 索引使用这 66 封受控输入，生成 66 个 documents、71 个 text units、644 个 entities、1,374 个 relationships、37 个 communities 和 35 个 community reports。Vector baseline 采用同一批邮件；比较结果保存在对应的 CA 和 CC 题组文件中。

索引已完成，并已用于 GraphRAG/Vector 首轮对照。一个社区报告因 JSON 控制字符未生成，最终保留 35 个 community reports；该缺失作为索引质量限制保留，不能将社区报告覆盖视为完整。

题目设计包括主问题 CA01（25 封证据邮件）和同一 66 封分母下的 CC 题组；另外已运行 CA02 和 CA03 的 Graph/Vector 对照。详细问题、证据和展示顺序见[实验结果与 Enron 案例](./实验结果与Enron案例.md)与[CA01 题目设计](https://github.com/ysaaa-rain/GraphRAG-6/blob/main/experiments/enron_california_crisis/question_design_CA01.md)。
