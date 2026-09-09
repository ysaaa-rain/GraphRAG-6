# DeepSeek API 使用消耗分析

## 1. 统计目的与口径

本文记录截至 2026-09-09 项目本地运行产物中可以追溯的 DeepSeek 使用情况，帮助控制实验成本、安排 API 额度，并避免把本地 Qwen embedding 的运行量误记为 DeepSeek 消耗。

本文的 token 分为两种口径：

1. 已记录 token：实验输出或 GraphRAG metrics 日志中直接保存的 prompt、completion、total token。
2. 评测调用推算：官方评测脚本调用 DeepSeek 作为指标评审器，但没有保存接口返回的 token usage；这里只统计题数、正常路径调用次数和重试上限，不把推算值冒充实际 token。

DeepSeek 控制台账单才是费用和实际计费 token 的最终依据。GraphRAG 的本地 token 统计可能包含缓存响应，查询脚本的 token 由项目 tokenizer 计算，并不等同于服务商账单中的缓存命中、缓存未命中和计费 token 拆分。因此，本文不直接给出金额，也不把本地 total token 直接称为已扣费金额。

## 2. 当前可直接核对的汇总

| 阶段 | 数据/任务 | DeepSeek 请求 | prompt token | completion/output token | 本地记录总 token | 统计状态 |
|---|---|---:|---:|---:|---:|---|
| Medical 建库 | GraphRAG indexing | 3,790 | 3,951,525 | 2,244,808 | 6,196,333 | metrics 日志直接记录 |
| Medical 查询 | 2,062 道 Local Search | 2,062 | 19,681,955 | 1,127,033 | 20,808,988 | 逐题输出直接记录 |
| Enron 建库 | 66 封展示语料的 GraphRAG indexing | 453 | 623,099 | 249,975 | 873,074 | metrics 日志直接记录 |
| 已记录合计 | Medical + Enron | 6,305 | 24,256,579 | 3,621,816 | 27,878,395 | 不含评测 judge token |

### 2.1 只看当前正式 benchmark Medical

Medical 建库和查询目前合计记录：

    6,196,333 + 20,808,988 = 27,005,321 tokens

这还没有包含官方 generation/retrieval 评测阶段作为“裁判”的 DeepSeek 请求，因此项目实际使用量应高于这个已记录数；评测阶段的精确 token 需要以后补充 usage 采集后才能确认。

## 3. 各阶段消耗说明

### 3.1 Medical 建库：当前最大的结构化处理阶段

建库阶段 DeepSeek 主要用于实体抽取、关系抽取、实体和关系描述汇总、社区报告生成。

最终 metrics 日志记录：

    attempted_request_count: 3790
    successful_response_count: 3790
    failed_response_count: 0
    prompt_tokens: 3951525
    completion_tokens: 2244808
    total_tokens: 6196333

按缓存目录拆分的本地 token 记录如下：

| 建库子阶段 | 请求记录 | prompt token | completion token | total token |
|---|---:|---:|---:|---:|
| 实体/关系抽取 extract_graph | 398 | 1,853,643 | 1,206,093 | 3,059,736 |
| 描述汇总 summarize_descriptions | 3,120 | 667,544 | 739,364 | 1,406,908 |
| 社区报告 community_reporting | 271 | 1,430,323 | 299,348 | 1,729,671 |
| 合计 | 3,789 | 3,951,510 | 2,244,805 | 6,196,315 |

拆分合计与最终日志相差 1 条请求、18 token，原因是缓存文件和运行日志的记录边界不同；正式汇总采用最终 metrics 日志的 3,790 请求和 6,196,333 token。

日志还显示最终一次重跑时有 3,789 条缓存响应。这说明后续重复执行建库时大部分结果直接从本地缓存读取，不应按完整 619.6 万 token 重复估计新增 API 消耗；但首次生成这些缓存内容时已经发生了相应的模型处理，实际历史账单仍需以 DeepSeek 控制台为准。

### 3.2 Medical 查询：每道题一次答案生成

2,062 道官方题目均完成 Local Search，项目输出逐题保存：

    llm_calls: 2062
    prompt_tokens: 19681955
    output_tokens: 1127033

查询总量为 20,808,988 token，平均每题约 10,093 token。按题型拆分：

| 题型 | 题数 | prompt token | output token | total token |
|---|---:|---:|---:|---:|
| Fact Retrieval | 1,098 | 10,342,399 | 419,724 | 10,762,123 |
| Complex Reasoning | 509 | 4,910,461 | 299,567 | 5,210,028 |
| Contextual Summarize | 289 | 2,778,402 | 197,283 | 2,975,685 |
| Creative Generation | 166 | 1,650,693 | 210,459 | 1,861,152 |
| 合计 | 2,062 | 19,681,955 | 1,127,033 | 20,808,988 |

这里的 prompt_tokens 和 output_tokens 是当前 GraphRAG 查询结果对象中的项目统计值；它能用于不同方法之间的相对比较，但不替代 DeepSeek 服务端 usage 账单。

### 3.3 Medical generation 评测：DeepSeek 作为自动评审器

