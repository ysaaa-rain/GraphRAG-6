# 项目当前状态与 Enron 展示交接

> 更新日期：2026-09-08
>
> 用途：给组员准备结果展示，统一记录已经确认的范围、真实实验进度、Enron 代表性问题和运行后的结论填写方式。

## 1. 先看结论

当前项目已经确定为三条正式主线：GraphRAG-Bench Novel、GraphRAG-Bench Medical，以及 Enron Email 实际应用。现在还没有任何结果可以预先写成“GraphRAG 一定优于 Vector RAG”；最终结论必须以同数据、同模型、同问题的逐题结果为依据。

| 工作项 | 当前状态 | 说明 |
|---|---|---|
| 正式范围和技术路线 | 已确定 | 不再新增第四个正式数据集；GraphRAG 核心引擎基本保持不动，重点建设数据处理、统一评测、Vector baseline、证据展示和界面。 |
| Enron 全量预处理 | 已完成 | 已处理 517,401 封邮件，生成统一字段、线程键和文件夹审计结果；这一步不是 GraphRAG 建库。 |
| Enron 建库分母 | 已确定 | 只选两个原始文件夹，共 66 封：`california_crisis` 20 封，`california_crisis__press` 46 封；不把 517,401 封全部建库。 |
| Enron GraphRAG 建库 | 部分产物已生成，待恢复/验收 | 上一轮运行的是这 66 封，不是 30 封 S0，也不是 517,401 封全量；核心表和部分向量目录已生成，但日志停在 embedding 阶段，没有最终完成标记，当前未检测到仍在运行的索引进程。 |
| Enron Vector baseline | 待 GraphRAG 索引完成后运行 | 必须使用同一 66 封、同一切分、同一 Qwen embedding、同一 DeepSeek 和相同回答协议。 |
| Enron 代表性问题 | 已选定 | 主问题 CA01，辅以 CC01、CC02、CC03；共 4 题，最后可按运行时间和结果选择 3–4 题展示。 |
| Medical benchmark | GraphRAG 建库和 2,062 题查询已完成；generation 评测运行中 | generation 使用独立 `.venv-benchmark`，沿成功 checkpoint 断点续跑；完成后还要运行 retrieval 评测。 |
| Novel benchmark | 待开始 | Medical 当前阶段结束后进入 Novel。 |
| 最终展示 | 正在准备材料 | 现在可以准备问题、参考答案、检索上下文和展示版式；Graph/Vector 的胜负要等实际运行结果。 |

## 2. 已经做出的固定决策

### 2.1 项目范围

- 正式 benchmark 只有 GraphRAG-Bench Novel 和 Medical。
- 正式实际应用只有 Enron Email，不再扩展新的领域。
- 《红楼梦》、HotpotQA、MuSiQue、2WikiMultiHopQA 等只保留为历史或备用参考，不进入当前最终结果。

### 2.2 模型和公平对照

- 生成、实体/关系抽取和回答：DeepSeek V4 Flash API。
- embedding：本地 `Qwen/Qwen3-Embedding-0.6B`，固定 revision、1024 维和归一化配置。
- Vector、GraphRAG 和可选 Hybrid 必须使用同一批原文、同一 chunk 规则、同一 embedding、同一 LLM、同一回答协议和可比的上下文预算。
- 结果必须逐题保留答案、检索上下文、source path、证据召回、延迟、token 和错误状态。
- 关闭继承来的仓库级 GitHub Actions，不代表降低本地测试、集成测试、端到端评测和结果审计要求。

### 2.3 Enron 数据范围

全量预处理用于保证数据资产完整和后续可扩展；本轮建库为了控制 API 和索引成本，只采用已确认的 66 封受控分母：

```text
data/processed/enron/california_crisis_66/documents.jsonl
    ├── maildir/dasovich-j/california_crisis/       20 封
    └── maildir/dasovich-j/california_crisis__press/ 46 封
```

不重新给邮件分配新主题，不根据关键词重新聚类；保留原始 mailbox folder 作为选择依据。`messages.jsonl` 是全量邮件预处理产物，不是建库之后的图谱产物；66 封建库输入是从它筛选出的独立 `documents.jsonl`。

## 3. Enron 展示题集

当前 Enron 题目文件分为两部分：`experiments/enron_california_crisis/questions_CA01.jsonl` 单独保存最重要的 CA01，`experiments/enron_california_crisis/questions.jsonl` 保存此前已经整理好的 CC01、CC02、CC03。这样既能单独优先运行 CA01，也不会覆盖组员已有题目；CA01 的完整人工设计和 25 封证据邮件见[CA01 题目设计](../experiments/enron_california_crisis/question_design_CA01.md)。

| 优先级 | ID | 题型与展示作用 | 设计阶段涉及邮件 | 预期观察 |
|---:|---|---|---:|---|
| 1 | CA01 | 主问题：跨信息收集、内部协调、FERC 政策讨论到 Direct Access 立法的多人物、多实体、多跳关系链。 | 25 封唯一邮件（20 必需 + 5 相邻） | 最有希望看到 GraphRAG 在实体—关系—时间链上的优势；必须等实测确认。 |
| 2 | CC02 | 人物/组织角色链：从媒体和数据库协调，到 FERC comments，再到 Direct Access coalition。 | 13 封唯一邮件 | 论证图结构对“谁通过什么组织参与了什么政策过程”的帮助。 |
| 3 | CC03 | 46 封 press 邮件中的政策回应和 deregulation 竞争观点，并区分事实、提案和评论。 | 20 封唯一邮件 | 作为“图帮助有限或两者接近”的候选；它更偏主题总结，不要预先宣称 Graph 获胜。 |
| 4 | CC01 | 2000 年 8 月到 2001 年 2 月的危机诊断和州/联邦政策回应演化。 | 14 封唯一邮件 | 作为跨时间全局总结备选；与 CA01 部分重叠，时间有限时可不单独展示。 |

