# 实验配置与证据

| 目录 | 内容与范围 |
|---|---|
| `benchmark_medical/` | GraphRAG-Bench Medical 建库配置 |
| `benchmark_novel/` | GraphRAG-Bench Novel 建库配置，不代表全量评测完成 |
| `enron_california_crisis/` | 66 封邮件的受控案例、问题与参考答案 |
| `enron_rumor_variants/` | 政策传闻、转发链与干扰邮件的小规模输入和提示词 |
| `enron_airline_questions/` | 航空合作与 ICE 注册问答题集、原文摘录和生成脚本 |
| `enron_q001/` | 早期三题对照的原始人工判读记录及证据范围说明 |
| `graphrag_prompts/` | 共享索引与查询提示词 |

不同题集的数据范围各自独立，不合并统计结果。索引、向量库与批量输出由运行环境保存，`outputs/` 按 Git 忽略规则管理。模型、数据来源、评测口径和限制见[实验结果](../docs/实验结果与Enron案例.md)与[数据资产](../docs/数据资产清单.md)。
