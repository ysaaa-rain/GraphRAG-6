# 我的 Enron 个人问题集 v2（全量语料版，2 题）

> 依据组长反馈重构：**实验题问宽问笼统（考验图的多跳/全景能力），对照题问精确问窄（证明图并不强于 Vector）**。
> 语料基准：全量 Enron 官方包（517,401 封），不再受 s0 30 封样本限制。
> 交付文件：`questions_zh.jsonl`（合并用）/ `questions_en.jsonl`（跑检索推荐）/ `build.js`（可重新生成）。
> 旧版 5 题（s0 版）已删除，本 v2 为唯一正式交付。

## 一、设计哲学（问题形态 = 实验自变量）

| | 实验题 E1（证明图有价值） | 对照题 K1（诚实证明图无优势） |
|---|---|---|
| 题型 | `multi_hop` | `graph_limited` |
| 提问口径 | 笼统、开放式：问“整个事件有哪些参与方、各方利益/立场/顾虑、分歧如何协调、走向什么结果” | 精确、有锚点：锁定一个具体流程/系统 |
| 邮件跨度 | 大：答案需拼接 **11+ 封、跨 2 个大区、≥6 方主体、3 个时间阶段** | 小：**1 封** 邮件即答 |
| 预期结果 | Graph 明显优于 Vector（需沿“人–公司–事件–产品线”关系把散落片段组织成完整脉络） | Vector = Graph（top-k 命中单封即答，图无加成） |

## 二、E1｜multi_hop（宽口径全景）——预期图高价值

**问题（笼统版）**：2000 年下半年 Enron 同时推进与 British Airways 与 Continental 两家航空公司的合作，内部出现跨伦敦/休斯敦、跨部门的取舍与协调。请还原全过程：参与方？各方利益/立场/顾虑？两套价值主张谁提出、依据什么？分歧如何协调、走向如何？按“参与方→利益→协调→结果”组织并给出邮件依据。

**为什么这道题必须靠图才能答好**
- 答案要求把 **10/25 前史 → 11/21(BA 协议) → 12/4(Wasaff 回应/指派 Ramsey) → 12/7-12/11(会议筹备) → 12/12(会议) → 12/15(纪要行动项)** 六阶段串成一条因果链；
- 涉及至少 6 方：伦敦 Enron Europe（Dyson/Kemp/Bailey/Brown）、休斯敦 Global Strategic Sourcing（Wasaff/Hunter/Ramsey/Medcalf）、EGM/ENA 产品线（Shankman/Nowlan/Breslau/Tawney/Gagliardi/Engberg）、EES（电力）、Continental（Kellner/Howard/Hartford/Pressly/Rummel）、British Airways（对手方）；
- 关键数字散在 `/5`（票务 $40M/$17.5M、约数）与 `/9`（精确 $9,682,084/$45,001,744、首笔 1998-01-14）与 `/2`（BA 约 $3M/年）——单封无法给出全貌；
- 结论性质要求“诚实边界”：多数提案仍处评估/提案状态（Pressly 拒 jet swaps、塑料由 Howard 团队考虑、电力数据拖延），**无签约证据，也未见取消 BA 的记录**——好系统不能把“提案”说成“已签约/已取消”。

**判分（要素清单式，逐点命中给分）**：详见 jsonl 中 `answer_elements`（7 组：起因前史 / 伦敦方 / 休斯敦方 / 产品线方 / Continental 方 / 其他单元与背景 / 协调与结果），每组含“应给出的事实 + 对应证据”。盲审者可按清单核对模型答案覆盖了哪些事实、引用了哪些邮件。显式多跳路径见中文 jsonl 中 E1 的 `gold_path` 字段（时间链 + 实体关系链：10/25 会议 → 11/21 BA 协议 → 12/4 Wasaff–Dyson 协调 → 12/6 综述 → 12/11 简报 → 12/12 会议 → 12/15 纪要）。

**跑完怎么解释**：预期 Vector 只能给出碎片化罗列（某一封里的几个点），Graph 能按人/组织/事件链还原完整因果；若 Vector 意外全对，可写“top-k 恰好召回了所有关键信”，如实记录。

证据路径（11 封，均已核对存在于全量库）：
`arnold-j/continental_airlines/1.,2.,3.,4.,5.,9.,10.,11.,12.`、`arnold-j/all_documents/70.`

## 三、K1｜graph_limited（精确窄口径对照）——预期图低价值

**问题（精确版）**：Jeffrey Shankman 邮箱中关于 Intercontinental Exchange（ICE）注册的邮件（Sheri Thomas 2000-11-02 发起）说明：所有用户必须通过哪个内部流程注册？审批将模仿哪个既有系统？

**为什么是对照题**：答案完全落在**单封邮件**（`shankman-j/all_documents/786.`）的两句话里（eRequest；模仿 EnronOnline），不需要任何跨邮件关系 → Vector top-k 命中即答对，图结构无加成 → 证明“不是所有题都需要图”。

**跑完怎么解释**：预期 Vector=Graph 全对（或全错），用作“图无帮助/持平”的诚实对照案例，与 E1 的“图有帮助”形成对照。

## 四、自检结论

- 两份 jsonl 各 2 题：字段齐全（9 必备 + `evidence_quotes` + E1 的 `answer_elements`）、类别/取值合法、id 唯一；
- 全部 11 条证据路径均在**全量语料成员清单**中逐字命中（脚本校验 0 错误）；
- 证据摘录为原文逐字引用，可对照 `data/e1_mailset_prettified.txt` 复核。

## 五、合并/使用提示

1. **跑检索**：用 `questions_en.jsonl`（英文题目+英文参考答案），三种系统同一文本跑。
2. **合并**：`question_id` E1/K1 为占位符，并入共享 `questions.jsonl` 前请改成不与 A01–F02 冲突的编号（如 `<你的代号>1/2`）。
3. **校验**：仓库 `scripts/validate_enron_questions.py` 目前只认识 s0 的 `messages.jsonl`，对全量语料题会把证据判“不存在”——需等组长用全量语料生成新的 `messages.jsonl` 后再整体校验；本包的证据真实性已按全量成员清单核对。
4. **盲审**：把 `answer_elements` 清单给另一位同学，只凭证据摘录核对即可。