该阶段不是再次生成 GraphRAG 答案，而是让 DeepSeek 判断已有答案的质量。官方指标代码中：

- Answer Correctness：正常路径每题 3 次 DeepSeek 调用；
- Coverage：正常路径每题 2 次调用；
- Faithfulness：正常路径每题 2 次调用；
- ROUGE-L：本地计算，不调用 DeepSeek。

按当前 2,062 道题和题型配置，正常首次返回有效 JSON 时预计为：

| 题型 | 题数 | 正常路径 DeepSeek 调用 |
|---|---:|---:|
| Fact Retrieval | 1,098 | 3,294 |
| Complex Reasoning | 509 | 1,527 |
| Contextual Summarize | 289 | 1,445 |
| Creative Generation | 166 | 1,162 |
| 合计 | 2,062 | 7,428 |

部分评审函数带 JSON 解析重试。按当前代码的重试上限，理论最多约 9,912 次；实际 token 数和实际重试次数没有写入本次评测结果文件，因此当前只能记录为“已完成 2,062 道、调用量按代码推算”，不能声称精确 API token 消耗。

该阶段的本地 Qwen embedding 调用只用于 Answer Correctness 的语义相似度，不消耗 DeepSeek API；模型仍是统一的 Qwen3-Embedding-0.6B。

### 3.4 Medical retrieval 评测：DeepSeek 作为检索质量评审器

该阶段评估已保存的检索上下文，不重新建图。每道题正常路径包括：

- Context Relevancy：2 次 DeepSeek 评分；
- Evidence Recall：1 次 DeepSeek 证据归因判断。

因此正常路径预计：

    2062 × 3 = 6186 次 DeepSeek 调用

考虑当前函数的重试上限，理论最多约 12,372 次。本阶段的评测 JSON 没有保存 prompt/completion token 或重试次数，所以精确 token 消耗暂不可由现有产物恢复。

### 3.5 Enron 66 封展示语料建库

Enron 本轮只使用 66 封邮件作为可控展示分母，不代表 517,401 封完整归档已经全量建库。其最终 indexing metrics 记录：

    attempted_request_count: 453
    successful_response_count: 453
    failed_response_count: 0
    prompt_tokens: 623099
    completion_tokens: 249975
    total_tokens: 873074

该阶段属于正式实际应用展示准备，不属于 GraphRAG-Bench Medical/Novel 的官方 benchmark 消耗。最终一次运行显示 452 条缓存响应，重复运行时应优先复用缓存。

### 3.6 Novel：只发生了失败的额度检查请求

Novel 尚未正式建库。日志记录：

    attempted_request_count: 1
    successful_response_count: 0
    failed_response_count: 1
    error: Insufficient Balance

本地日志没有记录成功响应 token。由于请求在服务端额度校验阶段失败，不能从项目文件判断服务商是否产生了任何计费；这 1 次失败请求不纳入已记录 token 合计，是否产生费用只能在 DeepSeek 控制台确认。

## 4. 当前结论

1. 已记录的最大消耗阶段是 Medical 查询：约 2,080.9 万 token，主要来自 2,062 次最终答案生成。
2. Medical 建库是第二大消耗阶段：约 619.6 万 token，主要集中在实体/关系抽取、描述汇总和社区报告。
3. 官方自动评测还会产生额外 DeepSeek 消耗：generation 正常路径约 7,428 次 judge 调用，retrieval 正常路径约 6,186 次 judge 调用；本次没有 token usage 记录，因此未纳入 2,787.8 万已记录 token。
4. Enron 66 封试验约 87.3 万 token；它与 Medical/Novel benchmark 分开统计。
5. Novel 当前只失败 1 次，没有有效生成结果；后续额度恢复前不再自动重试。
6. Qwen embedding 在本机运行，不计入 DeepSeek API；官方评测阶段的 Qwen 语义相似度也不计入 DeepSeek API。

## 5. 后续成本记录要求

下一轮正式实验前，评测脚本需要为每次 DeepSeek 调用记录以下字段，并按实验阶段汇总：

    stage
    dataset
    question_id
    model
    cache_hit
    prompt_tokens
    completion_tokens
    total_tokens
    latency_seconds
    retry_count

费用计算必须使用 DeepSeek 控制台或当期官方价格，并单独区分输入、缓存命中输入、缓存未命中输入和输出 token。未采集到服务端 usage 时，报告中只能写“本地统计 token”或“调用次数推算”，不能写成精确费用。

## 6. 可复核文件

- Medical 建库日志：experiments/outputs/benchmark_medical/logs/indexing-engine.log
- Medical 查询明细：experiments/outputs/benchmark_medical/graphrag_local_answers.json
- Medical generation 评测：experiments/outputs/benchmark_medical/graphrag_local_generation_eval.json
- Medical retrieval 评测：experiments/outputs/benchmark_medical/graphrag_local_retrieval_eval.json
- Enron 建库日志：experiments/outputs/enron_california_crisis/logs/indexing-engine.log
- Novel 失败日志：experiments/outputs/benchmark_novel/logs/indexing-engine.log
