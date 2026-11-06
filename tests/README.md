# 引擎关键测试

本目录保留 Microsoft GraphRAG 中与当前本地索引和查询链路有关的测试，源码版权声明沿用原样。

| 目录 | 范围 |
|---|---|
| `unit/` | 配置、文本切分、图结构、索引组织、查询上下文和存储表 |
| `integration/` | 本地文件、LanceDB、缓存及模型接口集成 |
| `verbs/` | 索引流程步骤、实体关系、社区报告与向量更新 |
| `fixtures/text/`、`verbs/data/` | 保留测试依赖的固定输入与表数据 |

从仓库根目录运行：

```bash
uv sync --all-packages
uv run poe test_unit
uv run poe test_integration
uv run poe test_verbs
```

部分模型集成用例或切分用例需要额外资源；执行前检查模型凭据、NLTK 数据和用例标记。测试文件的保留不表示已在当前环境运行通过，也不构成完整端到端问答验证。

自定义算法测试见 [graphrag6-retrieval](../graphrag6-retrieval/README.md)，工作台测试见 [graphrag-workbench](../graphrag-workbench/README.md)。
