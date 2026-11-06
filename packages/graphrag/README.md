# GraphRAG 核心系统

本包提供项目的索引、图谱构建、社区摘要和查询入口。当前项目通过它完成 Enron 邮件的实体—关系—社区建库，并提供 Local、Global、DRIFT 与 Basic 查询路径。

## 项目内使用

```bash
./.venv/bin/python -m graphrag index \
  --root experiments/enron_california_crisis \
  --method standard \
  --verbose
```

索引输出包括 documents、text units、entities、relationships、communities、community reports 以及文本/实体/社区向量。查询时，GraphRAG 使用图结构和文本证据组织上下文；Basic Search 使用文本单元向量作为 Vector RAG 对照。

## 当前实验边界

Enron 本轮索引只使用 `data/processed/enron/california_crisis_66/documents.jsonl` 的 66 封邮件。完整的 517,401 封邮件已做规范化预处理，但没有全部送入本轮图谱索引。模型、embedding、切分规则和评测协议以项目 `docs/` 与 `experiments/` 中的配置为准。

## 开源来源

本组件源自 [Microsoft GraphRAG](https://github.com/microsoft/graphrag)，沿用仓库根目录的 MIT 许可证，源码版权声明保留。
