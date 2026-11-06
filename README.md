# GraphRAG-6 知识工程综合实践

本项目围绕**基于知识图谱的检索增强生成（GraphRAG）**构建知识问答与实验分析系统。系统将结构化实体关系、向量检索和原文证据结合，用于跨文档信息检索、关系追踪和问答生成，并提供统一的检索工作台。

## 系统组成

- [GraphRAG 工作台](graphrag-workbench/)：基于 Streamlit 的索引管理、七种检索方法切换、答案对照、实体关系图与证据链展示。
- [检索算法包](graphrag6-retrieval/)：LightRAG 风格双层检索、HippoRAG 2 风格的图传播检索，以及 PathFusionRAG 混合路径检索。
- [实验脚本](scripts/)与[实验配置](experiments/)：Enron 邮件预处理、GraphRAG-Bench 查询与评测、Enron 检索对照。
- [Microsoft GraphRAG 引擎](packages/)：项目采用的开源索引与查询基础，保留其原有许可证和版权声明。自定义检索策略与工作台分别位于独立目录。

PathFusionRAG 对 BM25 词项匹配、Dense 检索与有限跳数图路径进行加权融合，并输出候选证据对应的实体、关系、路径及分数。其图路径分数用于排序增强；具体实现和参数见[算法说明](docs/GraphRAG方法调研与系统实现细节.md)。

## 目录结构

| 路径 | 内容 |
|---|---|
| `graphrag-workbench/` | 工作台、索引模板与界面测试 |
| `graphrag6-retrieval/` | 自定义检索算法、证据记录与算法测试 |
| `packages/` | Microsoft GraphRAG 引擎及运行组件 |
| `scripts/` | 数据处理、模型服务和评测脚本 |
| [`experiments/`](experiments/README.md) | 实验配置、问题、原文证据与判读记录 |
| `docs/` | 方法、运行说明、数据来源与结果汇总 |
| `presentations/` | 系统方法汇报演示文稿 |
| [`tests/`](tests/README.md) | 本地索引与检索相关的引擎关键测试、固定样例 |

## 数据与实验

项目使用 Enron Email、GraphRAG-Bench 等数据开展索引、问答与检索评测，同时对 Natural Questions、HotpotQA、2WikiMultiHopQA、MuSiQue、Qasper 和 QMSum 进行了多方法对照实验。六个公开数据集的运行结果在工作台的“方法对照”页面展示，具体数值和场景分析见[方法与实验说明](docs/GraphRAG方法调研与系统实现细节.md)。

Enron Email 完成了 **517,401 封邮件**的统一预处理与文件夹审计。California Power Crisis 案例采用两个原始文件夹共 **66 封邮件**建库，生成 66 个 documents、71 个 text units、644 个 entities、1,374 个 relationships、37 个 communities 和 35 个 community reports。Enron 的 Graph/Vector 检索对照已经运行，包括 CA01、CA02、CA03 和 CC 题组；不同问题中两种检索方式各有优势，逐题比较见项目实验说明。

GraphRAG-Bench Medical 完成 **2,062 道问题**的 GraphRAG 查询、generation 与 retrieval 指标评测；Answer Correctness 为 0.363293，Evidence Recall 为 0.568109。评测指标和异常值口径见[全量评测说明](docs/GraphRAG-Bench全量评测说明.md)。

实验使用的索引、向量库及批量问答输出由实验环境保存，Git 仓库主要维护代码、配置、评价方式和结果汇总。运行时通过 `GRAPHRAG_INDEX` 指向相应索引目录。

## 运行

工作台的安装、配置、索引构建和启动命令见[工作台快速开始](graphrag-workbench/README.md)。检索算法的独立测试入口见[算法包说明](graphrag6-retrieval/README.md)。

## 文档

- [系统方法与实现](docs/GraphRAG方法调研与系统实现细节.md)
- [实验与当前进展](docs/实验结果与Enron案例.md)
- [GraphRAG-Bench 评测](docs/GraphRAG-Bench全量评测说明.md)
- [Enron 应用与数据](docs/实际应用领域方案.md)
- [评测设计](docs/评测方案.md)
- [配置与运行](docs/配置与运行.md)
- [数据资产](docs/数据资产清单.md)
- [基线来源](docs/基线说明.md)
- [开发与协作](docs/协作与质量规范.md)

## 开源来源

核心索引引擎采用 [Microsoft GraphRAG](https://github.com/microsoft/graphrag)，并保留上游许可证及相关版权声明。LightRAG 与 HippoRAG 2 的实现参考对应公开论文及方法思想，属于基于 GraphRAG 数据结构的独立适配；PathFusionRAG 为本项目设计的融合策略。各部分算法来源与实现差异见[方法说明](docs/GraphRAG方法调研与系统实现细节.md)。
