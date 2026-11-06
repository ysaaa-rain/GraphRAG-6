# Enron 航空合作问答题集

> 本题集围绕跨邮件关系链和单事实检索设计两种类型的问题，分别观察图检索与向量检索在不同证据结构下的表现。
> 语料范围：Enron 完整邮件归档中与航空合作和 ICE 注册有关的邮件；与 California Power Crisis 66 封案例分别管理。
> 文件：`questions_zh.jsonl`、`questions_en.jsonl` 和生成脚本 `build.js`。

## 一、问题类型

| | E1（多文档关系问题） | K1（单事实问题） |
|---|---|---|
| 题型 | `multi_hop` | `graph_limited` |
| 提问口径 | 笼统、开放式：问“整个事件有哪些参与方、各方利益/立场/顾虑、分歧如何协调、走向什么结果” | 精确、有锚点：锁定一个具体流程/系统 |
| 邮件跨度 | 大：答案需拼接 **11+ 封、跨 2 个大区、≥6 方主体、3 个时间阶段** | 小：**1 封** 邮件即答 |
| 预期结果 | 适合检查图检索的跨文档证据整合能力 | 适合检验向量检索的直接事实召回 |

## 二、E1：跨邮件关系问题

**问题（笼统版）**：2000 年下半年 Enron 同时推进与 British Airways 与 Continental 两家航空公司的合作，内部出现跨伦敦/休斯敦、跨部门的取舍与协调。请还原全过程：参与方？各方利益/立场/顾虑？两套价值主张谁提出、依据什么？分歧如何协调、走向如何？按“参与方→利益→协调→结果”组织并给出邮件依据。

**证据组织特点**
- 答案要求把 **10/25 前史 → 11/21(BA 协议) → 12/4(Wasaff 回应/指派 Ramsey) → 12/7-12/11(会议筹备) → 12/12(会议) → 12/15(纪要行动项)** 六阶段串成一条因果链；
- 涉及至少 6 方：伦敦 Enron Europe（Dyson/Kemp/Bailey/Brown）、休斯敦 Global Strategic Sourcing（Wasaff/Hunter/Ramsey/Medcalf）、EGM/ENA 产品线（Shankman/Nowlan/Breslau/Tawney/Gagliardi/Engberg）、EES（电力）、Continental（Kellner/Howard/Hartford/Pressly/Rummel）、British Airways（对手方）；
- 关键数字散在 `/5`（票务 $40M/$17.5M、约数）与 `/9`（精确 $9,682,084/$45,001,744、首笔 1998-01-14）与 `/2`（BA 约 $3M/年）——单封无法给出全貌；
- 结论性质要求“诚实边界”：多数提案仍处评估/提案状态（Pressly 拒 jet swaps、塑料由 Howard 团队考虑、电力数据拖延），**无签约证据，也未见取消 BA 的记录**——好系统不能把“提案”说成“已签约/已取消”。

**判分（要素清单式，逐点命中给分）**：详见 jsonl 中 `answer_elements`（7 组：起因前史 / 伦敦方 / 休斯敦方 / 产品线方 / Continental 方 / 其他单元与背景 / 协调与结果），每组含“应给出的事实 + 对应证据”。盲审者可按清单核对模型答案覆盖了哪些事实、引用了哪些邮件。

**分析方式**：按照人物、部门、事件和时间关系检查两种检索方法的证据覆盖；逐条核对答案中的来源。

证据路径（11 封，均已核对存在于全量库）：
`arnold-j/continental_airlines/1.,2.,3.,4.,5.,9.,10.,11.,12.`、`arnold-j/all_documents/70.`

## 三、K1：直接事实问题

**问题（精确版）**：Jeffrey Shankman 邮箱中关于 Intercontinental Exchange（ICE）注册的邮件（Sheri Thomas 2000-11-02 发起）说明：所有用户必须通过哪个内部流程注册？审批将模仿哪个既有系统？

**为什么是对照题**：答案完全落在**单封邮件**（`shankman-j/all_documents/786.`）的两句话里（eRequest；模仿 EnronOnline），不需要任何跨邮件关系 → Vector top-k 命中即答对，图结构无加成 → 证明“不是所有题都需要图”。

**分析方式**：检查单封原文是否被检索命中，以及答案是否准确给出 eRequest 和 EnronOnline。

## 四、问题与证据

- 两份 jsonl 各 2 题：字段齐全（9 必备 + `evidence_quotes` + E1 的 `answer_elements`）、类别/取值合法、id 唯一；
- 全部 11 条证据路径均在**全量语料成员清单**中逐字命中（脚本校验 0 错误）；
- 证据摘录以原始邮件为依据，关联路径保存在题目文件中。

## 五、使用

`questions_en.jsonl` 保存英文问答与参考答案，`questions_zh.jsonl` 保存对应中文版本，`build.js` 用于生成题目文件。使用本题集时，应将其与 California Power Crisis 66 封案例分开处理，确保索引数据范围和证据来源一致。
