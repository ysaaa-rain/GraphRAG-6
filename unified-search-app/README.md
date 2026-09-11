# Unified Search 展示界面

Unified Search 是本项目的可选 Web 展示入口，用于在同一数据集上查看不同检索方式的答案、检索上下文和引用。当前界面支持 Microsoft GraphRAG 的 Global、Local、DRIFT、Basic/Vector，以及 LightRAG 风格、HippoRAG 2 风格和本项目 Hybrid Path 三种可切换方法。

## 依赖和运行

- Python 3.11–3.13
- `graphrag==3.1.2`
- `azure-search-documents~=12.0`

依赖版本和锁文件位于当前目录的 `pyproject.toml` 与 `uv.lock`，与根目录的 GraphRAG 3.1.2 系统保持一致。

```bash
uv sync
uv run poe start
```

## 数据目录

在数据根目录创建 `listing.json`，每个条目描述一个可查询索引：

```json
[
  {
    "key": "california-crisis",
    "path": "california-crisis",
    "name": "California Power Crisis",
    "description": "Enron California Power Crisis 66-email index",
    "community_level": 2
  }
]
```

每个数据目录至少包含 `settings.yaml` 和 `output/`；需要本地数据时，通过 `DATA_ROOT` 指定数据根目录。Azure Blob 数据源仍可按 `BLOB_ACCOUNT_NAME` 和 `BLOB_CONTAINER_NAME` 配置，但不属于本轮 Enron 首轮对照的必需路径。

## 界面用途

左侧选择数据集、问题生成数量和检索方法；右侧展示答案、引用和社区报告。课堂演示时优先使用本项目已经验收的 Enron 66 封索引。每个结果下方会显示实体—关系—文本证据链、子图和红色路径高亮，每次查询还会把完整 `RetrievalTrace` 追加到 `output/retrieval_traces.parquet`。

## 方法选择

| UI 方法 | 核心机制 |
|---|---|
| Microsoft Local / Global / DRIFT | 直接调用当前 `graphrag==3.1.2` API |
| LightRAG 风格 | 低层实体/关系匹配 + 高层社区报告匹配，并通过实体反向链接文本 |
| HippoRAG 2 风格 | 实体种子 + 加权 Personalized PageRank，再整合邻域 passage |
| Hybrid Path | BM25、已有 GraphRAG dense vector index 和受最大 hop 约束的图路径三路融合 |

自定义方法是针对本仓库已有 GraphRAG 输出 schema 的实现适配，不是将第三方项目直接作为依赖安装；详细原理、字段和运行边界见根目录 [GraphRAG 方法调研与系统实现细节](../docs/GraphRAG方法调研与系统实现细节.md)。
