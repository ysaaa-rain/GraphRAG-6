# graphrag6-retrieval

本项目自己的检索算法库。和微软的 GraphRAG 引擎（仓库根的 `packages/`）分开管理：
引擎提供基础索引和查询能力，本目录实现面向 GraphRAG Parquet 索引的独立检索策略。

## 内容

| 文件 | 作用 |
|---|---|
| `graphrag6_retrieval/retrieval.py` | BM25、实体图邻接、Personalized PageRank、有限跳数图路径、path/evidence recall |
| `graphrag6_retrieval/custom_search.py` | GraphRAG 向量索引与 LLM 适配 |
| `graphrag6_retrieval/typing.py` | 检索方法、结果及 trace 数据契约 |
| `graphrag6_retrieval/trace_store.py` | Parquet 形式的查询证据记录 |

界面上可切换的三种方法就来自这里：**LightRAG 风格（低层实体/关系 + 高层社区）**、
**HippoRAG 2 风格（实体种子 + 加权 PPR 多跳）**、**PathFusionRAG（BM25 + Dense + 有限跳数图路径加权融合）**。

## 代码来源与实现边界

- `retrieval.py`、`custom_search.py`、`trace_store.py`：本项目在 commit `0b8665c`
  （2026-09-11）新增，最初放在已删除的上游演示前端中，2026-09-13 抽成独立包
  （同时把 `trace_store` 从依赖旧前端的 `Datasource` 抽象改成自包含）。
- `typing.py`：源自上游 Microsoft 的同名文件（commit `0e1a6e3`，2025-04-07），
  由本项目扩展出 `SearchMethod` 和 `RetrievalTrace`。

## 用法

```python
from graphrag6_retrieval import GraphRetriever, SearchMethod, save_trace

retriever = GraphRetriever(entities=..., relationships=..., text_units=...)
bundle = retriever.retrieve("问题", SearchMethod.HYBRID_PATH)   # 无向量资源时使用 BM25 与图路径分数
save_trace(index_dir, bundle.trace)
```

只要向量通道时才需要 embedding 服务和 `custom_search` 里的那几个工厂函数。

## 测试

```powershell
cd graphrag6-retrieval
uv run --group dev pytest -q tests
```

测试使用固定的实体、关系和文本数据，不需要远程 LLM 或 embedding 服务。
