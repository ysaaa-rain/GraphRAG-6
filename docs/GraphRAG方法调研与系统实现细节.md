# GraphRAG 方法调研与系统实现细节

> 文档状态：已完成第一版代码实现与静态检查。本文描述当前仓库中的真实实现边界；没有把尚未运行的线上评测分数写成结论。更新时间：2026-09-11。

## 1. 目标和实现边界

本阶段的目标不是把多个第三方仓库硬拼在一起，而是在已有 Microsoft GraphRAG 索引上提供统一、可切换、可解释的查询层：

1. 保留 `microsoft_local`、`microsoft_global`、`microsoft_drift` 和 `microsoft_basic` 原始入口。
2. 增加 LightRAG 思路的双层检索和 HippoRAG 2 思路的 Personalized PageRank 多跳检索。
3. 增加本项目自己的 `hybrid_path`：BM25 词项、已有 GraphRAG dense vector index、图路径邻近度三路融合，并限制最大跳数。
4. 所有方法都返回统一的 `SearchResult` 和 `RetrievalTrace`，前端可以显示同样的实体—关系—文本证据链，评测脚本可以读取同样的路径字段。
5. 查询结束后将 trace 追加写入数据集的 `output/retrieval_traces.parquet`，不修改原有 entities、relationships、text_units 和 community reports 表。

这里的 “LightRAG 风格” 和 “HippoRAG 2 风格” 是基于论文机制对当前 GraphRAG schema 的工程适配，不声称是两个项目的官方 reference implementation。这样处理的原因是当前项目已经有完整的 Microsoft GraphRAG 3.1.2 Parquet/LanceDB 产物；直接接入两个不同的完整索引器会引入不同的切分、实体抽取、embedding 和 LLM 条件，无法进行公平对照。

## 2. GraphRAG 发展路线和候选方法

### 2.1 Microsoft GraphRAG：从 Local 到 Global

Microsoft GraphRAG 的核心是：先用 LLM 从原文抽取实体和关系，再做社区发现，并为社区生成报告。Global Search 将社区报告分批 map 成局部答案，再 reduce 成最终回答；Local Search 则从与问题相近的实体出发，组合实体、关系、社区报告和关联文本；DRIFT 在社区信息基础上进行迭代式探索；Basic Search 是文本 chunk 的向量 RAG 基线。

它解决的是普通 chunk top-k 很难回答的全局主题和跨文档关联问题。代价是索引期需要大量 LLM 抽取和社区摘要，且 Global 的每次查询可能需要多次 map/reduce 调用。当前仓库使用 `graphrag==3.1.2` 的 API，不改写 Microsoft 原有检索代码。

### 2.2 LightRAG：双层实体/关系检索

LightRAG 的论文将索引和检索都组织成图，并在查询时区分：

- 低层关键词：问题中的具体实体、属性和细节；
- 高层关键词：问题的主题、任务和整体语义。

两路关键词都用于检索，但检索目标不是直接拿 chunk，而是先找实体和关系，再将对应文本拼回上下文。论文强调图结构与向量表示结合，以及增量更新。官方仓库还提供 local、global、hybrid、naive、mix 等运行模式。

本项目适配实现：

1. 对 `entities` 表的 `title/type/description` 做 BM25 式低层候选匹配。
2. 对 `community_reports` 的 `title/summary/full_content` 做高层候选匹配。
3. 将高层命中的 community 反向映射到 `communities.entity_ids`，补充低层没有直接命中的实体。
4. 对选中实体诱导出关系，依据关系词项分数或图内关系分数排序。
5. 通过 `entity_ids` 和 `relationship_ids` 反向取回 `text_units`，形成实体—关系—文本上下文。

它的理论优势是覆盖面较好，特别适合主题总结、多个相关实体共同回答、跨文档信息整合；它的风险是高层社区扩张可能带来噪声，且缺少 HippoRAG 式的显式概率传播。

### 2.3 HippoRAG 2：图上的长期记忆和多跳传播

HippoRAG 2 延续 HippoRAG 的思路，用 LLM 构建知识图谱，再用 Personalized PageRank（PPR）将查询命中的实体种子向邻域传播。论文将其解释为把实体关联保存在外部长期记忆中；ICML 2025 版本强调更深的 passage integration 和更有效的在线 LLM 使用，并报告在 associative memory 任务上的提升。

本项目适配实现：

