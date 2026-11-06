# Enron 航空合作与注册流程问答题集

本目录保存两道基于 Enron 邮件原文设计的问题，以及对应的中英文版本和生成脚本。使用的数据范围为 Enron 完整归档中的相关邮件，独立于 California Power Crisis 的 66 封邮件建库实验。

- **E1（multi_hop）**：涉及 British Airways、Continental 和 Enron 多部门合作的跨邮件关系问题。参考答案需要结合多个时间阶段、人物和邮件证据。
- **K1（graph_limited）**：关于 ICE 注册程序的单事实问题。答案依据集中在单封邮件，适合比较图检索与向量检索在直接事实问答中的表现。

`questions_en.jsonl` 保存英文题目、参考答案、原文证据和路径标注；`questions_zh.jsonl` 保存对应中文问题；`build.js` 为题集生成脚本。评测前应统一参与比较的语料范围、检索参数和答案协议。

问题内容、证据邮件与判定要素见[Enron 航空合作问答题集](../README.md)。