### 展示优先顺序

建议组员先跑并优先展示：

1. **CA01**：主案例，回答“图为什么可能帮助跨邮件、多跳关系组织”。
2. **CC02**：补充人物—组织—政策的关系路径，避免结论只依赖一题。
3. **CC03**：补充同一主题下图结构可能没有明显增益的情况，体现诚实边界。
4. **CC01**：若结果与 CA01 呈现出不同差异，再加入时间演化案例；否则作为备份材料。

之前的 Alice、Bob、Charlie、Project X 示例没有真实 Enron 邮件依据，不进入正式展示。旧材料中的单封 ICE/eRequest 对照题也不在这 66 封建库分母内，不能直接与本轮结果混合。

## 4. Enron 运行状态和已知检查点

### 4.1 GraphRAG 索引

恢复/重跑 Enron 66 封索引时使用：

```bash
./.venv/bin/python -m graphrag index \
  --root experiments/enron_california_crisis \
  --method standard \
  --verbose
```

上一轮日志显示 66 个文档完成输入加载、切分、实体关系抽取和社区创建，并在 text-unit embedding 阶段停止；当前没有检测到仍在运行的索引进程，因此不能把当前目录里的中间 parquet 文件当成最终完成结果。需要恢复或重跑，确认所有输出表、向量库、日志末尾和 `context.json` 的最终状态。

日志中出现过一条社区报告 JSON 校验警告：某报告包含控制字符，导致 community `10.0` 没有报告。该问题需要在索引完成后确认是否只是单个社区报告缺失、是否影响查询；展示时不能隐瞒，应记录为已知限制或修复后重跑。

### 4.2 Medical benchmark

- Medical GraphRAG 结构化索引已完成，Local Search 查询已完成 2,062/2,062，全部返回非空答案和检索上下文。
- 已生成索引结构指标；generation 官方评测正在运行，并使用成功 checkpoint 断点续跑。
- 由于 MPS 长文本语义评测曾触发本地服务原生退出，当前 generation 评测使用 CPU embedding、并发 1；模型、revision、维度和归一化参数不变。
- generation 完成后运行 retrieval，再汇总四种官方题型；在官方评测结束前不要写 Medical 最终分数。

## 5. 组员结果展示所需内容

每道最终展示题统一准备一张或一组对照页，顺序固定为：

```text
问题
  ↓
参考答案与人工证据范围
  ↓
Vector RAG：检索到的 source path、文本片段、答案、引用
  ↓
GraphRAG：实体、关系/子图、检索到的 source path、答案、引用
  ↓
指标与人工判定
  ↓
为什么 Graph 更好、Vector 更好、或两者接近
```

每题至少填写：

- GraphRAG 答案原文；
- Vector RAG 答案原文；
- 两者各自检索到的 source path 和关键上下文；
- 必需证据召回数/总数，必要时补充可接受相邻证据召回；
- 答案是否覆盖关键人物、关系、政策对象和多跳路径；
- 延迟、LLM 调用次数、输入/输出 token 和估算成本；
- 最终人工结论：Graph 优于 Vector、Vector 优于 Graph、两者接近，或两者均失败；
- 结论依据和失败原因，不能只写“GraphRAG 更先进”。

运行后可使用以下入口生成 Enron 的逐题 Graph/Vector 原始结果：

```bash
./.venv/bin/python scripts/run_enron_comparison.py \
  --root experiments/enron_california_crisis \
  --questions experiments/enron_california_crisis/questions_CA01.jsonl \
  --output experiments/outputs/enron_california_crisis/comparison.json
```

该命令示例先运行 CA01。索引恢复并通过基本检查后，再用相同命令把 `--questions` 换成 `experiments/enron_california_crisis/questions.jsonl`，输出到另一个文件，例如 `comparison_CC01_CC03.json`。输出文件属于本地运行产物，不提交大体积结果或 API 缓存。

## 6. 当前还不能写成已完成的内容

- Enron 还没有完成 Vector baseline，因此还没有 GraphRAG 对 Vector RAG 的实测优劣结论。
- Enron 当前不是 517,401 封全量建库，而是 66 封受控分母建库；汇报时必须明确这一点。
- Medical 的 generation/retrieval 指标尚未全部结束，不能只展示已完成的查询数量就宣称 benchmark 完成。
- CA01 的“GraphRAG 预计更强”是问题设计假设，不是实验事实；如果 Vector 召回足够完整，必须如实报告两者接近。

## 7. 交接后最短路径

1. 恢复或重跑 Enron 66 封索引，并完成日志/输出验收。
2. 先用 `questions_CA01.jsonl` 运行 CA01，再用 `questions.jsonl` 运行 CC01、CC02、CC03 的 GraphRAG 与 Vector 对照。
3. 对每题保存答案、上下文、source path、证据召回、延迟和 token。
4. 按“主案例 + 关系链补充 + 图帮助有限/持平案例”制作展示页。
5. Medical generation 完成后运行 retrieval，最后再处理 Novel 和整体汇报归档。

相关文档：

- [CA01 题目设计](../experiments/enron_california_crisis/question_design_CA01.md)
- [Enron 全量预处理与建库范围](./Enron全量预处理与建库候选.md)
- [GraphRAG-Bench 全量评测说明](./GraphRAG-Bench全量评测说明.md)
- [阶段计划与执行清单](./阶段计划与执行清单.md)