1. 用实体 BM25 分数和可选 entity dense 分数形成 seed personalization。
2. 将关系权重作为图边权；图按无向邻接处理，避免邮件/文档关系方向不稳定时完全丢失关联。
3. 迭代计算：

   `p_(t+1) = alpha * s + (1 - alpha) * P^T * p_t`

   默认 `alpha=0.15`，30 次迭代；`s` 是归一化种子分布，`P` 是按边权归一化的转移矩阵。
4. 用 `0.65 * PPR + 0.35 * seed_score` 排序实体，选中实体之间的关系，并把这些实体关联的 passages 整合进上下文。
5. 用 BFS 找出 seed 到命中实体的最短图路径，限制最大 hop 为 2，避免全图扩散。

它的理论优势是对多跳和隐式关联更友好：即使第二跳实体没有与问题直接共享词项，也可能因为邻域传播得到较高分；它的风险是图质量会直接影响传播，错误边、超级节点和关系权重异常都可能把噪声扩散到答案上下文。对单事实问题，PPR 的额外成本可能不如 Basic/Vector。

### 2.4 其他 2025 方向

调研中还记录了以下方向，但本轮没有作为第三个外部方法直接接入：

- **FG-RAG**：在图检索中做 Context-Aware Entity Expansion，并在回答前做 query-level fine-grained summarization，目标是改善 query-focused summarization 的细节和覆盖。
- **E²GraphRAG**：用更轻的实体抽取、summary tree、entity/chunk 双向索引和自适应 local/global 选择，主打效率；论文报告相对于 GraphRAG 和 LightRAG 的索引/检索速度优势，但其索引 schema 与本项目不同。
- **QCG-RAG**：用 Doc2Query/Doc2Query-- 构建 query-centric graph，以可控粒度处理细粒度实体图和粗粒度文档图之间的取舍，重点是多跳 chunk retrieval。
- **LazyGraphRAG**：Microsoft 研究方向，核心思想是延迟昂贵的图摘要工作，将成本从索引期移到需要时；官方 GraphRAG 仓库已经进入维护模式，LazyGraphRAG 的完整公开方法和可直接复用的查询 API 仍不如当前两个论文/代码组合清晰，因此本阶段不把“实现了 LazyGraphRAG”写入结论。

这些工作说明 GraphRAG 的发展大致沿着四条线推进：降低索引成本、从社区摘要转向实体/关系直接检索、增强多跳传播、以及让检索粒度和查询意图更自适应。

## 3. 为什么选择这两个方法

不存在脱离数据集、任务和 LLM 的唯一“效果最好” GraphRAG。Global QFS、单事实、跨文档多跳和动态增量的最优点不同，论文的 benchmark、LLM、prompt 和指标也不同。因此本项目采用可证据支持的工程选择：

| 方法 | 最可能的优势问题 | 主要代价/风险 | 本项目结论 |
|---|---|---|---|
| Microsoft Global | 全局主题、跨社区总结 | 预生成社区报告昂贵，map/reduce 延迟高 | 保留作官方全局基线 |
| Microsoft Local | 具体实体、局部关系、可回溯文本 | 依赖实体向量和局部 seed，可能漏掉隐式多跳 | 保留作官方局部基线 |
| LightRAG 风格 | 多主题覆盖、低层细节与高层主题同时出现 | 社区扩张噪声，依赖高质量社区报告 | 作为结构化双路候选 |
| HippoRAG 2 风格 | 多跳、关联记忆、跨实体传播 | 图噪声传播；单事实可能过度扩张 | 作为路径/多跳候选 |
| Hybrid Path（本项目） | 需要同时兼顾精确词项、语义相似和可解释路径 | 权重需要在验证集上校准；没有 dense index 时退化为 lexical+graph | 作为默认创新候选，待评测确认 |

理论上不能直接写成“Hybrid Path 一定优于所有方法”。更严谨的预期是：

- 全局总结：Microsoft Global 或 LightRAG 风格更有优势，因为它们能覆盖多个社区/主题。
- 直接事实：Microsoft Basic 或 Hybrid Path 更有优势，因为 BM25/dense 证据不会无必要地扩散。
- 明确多跳：HippoRAG 2 风格或 Hybrid Path 更有优势，因为它们显式保留图路径。
- 关键词表达不稳定、但语义明确：dense channel 和 PPR 能补充词项匹配。
- 图谱抽取存在错误：Basic、Hybrid 的文本直达分支比纯 PPR 更稳健。

