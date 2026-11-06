# 实验结果与 Enron 案例

## 1. 系统与数据范围

本项目包括 Microsoft GraphRAG 索引基础、七种可切换检索方法、PathFusionRAG 融合策略、证据链与子图工作台，以及统一评测脚本。实验覆盖 GraphRAG-Bench、Enron Email 和六个公开问答数据集的多方法对照。

Enron Email 使用 CMU 公开邮件归档。已完成 517,401 封邮件的统一预处理与文件夹审计；California Power Crisis 案例从两个原始文件夹选择 66 封邮件建库：

- `maildir/dasovich-j/california_crisis/`：20 封。
- `maildir/dasovich-j/california_crisis__press/`：46 封。

这一范围保留了原始 source path、邮件关系和题目证据标注，便于检索结果回溯。

## 2. Enron 索引与问答实验

66 封邮件的 GraphRAG 索引已经完成，得到 66 个 documents、71 个 text units、644 个 entities、1,374 个 relationships、37 个 communities、35 个 community reports。一个社区报告因结构化文本包含控制字符而未生成，保留为索引质量记录。

GraphRAG 与 Vector RAG 的首轮对照已经完成，结果文件包括 `comparison_CA01.json`、`comparison_CA02.json`、`comparison_CA03.json` 和 `comparison_CC_66.json`。CA01、CA03 在证据召回方面体现有限的 Graph 优势，CA02 中 Vector 略优。各案例需要结合原文证据解释，而不是只依据最终答案判定。

主问题 CA01 追踪加州电力危机中信息收集、政策沟通和 Direct Access 立法讨论之间的跨邮件关系；其题目、参考答案及证据集合见 [CA01 题目设计](../experiments/enron_california_crisis/question_design_CA01.md)。其他题目见 `experiments/enron_california_crisis/questions.jsonl`。

## 3. GraphRAG-Bench

Medical 已完成图索引、2,062 道 Local Search 查询，以及全部 2,062 道的 generation 和 retrieval 评价。主要汇总指标如下：

| 指标 | Medical |
|---|---:|
| Answer Correctness | 0.363293 |
| ROUGE-L | 0.081630 |
| Coverage | 0.540099 |
| Faithfulness | 0.315056 |
| Context Relevancy | 0.662225 |
| Evidence Recall | 0.568109 |

retrieval 评价中，Complex Reasoning 和 Fact Retrieval 各有 168 道题的两个单项指标为 null；汇总均值跳过这些无法计算的值。

## 4. 公开数据集方法比较

系统已运行 Natural Questions、HotpotQA、2WikiMultiHopQA、MuSiQue、Qasper 和 QMSum 的多方法对照。工作台首页展示六个数据集的成绩表，其中 PathFusionRAG 在 Natural Questions、HotpotQA、2WikiMultiHopQA 和 Qasper 上取得本组比较中的最高分，HippoRAG 2 风格在 MuSiQue 更高，LightRAG 风格在 QMSum 更高。具体分数及方法结构见[GraphRAG 方法与实现细节](./GraphRAG方法调研与系统实现细节.md)。

## 5. 系统实现与实验入口

工作台在 `graphrag-workbench/` 中提供索引状态、七种检索方法、文本证据、图路径和子图展示。检索算法位于 `graphrag6-retrieval/`。项目实验采用 DeepSeek API 进行抽取和问答，本地 Qwen3-Embedding-0.6B 提供向量表示。

索引和批量实验输出保留于实验运行环境；仓库包含数据处理、索引配置、查询、评测与方法比较所需的代码及汇总说明。运行入口见[工作台 README](../graphrag-workbench/README.md)。

相关文件：[Enron 应用方案](./实际应用领域方案.md)、[数据处理范围](./Enron数据预处理与建库范围.md)、[评测方案](./评测方案.md)。
