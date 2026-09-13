# graphrag6-retrieval

本项目自己的检索算法库。和微软的 GraphRAG 引擎（仓库根的 `packages/`）分开管理：
引擎是别人写的，这里是我们要讲的部分。

## 内容

| 文件 | 行数 | 作用 |
|---|---:|---|
| `graphrag6_retrieval/retrieval.py` | 985 | BM25、实体图邻接、Personalized PageRank、受跳数约束的路径搜索、path/evidence recall 指标 |
| `graphrag6_retrieval/custom_search.py` | 142 | 三种自定义检索的组装，复用 GraphRAG 的向量库、embedding 和 completion |
| `graphrag6_retrieval/typing.py` | 111 | `SearchMethod` / `SearchType` / `SearchResult` / `RetrievalTrace` |
| `graphrag6_retrieval/trace_store.py` | 51 | trace 追加写入 `<index>/output/retrieval_traces.parquet` |

界面上可切换的三种方法就来自这里：**LightRAG 风格（低层实体/关系 + 高层社区）**、
**HippoRAG 2 风格（实体种子 + 加权 PPR 多跳）**、**Hybrid Path（BM25 + 向量 + 图路径融合）**。

## 代码来源（写报告时按这个说）

- `retrieval.py`、`custom_search.py`、`trace_store.py`：本项目在 commit `0b8665c`
  （2026-09-11）新增，最初放在上游演示前端目录 `unified-search-app/app/rag/` 下，
  2026-09-13 抽成独立包（同时把 `trace_store` 从依赖旧前端的 `Datasource` 抽象改成自包含）。
- `typing.py`：源自上游 Microsoft 的同名文件（commit `0e1a6e3`，2025-04-07），
  由本项目扩展出 `SearchMethod` 和 `RetrievalTrace`。

## 用法

```python
from graphrag6_retrieval import GraphRetriever, SearchMethod, save_trace

retriever = GraphRetriever(entities=..., relationships=..., text_units=...)
bundle = retriever.retrieve("问题", SearchMethod.HYBRID_PATH)   # 纯图检索，不需要 embedding
save_trace(index_dir, bundle.trace)
```

只要向量通道时才需要 embedding 服务和 `custom_search` 里的那几个工厂函数。

## 测试

```powershell
cd D:\AI\GraphRAG-6\graphrag6-retrieval
python -m unittest discover -s tests -t . -v
```

测试不需要 graphrag 以外的服务，也不需要 embedding 服务。
