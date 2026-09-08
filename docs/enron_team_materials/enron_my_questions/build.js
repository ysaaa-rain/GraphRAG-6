// Enron 个人问题集 v2（全量语料版）构建脚本
// 2 题：E1 = 宽口径 multi_hop（BA vs Continental 资源取舍全景）
//       K1 = 精确窄口径 graph_limited 对照（单封 ICE 注册邮件）
// 运行: node build.js   -> 生成 questions_zh.jsonl / questions_en.jsonl
const fs = require('fs');
const path = require('path');

const QUESTIONS = [
  // =====================================================================
  // E1 宽口径多跳：2000 年底 Enron 内部 British Airways vs Continental 取舍
  // 预期：graph_help = high（跨 2 个大区/≥6 方主体/10+ 封邮件才能答全）
  // =====================================================================
  {
    id: 'E1',
    category: 'multi_hop',
    zh: {
      question:
        '2000 年下半年，Enron 同时推进与两家航空公司——欧洲的 British Airways 与美国的 Continental Airlines——的合作，内部因此出现了一场跨越伦敦与休斯敦、涉及多个部门的取舍与协调。请还原这一事件的全过程，并说明：① 参与方有哪些（Enron 内外、部门、公司、个人）；② 每一方各自的立场、利益诉求或顾虑是什么；③ 两套合作方案的“价值主张”分别由谁提出、依据是什么；④ 这场分歧最终如何协调、事件走向了什么结果？请按“参与方 → 利益/立场 → 协调过程 → 结果”组织回答，并标注支撑你结论的邮件依据（发件人、日期、要点）。',
      reference_answer:
        '（要素清单式，见 answer_elements；逐方逐点给分。）概要：Enron 与 Continental 原有燃油套保+差旅合作（1998 年起，1999–2000-10-06 Enron 赚约 $9.68M、Continental 省约 $45.0M；票务购买 FY1999 约 $40M、2000H1 约 $17.5M）。2000 年 10 月 25 日双方决策层会议决定把合作扩展到天气衍生品与塑料套保（12 月会议是给缺席的 Kellner 的跟进）。11 月 21 日伦敦 Enron Europe 的 Fernley Dyson 通知休斯敦：已与 British Airways 谈成优先供应商协议、每年约省 $3M（对照 Continental）；George Wasaff（Global Strategic Sourcing）坚持 Continental 并认为多线业务潜力可超过 BA 节省，指派 Tracy Ramsey 牵头尽快与 Continental 成交；Dyson 接受协作并催促加快。随后 12 月 12 日 Enron–Continental 会议如期举行（Shankman 对 Kellner），12 月 15 日纪要列出燃料管理（换票期权、crack spread）、天气衍生品（rebate、保险）、塑料/防冻液外包三条行动线。未发现取消 BA 协议的记录：可见走向是“欧洲保留 BA 协议，美国侧继续并加速 Continental 三线合作”；多数新提案仍处评估/提案状态，尚未见签约证据。',
    },
    en: {
      question:
        'In the second half of 2000, Enron was simultaneously pursuing relationships with two airlines -- British Airways in Europe and Continental Airlines in the US -- which created an internal trade-off and coordination effort spanning London and Houston and several business units. Reconstruct this whole episode and explain: (1) who the parties were (inside and outside Enron: units, companies, people); (2) the position, interest or concern of each party; (3) who advanced the "value proposition" of each of the two options and on what basis; and (4) how the conflict was eventually coordinated and how the episode turned out. Structure your answer as "parties -> interests/positions -> coordination -> outcome" and cite the e-mail evidence you rely on (sender, date, key points).',
      reference_answer:
        'Element-checklist style (see answer_elements); score element by element. Summary: Enron and Continental had an existing fuel-hedging and travel relationship (crude hedging since a January 14, 1998 Kero forward; 1999 to Oct 6, 2000 Enron earned about $9.68M and Continental saved about $45.0M; ticket purchases about $40M in FY1999 and $17.5M in 1H2000). An October 25, 2000 decision-maker meeting agreed to expand the relationship to weather derivatives and plastics hedging (the December meeting was a follow-up for Larry Kellner, who had missed Oct 25). On November 21 London-based Fernley Dyson of Enron Europe informed Houston that Enron Europe had negotiated a preferred supplier agreement with British Airways saving roughly $3M per year versus Continental; George Wasaff (Global Strategic Sourcing) preferred to stay the course with Continental, argued the multi-line potential could exceed BA\'s savings, and assigned Tracy Ramsey to take the lead in closing a Continental deal quickly; Dyson accepted the collaboration while pressing for speed. The December 12 Enron-Continental meeting then took place (Shankman with Kellner), and the December 15 minutes listed three action lines: fuel management (call options for tickets; crack spread), weather derivatives (rebate program; insurance product), and antifreeze/plastics outsourcing. No record of cancelling the BA agreement was found: the visible outcome is "BA agreement retained in Europe, while the US side continued and accelerated the three-line Continental collaboration"; most new proposals remained at proposal/evaluation stage with no signing evidence yet.',
    },
    evidence_paths: [
      'arnold-j/continental_airlines/1.',
      'arnold-j/continental_airlines/2.',
      'arnold-j/continental_airlines/3.',
      'arnold-j/continental_airlines/4.',
      'arnold-j/continental_airlines/5.',
      'arnold-j/continental_airlines/9.',
      'arnold-j/continental_airlines/10.',
      'arnold-j/continental_airlines/11.',
      'arnold-j/continental_airlines/12.',
      'arnold-j/all_documents/70.',
    ],
    evidence_quotes: [
      { source_path: 'arnold-j/continental_airlines/1.', quote: 'A subsequent meeting held October 25th enabled decision makers from both companies to act on these earlier discussions and explore opportunities to expand beyond the current fuel management and travel initiatives to those in weather derivatives and plastics hedging.' },
      { source_path: 'arnold-j/continental_airlines/1.', quote: 'December 11th Meeting Purpose: Follow-up from October 25th meeting to specifically address Larry Kellner (who could not make the October 25th meeting) on three initiatives in order of $ magnitude: (1) fuel management, (2) weather derivatives, and (3) plastics hedging -- VaR analysis.' },
      { source_path: 'arnold-j/continental_airlines/2.', quote: 'Enron Europe has negotiated a preferred supplier agreement with British Airways which will save us circa $3m a year vs Continental Airlines. I know there are existing and potential links with Continental, so please let me know if this causes you a problem. (Fernley Dyson, 11/21/2000)' },
      { source_path: 'arnold-j/continental_airlines/2.', quote: 'We have a number of key initiatives in process with Continental including sales of broadband services, weather derivatives and facility management that have the potential to exceed the savings being offered by British Airways. I would prefer that we stay the course with Continental plus I am confident that Continental can either meet or exceed BA\'s current offer. (George Wasaff, 12/4/2000)' },
      { source_path: 'arnold-j/continental_airlines/3.', quote: 'Happy to work for the greater good, but would welcome your help in nailing a deal with Continental quickly, as my understanding is that they have been unresponsive to date. (Fernley Dyson, 12/4/2000)' },
      { source_path: 'arnold-j/continental_airlines/4.', quote: 'Consider it done. Tracy Ramsey will take the lead in getting a deal done. (George Wasaff, 12/4/2000)' },
      { source_path: 'arnold-j/continental_airlines/5.', quote: 'Current Enron US spend on Continental airline tickets was approximately $40 million in FY 1999 and $17.5 million for the first six months of 2000. ... Enron has been hedging Continental\'s crude oil over the past 2+ years. Value to Enron has been over $9 million; value to Continental has been over $45 million since 1999.' },
      { source_path: 'arnold-j/continental_airlines/9.', quote: 'The first transaction was on January 14, 1998 -- a one month Forward on Kero. Since then, Enron has completed 29 transactions with two commodities: KERO and Crude. ... Value to Enron: Enron has earned $9,682,084 (1999-October 6, 2000) ... Value to Continental: Continental has saved $45,001,744 (1999-October 6, 2000).' },
      { source_path: 'arnold-j/continental_airlines/9.', quote: 'New initiatives being proposed ... exchanging call options on crude oil for airline tickets (Craig Breslau); transacting financial swaps on line (Larry Gagliardi); creating a weather derivative product for the airline industry (Mark Tawney and Gary Taylor); outsourcing Continental\'s antifreeze and plastics risks ... (Alan Engberg).' },
      { source_path: 'arnold-j/continental_airlines/12.', quote: 'MEETING MINUTES: The December 12th meeting addressed three initiatives in order of economic value: (1) fuel management, (2) weather derivatives, and (3) plastics hedging -- VaR analysis. (1) Fuel management (Craig Breslau; John Nowlan) -- exchanging call options on crude oil for airline tickets; crack spread product to address basis risk. (2) Weather derivatives (Mark Tawney; Gary Taylor) -- rebate program; insurance product. (3) Outsourcing antifreeze and plastics risk (Alan Engberg).' },
      { source_path: 'arnold-j/all_documents/70.', quote: 'Similarly, Continental has not yet sent over data that they were to request from HL&P. I talked with someone in Mark\'s group on 12/4, and she indicated that they had the data, but their real estate group wanted to review it before they sent it to us. On this one also, it is unlikely that any transaction will get done in this calendar year. (Walton Agnew, 12/11/2000)' },
    ],
    gold_entities: [
      'British Airways', 'Continental Airlines', 'Enron Europe', 'Fernley Dyson',
      'George Wasaff', 'Sarah-Joy Hunter', 'Tracy Ramsey', 'Jeff Shankman',
      'Larry Kellner', 'Ron Howard', 'Greg Hartford', 'Craig Breslau',
      'Mark Tawney', 'Alan Engberg', 'John Nowlan', 'Walton Agnew',
      '"circa $3m a year"', '$9,682,084', '$45,001,744', '$40 million', '$17.5 million',
    ],
    gold_relations: [
      'Dyson/Enron Europe 11/21 通知 BA 优先供应商协议（年省约 $3M vs Continental）',
      'Wasaff 12/4 坚持 Continental（宽带/天气/设施管理潜力可超 BA），指派 Ramsey 牵头',
      '10/25 会议决定扩展到天气衍生品与塑料套保；12 月会议为 Kellner 跟进',
      '原油套保 1998-01-14 起、29 笔；1999–2000-10-06 Enron $9,682,084 / Continental $45,001,744',
      '12/12 会议举行（Shankman–Kellner），12/15 纪要列三条行动线',
      'Continental 侧多提案仍处评估/提案状态（Pressly 拒 jet swaps、电力数据拖延）',
    ],
    gold_path:
      '时间链：10/25 会议(扩展合作) -> 11/21 Dyson(Enron Europe)告知 BA 协议 -> 12/4 Wasaff 回应(坚持 Continental、指派 Ramsey) -> 12/6 关系综述(Hunter) -> 12/11 会议简报(/9) -> 12/12 会议(Shankman-Kellner) -> 12/15 纪要(三条行动线)。实体关系链：Continental Airlines --[燃油套保/差旅大客户]--> Enron(Global Strategic Sourcing: Wasaff/Hunter/Ramsey) --[产品线 EGM/ENA: Shankman/Nowlan/Breslau/Tawney/Gagliardi/Engberg]--> 跨售天气/塑料/燃料产品；Enron Europe(Dyson/Kemp/Bailey) --[优先供应商协议]--> British Airways(年省约 $3M)；两线在 Wasaff-Dyson 之间冲突并协调（12/4 邮件链 2/3/4）。完整答案需沿上述链拼接 ≥6 方、跨伦敦/休斯敦与 10/25→12/15 五个以上邮件阶段。',
    expected_graph_help: 'high',
    answerability: 'answerable',
    answer_elements: [
      { party: '起因/前史', facts: ['10/25 决策层会议将合作扩展至天气衍生品与塑料套保', '12 月会议是对 Kellner（缺席 10/25）的跟进', '既有基础：1998-01-14 起原油套保、29 笔交易'], evidence: ['1.', '9.'] },
      { party: '伦敦 Enron Europe（Dyson；涉 Kemp/Bailey/Brown）', facts: ['11/21 与 BA 谈成优先供应商协议', '每年省约 $3M vs Continental', '顾虑 Continental 进展慢/不回应；愿协作但催快'], evidence: ['2.', '3.'] },
      { party: '休斯敦 Global Strategic Sourcing（Wasaff/Hunter/Ramsey）', facts: ['购买侧：FY1999 票务约 $40M、2000H1 约 $17.5M', '销售侧：套保价值 Enron $9,682,084 / Continental $45,001,744（1999–2000-10-06）', '立场：留在 Continental，潜力可超 BA；指派 Ramsey 牵头'], evidence: ['5.', '9.', '2.', '4.'] },
      { party: 'Enron 产品线 EGM/ENA（Shankman/Nowlan/Breslau/Tawney/Gagliardi/Engberg）', facts: ['10/25 Engberg/Tawney 演示塑料与天气机会', '新提案：换票期权、线上互换、航司天气产品、防冻液/塑料外包', '12/15 纪要行动项：燃料管理/天气/塑料三线'], evidence: ['1.', '9.', '12.'] },
      { party: 'Continental Airlines（Kellner/Howard/Hartford/Misner 等）', facts: ['利益：套保省成本（已省约 $45M）、扩展燃料管理、天气/塑料风险外包、电力供应潜力', '决策慢：Pressly 对 jet swaps 不感兴趣、天气无后续、塑料由 Howard 团队评估、HL&P 电力数据拖延'], evidence: ['9.', '70.', '5.'] },
      { party: '其他 Enron 单元与行业背景', facts: ['EES 在探索电力商品交易', 'Agnew 的公司能源项目同时覆盖 Dell/Continental', 'Enron 已与 Delta 在纽约港做航油实物（行业参考）'], evidence: ['5.', '70.', '9.'] },
      { party: '协调与结果', facts: ['11/21 Dyson 通知 -> 12/4 Wasaff 系列回复 -> 12/12 会议举行 -> 12/15 纪要', '未发现取消 BA 的记录：欧洲留 BA，美国加速 Continental 三线', '多数提案仍处评估/提案状态，无签约证据'], evidence: ['2.', '3.', '4.', '11.', '12.'] },
    ],
  },

  // =====================================================================
  // K1 精确窄口径对照：单封邮件即可回答（图无帮助，Vector 同等可达）
  // =====================================================================
  {
    id: 'K1',
    category: 'graph_limited',
    zh: {
      question:
        'Jeffrey Shankman 邮箱中关于 Intercontinental Exchange（ICE）注册的邮件（Sheri Thomas 2000 年 11 月 2 日发起）说明：所有用户必须通过哪个内部流程注册？该流程的审批方式将模仿哪个既有系统？',
      reference_answer:
        '所有用户必须通过 eRequest 注册；审批流程将模仿 EnronOnline 的做法（requester 需进入内部安全应用发起申请，批准流程与 EnronOnline 一致）。',
    },
    en: {
      question:
        'According to the Intercontinental Exchange (ICE) enrollment e-mail thread in Jeffrey Shankman\'s mailbox (initiated by Sheri Thomas on November 2, 2000): through which internal process must all users enroll, and which existing system will the approval process mimic?',
      reference_answer:
        'All users must enroll via eRequest, and the approval process will mimic that of EnronOnline (requesters go through the internal security application; approval mirrors EnronOnline).',
    },
    evidence_paths: ['shankman-j/all_documents/786.'],
    evidence_quotes: [
      { source_path: 'shankman-j/all_documents/786.', quote: 'In order to manage the enrollment of users onto this system, all users must enroll via eRequest.  The approval process will mimic that of EnronOnline.' },
    ],
    gold_entities: ['Intercontinental Exchange', 'eRequest', 'EnronOnline', 'Sheri Thomas', 'Jeffrey Shankman'],
    gold_relations: ['注册必须经 eRequest', '审批流程模仿 EnronOnline'],
    expected_graph_help: 'low',
    answerability: 'answerable',
  },
];

function recordFor(q, lang) {
  const r = {
    question_id: q.id,
    category: q.category,
    question: q[lang].question,
    reference_answer: q[lang].reference_answer,
    evidence_source_paths: q.evidence_paths,
    evidence_quotes: q.evidence_quotes,
    gold_entities: q.gold_entities,
    gold_relations: q.gold_relations,
    expected_graph_help: q.expected_graph_help,
    answerability: q.answerability,
  };
  if (q.answer_elements) r.answer_elements = q.answer_elements;
  if (lang === 'zh' && q.gold_path) r.gold_path = q.gold_path;
  return r;
}

const dir = __dirname;
fs.writeFileSync(path.join(dir, 'questions_zh.jsonl'),
  QUESTIONS.map((q) => JSON.stringify(recordFor(q, 'zh'))).join('\n') + '\n', 'utf8');
fs.writeFileSync(path.join(dir, 'questions_en.jsonl'),
  QUESTIONS.map((q) => JSON.stringify(recordFor(q, 'en'))).join('\n') + '\n', 'utf8');
console.log('WROTE ' + QUESTIONS.length + ' questions x2 files');