正式结论必须根据本项目的 Enron 和 GraphRAG-Bench 逐题结果填写，不能用论文跨数据集分数替代。

## 4. 本项目创新：Hybrid Path GraphRAG

### 4.1 设计动机

Microsoft Local 的问题是图检索和文本证据虽然有关联，但返回结果的完整图路径没有统一保存；Basic/Vector 的问题是能找到相似文本，却无法回答“为什么这些文本通过哪些实体和关系连起来”。PPR 能扩大多跳召回，但可能把不相关邻域带入上下文。

因此 `hybrid_path` 把三类分数放在同一候选层：

`score(text) = 0.35 * lexical_bm25 + 0.35 * dense_vector + 0.30 * graph_path_proximity`

默认权重是可读的初始值，不是训练得到的最优权重，后续应在固定验证问题集上做消融和网格校准。

### 4.2 查询流程

1. 在 entity、relationship 和 text unit 上做 BM25-style lexical scoring。
2. 如果 settings 中已有 Microsoft GraphRAG 的 text/entity LanceDB 或其他 VectorStore，使用其 `similarity_search_by_text` 得到 dense scores；如果 vector store 不可用，dense channel 为空，不伪造向量分数。
3. 取高分实体作为 seed。
4. 对每个 seed 和文本关联实体做最大 2-hop BFS；找到路径时，按 `seed_score / (1 + hops)` 得到 graph path proximity。
5. 对每个 text unit 融合三路分数；保留 top-k source。
6. 将路径经过的实体加入子图，诱导出子图边，同时将来源文本、实体、关系、路径一起交给 LLM。
7. 在 trace 中保存每个 channel 的分数和最终权重，因此可以解释某一证据是词项、向量还是图路径带来的。

### 4.3 这算不算新的 GraphRAG

它不是新的预训练模型，也不是声称发表级新算法；它是一个原理清晰、规模适中的系统创新：

- 将现有 Microsoft GraphRAG dense index 作为一个可选检索通道，而不是重建 embedding；
- 将路径约束作为 GraphRAG 的精确性门控，防止无限邻域扩张；
- 将路径、子图和证据链作为一等输出字段，而不是只在 prompt 内临时拼接；
- 用同一界面和同一 trace schema 对比官方 GraphRAG、LightRAG 风格、HippoRAG 2 风格和本方法。

## 5. 代码结构和运行时数据流

### 5.1 关键文件

| 文件 | 职责 |
|---|---|
| `unified-search-app/app/rag/typing.py` | `SearchMethod`、`SearchType`、`SearchResult`、`RetrievalTrace` 数据契约 |
| `unified-search-app/app/rag/retrieval.py` | BM25、图邻接、PPR、BFS、三种自定义检索策略和 recall 计算 |
| `unified-search-app/app/rag/custom_search.py` | 复用 GraphRAG VectorStore、embedding model 和 LLM completion |
| `unified-search-app/app/rag/trace_store.py` | 将嵌套 trace 字段编码后 append 到 Parquet |
| `unified-search-app/app/app_logic.py` | 方法 registry、Microsoft API 调用、自定义方法调度、trace 持久化 |
| `unified-search-app/app/ui/sidebar.py` | 多选方法控件 |
| `unified-search-app/app/home_page.py` | 动态生成方法对照列和证据区 |
| `unified-search-app/app/ui/search.py` | 表格、证据链、JSON 字段和 Graphviz 子图 |
| `unified-search-app/app/knowledge_loader/*` | 读取 entities、relationships、text_units、documents 等表 |

### 5.2 统一方法 registry

`run_all_searches` 将左侧多选值转换为 `SearchMethod`，再映射到 runner：

```text
microsoft_basic  -> graphrag.api.basic_search
microsoft_local  -> graphrag.api.local_search
microsoft_global -> graphrag.api.global_search
microsoft_drift  -> graphrag.api.drift_search
lightrag         -> GraphRetriever.retrieve(LIGHTRAG)
hipporag2        -> GraphRetriever.retrieve(HIPPORAG2)
hybrid_path      -> GraphRetriever.retrieve(HYBRID_PATH)
```

所有 runner 最终都通过 `_record_result`：渲染答案、保存 trace、追加当前 session 的结果记录。这样新增方法不会再复制一套不同的结果字段。

### 5.3 自定义方法的向量 fallback

