# GraphRAG-Bench 全量评测说明

## 1. 文档目的

本文档规定本项目使用 GraphRAG-Bench 对 GraphRAG 系统进行正式评测的对象、数据、指标、运行方式和结果要求。本文档只记录项目事实、操作规范和评测结果，不记录对话内容或内部推理过程。

## 2. 评测范围

本阶段使用 GraphRAG-Bench 官方数据集中的两个子集：

| 子集 | 官方题目数 | 语料规模 | 题型 |
|---|---:|---:|---|
| Novel | 2010 | 20 篇文档，约 481.96 万字符 | Fact Retrieval、Complex Reasoning、Contextual Summarize、Creative Generation |
| Medical | 2062 | 1 个医学语料对象，约 105.22 万字符 | Fact Retrieval、Complex Reasoning、Contextual Summarize、Creative Generation |

官方题型数量核对结果：

| 子集 | Fact Retrieval | Complex Reasoning | Contextual Summarize | Creative Generation | 合计 |
|---|---:|---:|---:|---:|---:|
| Novel | 971 | 610 | 362 | 67 | 2010 |
| Medical | 1098 | 509 | 289 | 166 | 2062 |

官方题目文件中已经提供 `id`、题目、参考答案、题型和证据字段。本项目不修改官方题目、答案和证据，以保证结果可复现。Novel 还提供 `evidence_triple`，Medical 还提供 `evidence_relations`；这些字段作为证据结构信息保留在原始官方输入中。

官方基准仓库固定版本：

```text
仓库：https://github.com/GraphRAG-Bench/GraphRAG-Benchmark
提交：fdbab5959b18c96532580877ffe27d112bccc0ec
```

## 3. 当前系统配置

### 3.1 生成模型

- 模型：DeepSeek V4 Flash
- 调用方式：DeepSeek API
- 评测生成和指标判定使用同一模型配置
- thinking：disabled
- 运行中记录每道题的状态、耗时、输入/输出 token（如果接口返回）和错误信息

### 3.2 Embedding 模型

- 模型：本地 `Qwen/Qwen3-Embedding-0.6B`
- 建库和查询使用同一模型、同一服务地址、同一维度和同一归一化配置
- 评测中的语义相似度也调用同一套本地 Qwen embedding 服务，不切换为官方脚本默认的 BGE 模型
- 当前本机服务执行设备：Apple Silicon `mps`
- 为避免 macOS Metal 并发断言，当前正式运行将 `concurrent_requests` 固定为 `1`
- GraphRAG embedding 批量参数：`batch_size=32`、`batch_max_tokens=2048`
- 上述批量参数只影响请求分批方式，不改变模型、向量维度、归一化和输入文本；建库、查询与语义评测仍使用同一套 embedding 配置

### 3.3 首个 GraphRAG 方法

当前正式方法为 Microsoft GraphRAG 的 Local Search：

```text
官方语料
  ↓
文本切分
  ↓
实体与关系抽取
  ↓
社区发现与社区报告
  ↓
Qwen embedding
  ↓
Local Search 查询
  ↓
DeepSeek V4 Flash 生成答案
```

本阶段先得到可复现的 GraphRAG 结果。它不能单独证明 Graph 优于 Vector；后续必须在相同语料、相同题目、相同 DeepSeek 和相同 Qwen 配置下补跑 Vector baseline，再进行配对比较。

## 4. 官方指标

### 4.1 生成质量

官方指标按题型配置如下：

| 题型 | 指标 |
|---|---|
| Fact Retrieval | ROUGE-L、Answer Correctness |
| Complex Reasoning | ROUGE-L、Answer Correctness |
| Contextual Summarize | Answer Correctness、Coverage |
| Creative Generation | Answer Correctness、Coverage、Faithfulness |

### 4.2 检索质量

所有题型统一记录：

- Context Relevancy：检索上下文对回答当前问题的相关程度
- Evidence Recall：检索上下文能够覆盖官方证据的比例

### 4.3 索引与图结构质量

索引完成后使用官方 indexing evaluator 记录：

- 节点数、边数、平均度、图密度
- 连通分量数、最大连通分量规模
- 平均聚类系数、直径
- 连通分量规模统计
- 孤立节点数及不同度数阈值下的节点数

这些指标描述图结构，不等价于问答效果；必须与生成和检索指标分开解释。

### 4.4 工程运行指标

每次完整运行还记录：

- 题目总数、成功数、失败数、空答案数
- 各题型题量及成功率
- 平均和分位延迟（在汇总脚本中计算）
- 总 prompt token、总 output token（接口返回时）
- 运行配置、代码版本、benchmark commit、数据文件哈希

## 5. 官方题目的答案和标注边界

### 5.1 官方 benchmark 不需要重新出题

官方 Novel 和 Medical 题目、参考答案、证据已经固定。小组成员不得为了提高分数修改题目、答案或证据，也不需要为官方题目重新制作人工标签。

我们需要完成的是：

