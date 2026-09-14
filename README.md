# GraphRAG-6 知识工程综合实践

本项目是知识工程综合实践小组的 GraphRAG 系统工程。项目目标是建立一套可复现、可解释、可比较的 GraphRAG 实验系统。

项目主题：**基于知识图谱的 RAG 系统构建**。

## 项目目标

在公开数据集和开放文本上，完成知识图谱构建、检索、知识注入与问答生成，并在相同模型、数据、提示词和输出格式下，对比 Vector RAG、GraphRAG 和 Hybrid RAG 的效果、成本与延迟。

项目结论以实验数据为依据：如果图检索没有在某类问题上优于向量检索，也要记录原因和适用边界，不预设“GraphRAG 必然更好”。

## 前端与建库（新同学从这里开始）

检索界面和"从零建库到跑通"的完整步骤见 [graphrag-workbench/README.md](graphrag-workbench/README.md)。

- [graphrag-workbench](graphrag-workbench/)：GraphRAG 工作台前端。建索引进度、七种检索方法对照、每个阶段的产物、证据链与子图
- [graphrag-workbench/index-template](graphrag-workbench/index-template/)：新建索引的模板，复制即用（配置 + 13 个提示词，不需要手写 settings.yaml）
- [graphrag6-retrieval](graphrag6-retrieval/)：本项目自己的检索算法（LightRAG 风格、HippoRAG 2 风格、PathFusionRAG）

两点要知道：

1. **索引不在仓库里**。`experiments/outputs/` 被 `.gitignore` 忽略，因为索引是数据产物。要么照上面的快速开始自己建一份，要么把现有索引目录放在本地，用 `GRAPHRAG_INDEX` 环境变量指过去。
2. **引擎和算法是两回事**。微软的 GraphRAG 引擎源码在 `packages/`（约 3 万行，本项目只在社区报告解析处改过 1 个文件做 DeepSeek 适配）；本项目自己的算法在 `graphrag6-retrieval/`（约 1,300 行）。

## 当前阶段

- 已完成课程要求解析并归档原始课件。
- 已保留项目初始化记录，并固定当前系统的代码与配置版本。
- 已将正式评测范围收敛为 GraphRAG-Bench Novel、GraphRAG-Bench Medical 和 Enron Email 一个实际应用场景。
- Enron Email 使用大规模开放邮件语料；当前冻结 3–5 道跨邮件代表性问题做可解释展示；《红楼梦》不再作为最终应用主线。
- 已完成 517,401 封 Enron 邮件的统一预处理和文件夹级审计；正式建库不使用 517,401 封全量，而使用已确定的 66 封 California Power Crisis 受控分母（两个原始文件夹：20+46 封）。
- Enron 66 封索引已经完成并验收：生成 66 个 documents、71 个 text units、644 个 entities、1,374 个 relationships、37 个 communities 和 35 个 community reports；另有 1 个社区报告因控制字符未生成，已登记为限制。
- Enron Graph/Vector 首轮对照已经完成，输出为 `comparison_CA01.json`、`comparison_CA02.json`、`comparison_CA03.json` 和 `comparison_CC_66.json`；CA01/CA03 为有限 Graph 召回优势，CA02 为 Vector 略优，不能外推为普遍结论。
- Medical GraphRAG 建库、2,062 道查询、官方 generation 和 retrieval 评测均已完成；retrieval 个别题目的单项指标为 null，详见评测说明。Novel 已暂停，等待 DeepSeek 额度恢复。
- 已记录 DeepSeek V4 Flash 的 JSON-object 兼容适配、Qwen 模型 revision、向量维度和本机 MPS/CPU 稳定性配置；完整当前状态和组员展示交接见[项目当前状态与 Enron 展示交接](docs/项目当前状态与Enron展示交接.md)。
- GraphRAG-6 工作台已支持七种可选检索方法，并统一保存实体、关系、图路径、子图、文本证据和 recall 字段；自定义方法与前端证据链说明见[GraphRAG 方法调研与系统实现细节](docs/GraphRAG方法调研与系统实现细节.md)。

## 文档入口

- [课程要求与逐项检查表](docs/课程要求.md)
- [项目章程与开发路线](docs/项目章程与路线.md)
- [基线说明](docs/基线说明.md)
- [配置与运行约定](docs/配置与运行.md)
- [评测方案](docs/评测方案.md)
- [阶段计划与执行清单](docs/阶段计划与执行清单.md)
- [开放数据资产清单](docs/数据资产清单.md)
- [Enron 实际应用方案](docs/实际应用领域方案.md)
- [项目当前状态与 Enron 展示交接](docs/项目当前状态与Enron展示交接.md)
- [GraphRAG 方法调研与系统实现细节](docs/GraphRAG方法调研与系统实现细节.md)
- [协作与质量规范](docs/协作与质量规范.md)
- [阶段变更记录](docs/变更记录.md)
- [老师原始课件](docs/参考资料/课程要求.pptx)
- [总评评分标准截图](docs/参考资料/评分标准-总评.jpg)
- [阶段 1 评分标准截图](docs/参考资料/阶段1评分标准.jpg)

## 代码基线

当前系统代码、数据处理脚本、索引配置和评测入口均位于本仓库；组件边界、运行风险和后续修改范围见[基线说明](docs/基线说明.md)。

## 评测主线

1. 先用小规模固定样例和 GraphRAG-Bench Novel 的 100 条样本完成端到端冒烟测试。
2. 对两个 benchmark 和 Enron 实际应用场景，使用同一套条件运行 Vector、Graph 和 Hybrid 三种检索配置。
3. benchmark 使用官方问题、参考答案和评测协议；Enron 使用本组自建问题、人工参考答案、证据和路径标注。
4. 记录答案正确性、ROUGE-L、覆盖率、忠实度、证据召回、路径召回、上下文相关性、索引结构、延迟和成本。
5. 冒烟测试稳定后，再运行 Novel 和 Medical 的完整测试，并完成 Enron 实际应用实验。

阶段 1 还必须完成 3–5 个代表性问题、数据处理前后样例、最小问答闭环以及成员/进度说明；总评还必须展示 2–3 个普通 RAG 与 GraphRAG 的成功或失败案例。

## 协作原则

- 每个阶段以小而清晰的 commit 存档，commit message 写明目的。
- 代码变更必须有对应文档、测试或实验记录。
- 合并前先运行测试和静态检查；发现自动生成代码错误时先修正，再验收合并。
- 仓库不保存聊天记录、内部上下文、密钥、个人隐私或无用途的中间文件。

## 许可证说明

基线目录中的许可证和版权声明保留原样。新增代码、文档和实验产物的许可证与数据许可将在对应文件或数据记录中明确说明。