`create_embedding_resources` 会分别尝试加载：

- `text_unit_text` VectorStore；
- `entity_description` VectorStore；
- 当前 settings 中 `basic_search.embedding_model_id` 对应的 embedding model。

某一个 store 不存在时，其他资源仍可使用；三个资源都不可用时，自定义方法仍然可以用 BM25 和图算法运行，但 trace 的 `channel_scores.dense_vector` 为空。答案生成仍使用当前 settings 的 local-search completion model，并统一使用证据约束 prompt。

## 6. GraphRAG 输出 schema 和路径构造

### 6.1 输入表

系统读取以下 GraphRAG 输出：

- `output/entities.parquet`：至少需要 `id/title/description`，可选 `type/degree/community/text_unit_ids`；
- `output/relationships.parquet`：至少需要 `id/source/target/description`，可选 `weight/rank/text_unit_ids`；
- `output/text_units.parquet`：至少需要 `id/text`，可选 `entity_ids/relationship_ids/document_id/source_path/attributes`；
- `output/communities.parquet` 和 `output/community_reports.parquet`：用于 LightRAG 风格高层检索；
- `output/documents.parquet`：可选，用于从 `document_id` 回溯 source path。

ID 解析同时支持稳定 `id`、`human_readable_id`、`short_id` 和 entity title，以兼容不同 GraphRAG 版本的输出。

### 6.2 子图和路径

关系的 source/target 先解析到实体 ID，再构建双向邻接表。每一条路径记录：

```json
{
  "path_id": "path-1",
  "entity_ids": ["entity-a", "entity-b", "entity-c"],
  "relationship_ids": ["relationship-ab", "relationship-bc"],
  "hops": 2,
  "score": 0.73,
  "target_text_id": "text-unit-c"
}
```

对于 Microsoft 原生结果，系统从返回的 `entities` 和 `relationships` context 生成同样的 trace；原生 Global/Basic 如果没有完整关系或文本，缺失字段为空，不补造路径。

## 7. RetrievalTrace 完整字段

每个 query 的 `RetrievalTrace` 都有以下字段：

| 字段 | 含义 | 交互查询时是否一定有值 |
|---|---|---|
| `query` / `method` | 原问题和方法标识 | 是 |
| `matched_entity_ids` / `matched_entities` | 命中的实体 ID 和完整实体记录 | 视召回而定 |
| `matched_relationship_ids` / `matched_relationships` | 命中的关系 ID 和完整关系记录 | 视召回而定 |
| `graph_paths` | 每条路径的实体序列、关系序列、hop、分数和目标文本 | 自定义方法通常有 |
| `subgraph_nodes` | 子图节点 ID、标题、类型、seed 标记 | 有图结果时有 |
| `subgraph_edges` | 子图边 ID、source、target、description、weight | 有图结果时有 |
| `text_evidence` | 文本证据完整行，包括 source path 和 retrieval score | 视召回而定 |
| `retrieved_source_paths` | 去重后的来源路径 | 视数据 schema 而定 |
| `channel_scores` | BM25、dense、PPR、path proximity、权重等中间结果 | 自定义方法有 |
| `path_recall` | 与 gold graph paths 的 exact path recall | 无 gold 时为 `null` |
| `path_recall_numerator/denominator` | 路径召回分子/分母 | 无 gold 时为 0/0 |
| `evidence_recall` | 来源证据路径 recall | 无 gold 时为 `null` |
| `evidence_recall_numerator/denominator` | 证据召回分子/分母 | 无 gold 时为 0/0 |
| `created_at` | UTC 创建时间 | 是 |

落盘时，Parquet 中的嵌套 list/dict 使用 JSON 字符串保存，但字段名不变且不丢内容；读取后可用 `json.loads` 恢复。

## 8. 路径召回率和评测用法

交互式查询没有标准答案，所以系统不会把“命中了几条路径”误写成 path recall。`path_recall` 只有在评测适配层传入 gold path 时计算：

```python
from rag.retrieval import annotate_trace_metrics

annotate_trace_metrics(
    trace,
    gold_paths=[
        {"entity_ids": ["e-a", "e-b"], "relationship_ids": ["r-ab"]}
    ],
    gold_source_paths=["mail/a", "mail/b"],
)
```

当前实现的 path recall 是 exact entity-sequence + relationship-sequence recall；source evidence recall 是 gold source path 集合的覆盖率。两者不能代替答案正确率：