1. 确认官方文件未被修改；
2. 使用同一套索引和查询配置生成答案；
3. 将结果转换为官方评测器需要的字段；
4. 保存每题原始答案、检索上下文、状态和错误；
5. 使用固定版本的官方指标脚本计算结果；
6. 抽查不同题型的输入、输出和指标结果。

### 5.2 自建案例集才需要标注

后续为了展示 Graph 与 Vector 的真实差异，项目会建立独立的自建案例集。每道题建议至少包含：

```json
{
  "id": "case-001",
  "question": "问题文本",
  "question_type": "multi_hop_reasoning",
  "reference_answer": "参考答案",
  "required_evidence": ["必须支持答案的证据文本或文档 ID"],
  "acceptable_evidence": ["允许的等价证据 ID"],
  "entities": ["关键实体"],
  "relations": ["实体关系"],
  "expected_path": ["多跳路径"],
  "graph_expected_to_help": true,
  "ambiguity": false,
  "insufficient_evidence": false,
  "annotation_notes": "判定说明"
}
```

推荐的双人标注流程：

1. 第一人根据原始资料拟定问题、参考答案和证据；
2. 第二人在不看第一人说明的情况下独立复核；
3. 对答案、证据集合、实体和关系路径的冲突进行仲裁；
4. 在正式实验前冻结题目集版本；
5. 任何修改都新增版本并记录原因，不覆盖旧版结果。

## 6. 结果文件规范

每个子集、每种方法分别保存结果，不覆盖其他方法：

```text
experiments/outputs/
├── benchmark_novel/
│   ├── graphrag_local_answers.json
│   ├── graphrag_local_generation_eval.json
│   ├── graphrag_local_retrieval_eval.json
│   └── graphrag_local_summary.json
└── benchmark_medical/
    ├── graphrag_local_answers.json
    ├── graphrag_local_generation_eval.json
    ├── graphrag_local_retrieval_eval.json
    └── graphrag_local_summary.json
```

为便于小组成员直接复现实验，当前仓库已同步 GraphRAG-Bench 的官方数据文件和官方评测源码，位置为 `data/raw/benchmarks/GraphRAG-Benchmark/`。这些是固定的、对评测有直接用途的项目输入，不应由成员随意修改。GraphRAG 运行产生的索引、向量库、缓存、日志、完整问答输出和 Enron 原始压缩包仍属于本地运行产物，按 `.gitignore` 规则不进入 Git；代码、配置、数据来源说明、运行命令和汇总结果说明进入 Git。

每条问答结果至少保留：

- 官方题目 ID、题目、题型和参考答案
- GraphRAG 生成答案
- 检索上下文
- 官方证据
- 成功/空答案/API 错误状态
- 延迟、token 和错误信息
- 指标明细

## 7. 执行顺序和验收标准

```text
1. 固定官方 benchmark commit 与文件哈希
2. 准备 Novel/Medical 输入文件
3. 完成 Medical GraphRAG 建库
4. 完成 Novel GraphRAG 建库
5. 运行官方 indexing 指标
6. 全量生成 GraphRAG Local 答案
7. 全量运行 generation 指标
8. 全量运行 retrieval 指标
9. 生成题型分组和总体汇总
10. 抽查失败样本和异常指标
11. 再建立同配置 Vector baseline
12. 进行配对对比和失败归因
```

本阶段完成的最低验收条件：

- Novel 2010 道题和 Medical 2062 道题均有结果记录，或明确记录每一道失败原因；
- 四种题型均有分组结果；
- 生成、检索、索引三类指标分别有结果文件；
- 评测过程可以从断点继续，不因单题 API 错误丢失全量进度；
- 结果中明确区分 GraphRAG 当前绝对效果与后续 Vector 对照结论；
- 文档、配置和代码描述保持一致。

## 8. 当前进度

- [x] 固定 GraphRAG-Bench 官方仓库版本
- [x] 核对 Novel/Medical 官方题目规模和字段
- [x] 转换 Novel/Medical 输入数据
- [x] 编写全量 GraphRAG 查询脚本
- [x] 编写基于官方指标实现的断点评测脚本
- [x] Medical GraphRAG 建库

Medical 已完成并核验结构化索引和向量库：1 个文档、199 个文本单元、4,423 个实体、10,254 条关系、271 个社区；向量库已完成 entity description 4,423 行、community report 260 行、text unit 199 行的 embedding 写入。官方 indexing evaluator 已生成图结构指标：8,041 节点、10,254 边、最大连通分量 3,593、孤立节点 4,423、平均聚类系数 0.3881。社区报告有 260 条通过结构化 JSON 校验，少量 DeepSeek 返回 Markdown 代码围栏的报告被 GraphRAG 官方流程跳过，已作为异常记录。
- [ ] Novel GraphRAG 建库
- [ ] 全量生成答案
- [ ] 全量生成、检索、索引评测
- [ ] Vector baseline 对照

## 9. 下一步

等待两个语料的 GraphRAG 索引完成后，先计算索引指标，再按子集运行全量 Local Search 查询。查询结果完成后分别运行 generation 和 retrieval 评测，并在每个阶段保留可恢复的明细文件与汇总文件。
