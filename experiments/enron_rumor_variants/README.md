# Enron 政策传闻与干扰邮件实验

本目录包含独立的小规模索引配置、输入邮件和提示词，用于分析政策传闻、转发链条与干扰文档的检索表现。输入范围以 `input/` 为准，与 California Power Crisis 66 封索引和航空合作题集分别管理。

配置见 `settings.yaml`，提示词位于 `prompts/`，输入邮件位于 `input/`。从仓库根目录运行 `python -m graphrag index --root experiments/enron_rumor_variants`；模型和密钥配置方式见[配置与运行](../../docs/配置与运行.md)。本目录未附可据以计算效果指标的完整运行输出，不能仅凭输入与配置宣称检索效果。