- path recall 高、答案低：检索到路径，但生成或证据整合有问题；
- path recall 低、答案高：可能是生成模型依赖先验或 gold path 标注不完整；
- evidence recall 高、path recall 低：文本被找回了，但图结构没有形成完整链路。

正式评测仍需把 `RetrievalTrace` 与 `experiments/enron_california_crisis/questions*.jsonl` 的人工 evidence/path 标注接起来，并同时保留 Microsoft GraphRAG 原始结果。

## 9. 前端可视化

主页面左侧使用多选框，一次可选任意方法组合；右侧按方法动态生成等宽列。每一列包括：

1. 最终回答；
2. 原始 GraphRAG context citations；
3. “Graph 路径与证据链”表格：source path、text unit、entity IDs、relationship IDs、文本和 retrieval score；
4. JSON 展开区：完整命中实体、关系、路径和 recall 字段；
5. Graphviz 子图：节点是实体，边是关系；路径经过的节点和边用红色/粗线高亮，seed 节点用浅红，普通节点用浅蓝。

图的显示不是答案依据，而是审计界面。真正的答案依据仍然是 trace 里的 `text_evidence` 和 `retrieved_source_paths`。

## 10. 运行方式

在已有 GraphRAG 数据根目录和配置下：

```bash
cd unified-search-app
uv sync
uv run poe start
```

数据根目录需要有：

```text
DATA_ROOT/
  listing.json
  california-crisis/
    settings.yaml
    output/entities.parquet
    output/relationships.parquet
    output/text_units.parquet
    output/communities.parquet
    output/community_reports.parquet
    output/lancedb/...
```

`listing.json` 的 `path` 对应数据集目录。第一次选择自定义方法时才会尝试加载 text/entity vector store 和 embedding model；不启用自定义方法时，Microsoft 原生查询路径不变。

## 11. 测试和已知限制

新增 `unified-search-app/tests/test_retrieval.py` 覆盖：

- LightRAG 风格的低层/高层候选和文本回链；
- HippoRAG 2 风格的 PPR 图路径；
- Hybrid Path 的 dense candidate + constrained path 融合；
- exact path recall 和 source evidence recall。

已完成的静态验证是对新增 Python 文件执行 `python3 -m py_compile`。完整 Streamlit/GraphRAG 运行需要安装 `unified-search-app/pyproject.toml` 的依赖并提供真实 settings、向量索引和 LLM 配置；本轮没有把未在真实 API 环境跑过的查询写成“端到端通过”。

当前限制：

1. 自定义方法没有重新实现 LightRAG/HippoRAG 2 的索引阶段，因此它们共享 Microsoft GraphRAG 的实体和关系质量。
2. BM25 是依赖无关的轻量实现，不等同于 Lucene/BM25 服务端，超大语料应换成持久化倒排索引。
3. PPR 当前按实体图运行，未把 passage 节点显式纳入二部图；通过 text unit 的 entity links完成 passage integration。
4. `path_recall` 需要 gold 标注；仅凭查询日志不能自动计算真实召回率。
5. Blob trace 写回采用读—拼接—覆盖，在高并发生产环境应换成事务/批量存储；课程演示的单用户场景可以接受。
6. 当前权重、top-k、最大 hop 是可解释的默认参数，必须在固定验证集上做消融，不能宣称已调到全局最优。

## 12. 参考资料

以下链接是本次调研实际使用的论文或官方仓库：

1. [Microsoft Research: From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/)
2. [Microsoft GraphRAG 官方仓库](https://github.com/microsoft/graphrag)
3. [LightRAG 论文（arXiv:2410.05779）](https://arxiv.org/abs/2410.05779)
4. [LightRAG 官方仓库](https://github.com/HKUDS/LightRAG)
5. [HippoRAG 2 论文（ICML 2025 / arXiv:2502.14802）](https://proceedings.mlr.press/v267/gutierrez25a.html)
6. [HippoRAG 官方仓库](https://github.com/OSU-NLP-Group/HippoRAG)
7. [FG-RAG 论文（arXiv:2504.07103）](https://arxiv.org/abs/2504.07103)
8. [E²GraphRAG 论文（arXiv:2505.24226）](https://arxiv.org/abs/2505.24226)
9. [QCG-RAG 论文（arXiv:2509.21237）](https://arxiv.org/abs/2509.21237)
