# Enron S0 问题集

本目录保存 Enron S0 的第一版固定 pilot 问题集。它用于验证 Vector、GraphRAG 和 Hybrid 三种检索入口的结果记录格式，不代表最终 Enron 正式评测集。

## 当前版本

- 文件：`questions.jsonl`
- 题数：12 题，每个问题类别 2 题
- 类别：单事实、多实体关联、多跳推理、全局总结、图结构帮助有限、幻觉风险
- 证据：使用 `source_path` 指向 S0 规范化邮件；不在 Git 中提交原始邮件内容
- 状态：已完成首版人工标注，等待 Vector/Graph/Hybrid 逐题运行

## 字段约定

| 字段 | 含义 |
|---|---|
| `question_id` | 稳定的问题编号，后续结果文件按此关联 |
| `category` | 六类问题之一 |
| `question` | 实际发送给三种系统的问题 |
| `reference_answer` | 人工参考答案或拒答边界 |
| `evidence_source_paths` | 支持参考答案的原始邮件路径 |
| `gold_entities` | 期望识别的关键实体 |
| `gold_relations` | 期望识别的关键关系或事实连接 |
| `expected_graph_help` | 预先判断图结构是否应有帮助：`high`、`medium`、`low` |
| `answerability` | `answerable` 或 `insufficient_evidence` |

## 使用规则

1. 三种系统必须使用完全相同的问题文本和问题顺序。
2. 参考答案只用于离线评分，不发送给任何生成模型。
3. `expected_graph_help` 是实验前假设，不能替代实测结果；最终报告必须同时记录图结构有帮助和没有帮助的题目。
4. 任何新增或修改问题，都要更新 `questions.jsonl`、本说明和变更记录，并重新运行：

```bash
./.venv/bin/python scripts/validate_enron_questions.py
```

5. S0 pilot 稳定后，再扩展到 20–30 题，并为每个正式案例保留数据版本、问题集哈希和人工复核记录。
