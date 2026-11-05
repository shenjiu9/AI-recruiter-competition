// 演示数据。人名、公司、金额均为示例（PRD 0 文档信息）。时间相对“现在”生成，保证时限显示合理。
import type {
  AiActivity,
  Anomaly,
  Application,
  AutomationNode,
  Candidate,
  Conversation,
  DecisionCard,
  Evaluation,
  Handoff,
  Interview,
  KbEntry,
  OperationLog,
  Position,
  PositionHealth,
  Profile,
  Requisition,
  Resume,
  Slot,
} from '@recruiter/domain';
import type { BizInboxItem, CandidateBrief } from '../client';

const now = () => new Date();
export const hoursFromNow = (h: number) => new Date(now().getTime() + h * 3_600_000).toISOString();
const todayAt = (h: number, m = 0) => {
  const d = now();
  d.setHours(h, m, 0, 0);
  if (d.getTime() < Date.now()) d.setTime(Date.now() + 2 * 3_600_000);
  return d.toISOString();
};
const daysFromNowAt = (days: number, h: number, m = 0) => {
  const d = now();
  d.setDate(d.getDate() + days);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
};

export const positions: Position[] = [
  {
    id: 'JOB-202611-0017', version: 4, name: '华南大客户经理', dept: '销售部 / 华南大区', city: '深圳',
    status: 'open', ownerHr: '林悦', hiringManager: '周振华', planned: 2, hired: 1,
    salary: { low: 25, high: 32, unit: 'K/月', months: 14 }, expectedOnboard: daysFromNowAt(30, 9),
    confidential: false, health: 'watch', requisitionIds: ['REQ-202611-0042'],
  },
  {
    id: 'JOB-202611-0009', version: 7, name: '白班客服', dept: '客服中心', city: '深圳',
    status: 'open', ownerHr: '林悦', hiringManager: '何美玲', planned: 3, hired: 1,
    salary: { low: 7, high: 9, unit: 'K/月', months: 13 }, expectedOnboard: daysFromNowAt(40, 9),
    confidential: false, health: 'risk', requisitionIds: ['REQ-202611-0031'],
  },
  {
    id: 'JOB-202610-0044', version: 2, name: '客服主管', dept: '客服中心', city: '深圳',
    status: 'open', ownerHr: '林悦', hiringManager: '何美玲', planned: 1, hired: 0,
    salary: { low: 15, high: 20, unit: 'K/月', months: 13 }, expectedOnboard: daysFromNowAt(45, 9),
    confidential: false, health: 'ok', requisitionIds: ['REQ-202610-0118'],
  },
  {
    id: 'JOB-202610-0021', version: 9, name: '数据分析师', dept: '经营分析部', city: '上海',
    status: 'open', ownerHr: '林悦', hiringManager: '方启明', planned: 1, hired: 1,
    salary: { low: 22, high: 30, unit: 'K/月', months: 14 }, expectedOnboard: daysFromNowAt(-3, 9),
    confidential: false, health: 'ok', requisitionIds: ['REQ-202610-0077'],
  },
];

export const candidates: Candidate[] = [
  { id: 'c1', version: 3, name: '陈佳怡', phoneMasked: '138****6721', emailMasked: 'ch***@163.com', city: '深圳', currentCompany: '云策科技', currentTitle: '客户成功经理', years: 6, education: '本科', isKey: false, consent: 'granted', tags: ['大客户', 'SaaS'] },
  { id: 'c2', version: 2, name: '王磊', phoneMasked: '139****0288', emailMasked: 'wl***@qq.com', city: '深圳', currentCompany: '恒信软件', currentTitle: '高级客户经理', years: 8, education: '本科', isKey: true, consent: 'granted', tags: ['渠道'] },
  { id: 'c3', version: 1, name: '李婷', phoneMasked: '136****1934', emailMasked: 'lt***@gmail.com', city: '深圳', currentCompany: '速达物流', currentTitle: '客服组长', years: 5, education: '大专', isKey: false, consent: 'granted', tags: [] },
  { id: 'c4', version: 1, name: '赵晨', phoneMasked: '137****5520', emailMasked: 'zc***@163.com', city: '广州', currentCompany: '乐享电商', currentTitle: '客服专员', years: 2, education: '大专', isKey: false, consent: 'granted', tags: [] },
  { id: 'c5', version: 1, name: '孙悦', phoneMasked: '135****7781', emailMasked: 'sy***@126.com', city: '深圳', currentCompany: '星河保险', currentTitle: '客服主管', years: 7, education: '本科', isKey: false, consent: 'none', tags: ['人才库'] },
];

export const applications: Application[] = [
  { id: 'APP-000038201544', version: 7, candidateId: 'c1', positionId: 'JOB-202611-0017', positionName: '华南大客户经理', stage: 'interview', subStatus: '第 1 轮已完成，待定是否进入复试', startedAt: daysFromNowAt(-9, 10), source: 'BOSS直聘投递' },
  { id: 'APP-000037110092', version: 5, candidateId: 'c1', positionId: 'JOB-202610-0044', positionName: '客服主管', stage: 'ai_eval', subStatus: '已结束', ended: { result: 'rejected', reason: '不满足必备条件：5 年以上客服团队管理', at: '2026-08-14T03:00:00Z' }, startedAt: '2026-08-02T03:00:00Z', source: '人才库' },
  { id: 'APP-000038201601', version: 3, candidateId: 'c2', positionId: 'JOB-202611-0017', positionName: '华南大客户经理', stage: 'talking', subStatus: '转人工', startedAt: daysFromNowAt(-3, 14), source: '智联招聘投递' },
  { id: 'APP-000038201733', version: 2, candidateId: 'c3', positionId: 'JOB-202610-0044', positionName: '客服主管', stage: 'interview', subStatus: '第 1 轮：约面中', startedAt: daysFromNowAt(-6, 9), source: 'BOSS直聘投递' },
  { id: 'APP-000038201802', version: 1, candidateId: 'c4', positionId: 'JOB-202611-0009', positionName: '白班客服', stage: 'ai_eval', subStatus: '待确认', startedAt: daysFromNowAt(-1, 11), source: 'HR 导入' },
];

export const resumes: Record<string, Resume> = {
  c1: {
    candidateId: 'c1',
    fileName: '陈佳怡-客户成功经理-6年.pdf',
    paragraphs: [
      { ref: 'R1', text: '陈佳怡，深圳，本科（华南理工大学 市场营销，2018 届）。' },
      { ref: 'R2', text: '2018–2021 恒远信息 客户经理：负责制造业中小客户的签约与回款，个人年签约额约 900 万元。' },
      { ref: 'R3', text: '2021–2024 云策科技 客户成功经理：负责华南区大客户续约，年续约率 92%，管理客户 46 家，年合同额约 3,800 万元。' },
      { ref: 'R4', text: '主导 SaaS 产品在 3 家上市公司的落地，推动年度增购，平均增购金额 120 万元。' },
      { ref: 'R5', text: '2024 至今 云策科技 客户成功高级经理：带 4 人小组，负责 12 家战略客户的季度经营复盘与续约谈判。' },
      { ref: 'R6', text: '技能：客户分层运营、商务谈判、Salesforce、Power BI。' },
      { ref: 'R7', text: '证书：PMP。语言：英语 CET-6，粤语流利。' },
    ],
  },
  c2: {
    candidateId: 'c2', fileName: '王磊-高级客户经理.pdf',
    paragraphs: [
      { ref: 'R1', text: '王磊，深圳，本科，8 年 B2B 销售经验。' },
      { ref: 'R2', text: '2019 至今 恒信软件 高级客户经理：负责华南渠道合作伙伴 30 余家，年渠道销售额约 6,000 万元。' },
    ],
  },
  c3: {
    candidateId: 'c3', fileName: '李婷-客服组长.pdf',
    paragraphs: [
      { ref: 'R1', text: '李婷，深圳，大专，5 年客服经验。' },
      { ref: 'R2', text: '2021 至今 速达物流 客服组长：管理 12 人白班团队，首次解决率从 71% 提升到 84%。' },
    ],
  },
  c4: { candidateId: 'c4', fileName: '赵晨-客服专员.pdf', paragraphs: [{ ref: 'R1', text: '赵晨，广州，大专，2 年电商客服经验。' }] },
  c5: { candidateId: 'c5', fileName: '孙悦-客服主管.pdf', paragraphs: [{ ref: 'R1', text: '孙悦，深圳，本科，7 年保险客服经验，现任客服主管。' }] },
};

export const evaluations: Record<string, Evaluation> = {
  'APP-000038201544': {
    applicationId: 'APP-000038201544', conclusion: 'advance', score: 87, confidence: 0.89, lowReasons: [],
    profileVersion: 3, at: daysFromNowAt(-7, 15),
    items: [
      { id: 'M1', type: 'must', text: '3 年以上 B2B 大客户经营经验', verdict: 'meet', evidence: [{ kind: 'resume', ref: 'R3', quote: '负责华南区大客户续约，年续约率 92%' }, { kind: 'resume', ref: 'R5', quote: '负责 12 家战略客户的季度经营复盘与续约谈判' }], note: '2021 年起持续负责大客户续约与经营。' },
      { id: 'M2', type: 'must', text: '能独立完成年合同额 1,000 万元以上的续约谈判', verdict: 'meet', evidence: [{ kind: 'resume', ref: 'R3', quote: '年合同额约 3,800 万元' }], note: '管理的客户年合同额远超要求。' },
      { id: 'M3', type: 'must', text: '常驻深圳，能接受每月 1 周华南区内出差', verdict: 'meet', evidence: [{ kind: 'message', ref: 'm-91', quote: '每月出差一周没问题，之前也经常跑广州和佛山' }], note: '沟通中已确认。' },
      { id: 'M4', type: 'must', text: '本科及以上学历', verdict: 'meet', evidence: [{ kind: 'resume', ref: 'R1', quote: '本科（华南理工大学 市场营销，2018 届）' }], note: '' },
      { id: 'P1', type: 'plus', text: '有 SaaS 产品落地或增购经验', weight: '高', verdict: 'meet', evidence: [{ kind: 'resume', ref: 'R4', quote: '主导 SaaS 产品在 3 家上市公司的落地' }], note: '' },
      { id: 'P2', type: 'plus', text: '有带团队经验', weight: '中', verdict: 'meet', evidence: [{ kind: 'resume', ref: 'R5', quote: '带 4 人小组' }], note: '团队规模较小。' },
      { id: 'P3', type: 'plus', text: '熟悉制造业客户', weight: '低', verdict: 'unknown', evidence: [], note: '简历只提到早期的中小制造业客户。', question: '您服务过的大客户里，制造业客户大概占多少？' },
      { id: 'X1', type: 'redflag', text: '近 3 年内跳槽 3 次以上', verdict: 'not_meet', evidence: [{ kind: 'resume', ref: 'R3', quote: '2021–2024 云策科技' }], note: '近 5 年只换过 1 次工作，未命中。' },
    ],
  },
  'APP-000038201802': {
    applicationId: 'APP-000038201802', conclusion: 'need_info', score: 58, confidence: 0.52,
    lowReasons: ['3 次判断不一致', '2 条必备条件信息缺失'], profileVersion: 2, at: hoursFromNow(-5),
    items: [
      { id: 'M1', type: 'must', text: '1 年以上客服经验', verdict: 'meet', evidence: [{ kind: 'resume', ref: 'R1', quote: '2 年电商客服经验' }], note: '' },
      { id: 'M2', type: 'must', text: '能接受早 8 点到晚 5 点的白班排班', verdict: 'unknown', evidence: [], note: '', question: '白班是早 8 点到晚 5 点，做五休二，您可以接受吗？' },
      { id: 'M3', type: 'must', text: '能在深圳南山区到岗', verdict: 'unknown', evidence: [], note: '候选人目前在广州。', question: '岗位在深圳南山区，您方便过来工作吗？' },
    ],
  },
};

export const conversations: Record<string, Conversation> = {
  c1: {
    candidateId: 'c1', mode: 'ai',
    messages: [
      { id: 'm-80', sender: 'ai', text: '陈佳怡您好，我是星汇科技的 AI 招聘助手。看到您投递了华南大客户经理，想先了解几个情况，大约需要 3 分钟。您随时可以回复“转人工”找招聘顾问。', at: daysFromNowAt(-9, 10, 12) },
      { id: 'm-81', sender: 'candidate', text: '你好，这个岗位在深圳哪里办公？薪资大概多少？', at: daysFromNowAt(-9, 10, 20) },
      { id: 'm-82', sender: 'ai', text: '办公地点在深圳南山区科技园。这个岗位的对外薪资区间是 25–32K，14 薪，具体以面试结果为准。方便说一下您的期望薪资吗？', at: daysFromNowAt(-9, 10, 20), kbRefs: ['KB-03', 'KB-11'] },
      { id: 'm-88', sender: 'candidate', text: '期望 28K 左右。', at: daysFromNowAt(-9, 10, 31) },
      { id: 'm-89', sender: 'ai', text: '收到。这个岗位每月需要在华南区内出差约 1 周，您能接受吗？', at: daysFromNowAt(-9, 10, 31) },
      { id: 'm-91', sender: 'candidate', text: '每月出差一周没问题，之前也经常跑广州和佛山。', at: daysFromNowAt(-9, 10, 40) },
      { id: 'm-92', sender: 'ai', text: '好的，信息已经齐了。我们会在 2 小时内告诉您下一步安排。', at: daysFromNowAt(-9, 10, 40) },
      { id: 'm-120', sender: 'ai', text: '您好，第 1 轮面试已经完成，感谢参加。面试官正在讨论结果，有进展我会第一时间通知您。', at: daysFromNowAt(-1, 17, 5) },
    ],
  },
  c2: {
    candidateId: 'c2', mode: 'handoff', handoffReason: '候选人希望谈超出对外区间的薪资', handoffDueAt: hoursFromNow(1.5),
    messages: [
      { id: 'm-201', sender: 'ai', text: '王磊您好，我是星汇科技的 AI 招聘助手。想确认一下您对华南大客户经理岗位的期望薪资。', at: hoursFromNow(-3) },
      { id: 'm-202', sender: 'candidate', text: '我现在年包 50 万左右，期望涨 20%，你们能给到吗？', at: hoursFromNow(-0.6) },
      { id: 'm-203', sender: 'ai', text: '这个问题我需要请招聘顾问确认后回复您，工作时间 2 小时内会有人联系您。', at: hoursFromNow(-0.6) },
      { id: 'd-1', sender: 'ai', draft: true, text: '王磊您好，我是招聘顾问林悦。这个岗位的对外区间是 25–32K，14 薪，按您的期望，我们可以安排面试后结合评估结果再谈具体方案，您看可以吗？', at: hoursFromNow(-0.5) },
    ],
  },
};

export const operationLogs: Record<string, OperationLog[]> = {
  c1: [
    { at: daysFromNowAt(-1, 18, 2), actor: 'AI 招聘官（林悦）', isAi: true, text: '生成决策卡“是否让陈佳怡进入复试”，建议进入复试，把握 0.89' },
    { at: daysFromNowAt(-1, 16, 40), actor: '周振华', isAi: false, text: '提交第 1 轮面评：推荐' },
    { at: daysFromNowAt(-3, 11, 0), actor: 'AI 招聘官（林悦）', isAi: true, text: '确认面试时间 · 第 1 轮（L3 自动执行）' },
    { at: daysFromNowAt(-7, 15, 2), actor: '林悦', isAi: false, text: '确认筛选结论：进入面试' },
    { at: daysFromNowAt(-9, 10, 12), actor: 'AI 招聘官（林悦）', isAi: true, text: '首次联系候选人，发送 AI 身份说明与授权链接' },
  ],
};

const rejectBatch = [
  { applicationId: 'APP-000038201901', candidateName: '刘洋', reason: '不满足必备条件：能接受白班排班（候选人明确只做晚班）', confidence: 0.93 },
  { applicationId: 'APP-000038201902', candidateName: '周敏', reason: '不满足必备条件：1 年以上客服经验', confidence: 0.9 },
  { applicationId: 'APP-000038201903', candidateName: '吴昊', reason: '不满足必备条件：能在深圳南山区到岗', confidence: 0.88 },
  { applicationId: 'APP-000038201904', candidateName: '郑爽', reason: '命中不合适信号：半年内两次离职', confidence: 0.71 },
  { applicationId: 'APP-000038201905', candidateName: '何静', reason: '不满足必备条件：1 年以上客服经验（简历与沟通说法不一致）', confidence: 0.54 },
];

export const cards: DecisionCard[] = [
  {
    id: 'card-1', version: 1, type: 'screen_result', title: '是否让陈佳怡进入复试', object: { type: 'application', id: 'APP-000038201544' },
    positionName: '华南大客户经理', candidateId: 'c1', suggestion: '进入复试', confidence: 0.89, level: 2, dueAt: todayAt(18),
    reasons: [
      { text: '第 1 轮两位面试官都给了“推荐”，客户经营和沟通两项是本岗位近 3 个月面试者中的最高分', evidence: [{ kind: 'feedback', ref: 'F1', quote: '周振华：对续约谈判的拆解很清楚，能直接带战略客户。' }] },
      { text: '满足全部 4 条必备条件，其中“3 年以上大客户经营”有两段简历证据', evidence: [{ kind: 'resume', ref: 'R3', quote: '2021–2024 云策科技 客户成功经理：负责华南区大客户续约，年续约率 92%，管理客户 46 家，年合同额约 3,800 万元。' }, { kind: 'resume', ref: 'R5', quote: '带 4 人小组，负责 12 家战略客户的季度经营复盘与续约谈判。' }] },
      { text: '期望薪资 28K，在对外区间 25–32K 内', evidence: [{ kind: 'message', ref: 'm-88', quote: '期望 28K 左右。' }] },
    ],
    options: [
      { key: 'advance', label: '确认进入复试', primary: true },
      { key: 'reject', label: '淘汰', danger: true, confirm: '将按模板给陈佳怡发送淘汰通知，发出后无法撤回。' },
      { key: 'mine', label: '转给我处理' },
    ],
    state: 'open',
  },
  {
    id: 'card-2', version: 1, type: 'reject_confirm', title: '淘汰白班客服的 5 位候选人', object: { type: 'position', id: 'JOB-202611-0009' },
    positionName: '白班客服', suggestion: '淘汰并发送通知', confidence: 0.79, level: 2, dueAt: daysFromNowAt(1, 12),
    reasons: [
      { text: '4 人不满足必备条件，1 人命中不合适信号', evidence: [{ kind: 'rule', ref: '画像 v2', quote: '必备：1 年以上客服经验；能接受白班排班；能在深圳南山区到岗。' }] },
      { text: '何静的把握低：简历写 2 年经验，沟通中说“做过几个月”，需要你单独判断', evidence: [{ kind: 'message', ref: 'm-311', quote: '之前在电商做过几个月客服。' }] },
    ],
    options: [
      { key: 'reject', label: '淘汰选中的人', primary: true, danger: true, confirm: '将按模板发送淘汰通知，发出后无法撤回。' },
      { key: 'keep', label: '全部保留' },
    ],
    batch: rejectBatch, state: 'open',
  },
  {
    id: 'card-3', version: 1, type: 'salary_over', title: '王磊的期望薪资高于对外区间', object: { type: 'application', id: 'APP-000038201601' },
    positionName: '华南大客户经理', candidateId: 'c2', suggestion: '转给 HR 谈薪', confidence: 0.82, level: 2, dueAt: todayAt(17, 30), isKey: true,
    reasons: [
      { text: '候选人期望年包约 60 万元，按 14 薪折算约 43K，高于对外区间上限 32K', evidence: [{ kind: 'message', ref: 'm-202', quote: '我现在年包 50 万左右，期望涨 20%，你们能给到吗？' }] },
      { text: '候选人已被标记为关键候选人，对外动作最高 L2', evidence: [{ kind: 'rule', ref: '关键候选人', quote: '被标记为关键候选人的人，每条 AI 草拟回复先经 HR 确认。' }] },
    ],
    options: [
      { key: 'hr', label: '我来谈薪', primary: true },
      { key: 'tell_range', label: '继续推进并告知区间' },
      { key: 'reject', label: '淘汰', danger: true, confirm: '将按模板给王磊发送淘汰通知，发出后无法撤回。' },
    ],
    state: 'open',
  },
  {
    id: 'card-4', version: 1, type: 'schedule_conflict', title: '李婷的面试找不到共同空闲时间', object: { type: 'application', id: 'APP-000038201733' },
    positionName: '客服主管', candidateId: 'c3', suggestion: '换成面试官组里的田野', confidence: 0.74, level: 2, dueAt: todayAt(19),
    reasons: [
      { text: '原面试官何美玲未来 7 个工作日日程已满', evidence: [{ kind: 'rule', ref: '飞书日历', quote: '何美玲 11 月 6 日至 14 日工作时段全部忙碌。' }] },
      { text: '同组面试官田野有 4 个时段与候选人偏好的“下午”重合', evidence: [{ kind: 'message', ref: 'm-415', quote: '下午都可以，上午要带班。' }] },
    ],
    options: [
      { key: 'swap', label: '换成田野', primary: true },
      { key: 'later', label: '扩大到 14 个工作日' },
      { key: 'online', label: '改为线上面试' },
    ],
    state: 'open',
  },
  {
    id: 'card-5', version: 1, type: 'screen_result', title: '是否让赵晨进入面试', object: { type: 'application', id: 'APP-000038201802' },
    positionName: '白班客服', candidateId: 'c4', suggestion: '先补问 2 个问题', confidence: 0.52, lowReasons: ['3 次判断不一致', '2 条必备条件信息缺失'], level: 2, dueAt: daysFromNowAt(1, 10),
    reasons: [
      { text: '“能接受白班排班”和“能在深圳南山区到岗”两条必备条件还不知道', evidence: [{ kind: 'resume', ref: 'R1', quote: '赵晨，广州，大专，2 年电商客服经验。' }] },
    ],
    options: [
      { key: 'ask', label: '让 AI 补问', primary: true },
      { key: 'advance', label: '直接进入面试' },
      { key: 'reject', label: '淘汰', danger: true, confirm: '将按模板给赵晨发送淘汰通知，发出后无法撤回。' },
    ],
    state: 'open',
  },
  {
    id: 'card-6', version: 1, type: 'suggest_attach', title: '是否把孙悦挂到客服主管', object: { type: 'candidate', id: 'c5' },
    positionName: '客服主管', candidateId: 'c5', suggestion: '挂到本岗位', confidence: 0.86, level: 2, dueAt: daysFromNowAt(3, 18),
    reasons: [
      { text: '人才库中匹配分 91：7 年客服经验，现任客服主管', evidence: [{ kind: 'resume', ref: 'R1', quote: '7 年保险客服经验，现任客服主管。' }] },
      { text: '不在冷却期，最近 30 天没有被主动联系过', evidence: [{ kind: 'rule', ref: '冷却期', quote: '淘汰后 6 个月内不再触达同岗位及同序列同职级岗位。' }] },
    ],
    options: [
      { key: 'attach', label: '挂到客服主管', primary: true },
      { key: 'skip', label: '不挂' },
    ],
    state: 'open',
  },
  {
    id: 'card-7', version: 1, type: 'suggest_close', title: '数据分析师已招满，是否关闭岗位', object: { type: 'position', id: 'JOB-202610-0021' },
    positionName: '数据分析师', suggestion: '关闭岗位', confidence: 0.95, level: 1, dueAt: daysFromNowAt(3, 18),
    reasons: [{ text: '计划 1 人，已录用 1 人，可招人数为 0', evidence: [{ kind: 'rule', ref: '可招人数', quote: '可招 = 已通过来源需求人数之和 − 已录用人数。' }] }],
    options: [
      { key: 'close', label: '关闭岗位', primary: true, confirm: '关闭后各渠道下线，在途的 2 位候选人会转到“岗位关闭终止”。' },
      { key: 'pause', label: '暂停' },
      { key: 'keep', label: '保持招聘' },
    ],
    state: 'open',
  },
];

export const activity: AiActivity[] = [
  { actionId: 'act-1', at: hoursFromNow(-0.3), text: '向白班客服岗位的 32 人发出首条消息，已有 9 人回复', level: 3, reversible: false, reason: '岗位每日触达额度 32 人，按画像精排取前 32 名' },
  { actionId: 'act-2', at: hoursFromNow(-0.8), text: '把 3 位候选人推进到面试：客服主管 1 人，白班客服 2 人', level: 3, reversible: true, undoUntil: hoursFromNow(23), reason: '三人把握均 ≥ 0.85，白班客服的“AI 推进”环节为 L3' },
  { actionId: 'act-3', at: hoursFromNow(-1.4), text: '回复候选人周婷关于班车路线的问题', level: 3, reversible: false, reason: '引用知识库 KB-07“通勤与班车”' },
  { actionId: 'act-4', at: hoursFromNow(-2.1), text: '为李婷确认面试时间，第 1 轮，11 月 12 日 14:00', level: 3, reversible: true, undoUntil: hoursFromNow(21), reason: '候选人选择了 4 个时段中的第 2 个' },
  { actionId: 'act-5', at: hoursFromNow(-3.2), text: '为客服主管生成画像草稿，等用人经理确认', level: 2, reversible: true, undoUntil: hoursFromNow(20), reason: '岗位刚生成，画像为空' },
];

export const health: PositionHealth[] = [
  { positionId: 'JOB-202611-0009', name: '白班客服', openings: 2, total: 3, health: 'risk', why: '7 个工作日没有人进入面试' },
  { positionId: 'JOB-202611-0017', name: '华南大客户经理', openings: 1, total: 2, health: 'watch', why: '预计到岗比期望晚 3–8 个工作日' },
  { positionId: 'JOB-202610-0044', name: '客服主管', openings: 1, total: 1, health: 'ok', why: '各阶段转化正常' },
  { positionId: 'JOB-202610-0021', name: '数据分析师', openings: 0, total: 1, health: 'ok', why: '已招满' },
];

export const handoffs: Handoff[] = [
  { candidateId: 'c2', candidateName: '王磊', positionName: '华南大客户经理', reason: '超出对外区间的薪资协商', dueAt: hoursFromNow(1.5), lastMessage: '我现在年包 50 万左右，期望涨 20%，你们能给到吗？' },
  { candidateId: 'c3', candidateName: '李婷', positionName: '客服主管', reason: '知识库没有答案：是否提供宿舍', dueAt: hoursFromNow(1.1), lastMessage: '公司有员工宿舍吗？' },
  { candidateId: 'c4', candidateName: '赵晨', positionName: '白班客服', reason: '候选人要求人工', dueAt: hoursFromNow(0.4), lastMessage: '能找个真人聊吗' },
];

export const anomalies: Anomaly[] = [
  { id: 'an-1', kind: '面评超时', text: '客服主管第 1 轮（候选人李婷的同批次面试）：何美玲已超过 24 小时未提交面评，AI 已催过 1 次', link: '/interviews' },
  { id: 'an-2', kind: '渠道账号异常', text: '智联招聘企业账号登录失效，新简历暂时收不到', link: '/settings/automation' },
];

export const requisitions: Requisition[] = [
  { id: 'REQ-202611-0042', version: 3, no: 'REQ-202611-0042', title: '华南大客户经理', dept: '销售部 / 华南大区', type: 'additional', headcount: 1, initiator: '周振华', mode: 'self', status: 'approved', positionId: 'JOB-202611-0017', submittedAt: daysFromNowAt(-12, 10) },
  { id: 'REQ-202611-0051', version: 2, no: 'REQ-202611-0051', title: '白班客服', dept: '客服中心', type: 'replace', headcount: 2, initiator: '何美玲', mode: 'proxy', proxyBy: '林悦', status: 'in_approval', waitingFor: '方启明', waitingDays: 3, submittedAt: daysFromNowAt(-3, 9) },
  { id: 'REQ-202611-0055', version: 1, no: 'REQ-202611-0055', title: '售前解决方案顾问', dept: '销售部 / 华南大区', type: 'new', headcount: 1, initiator: '周振华', mode: 'ai_draft', status: 'draft', waitingFor: '周振华' },
  { id: 'REQ-202611-0031', version: 4, no: 'REQ-202611-0031', title: '白班客服', dept: '客服中心', type: 'new', headcount: 3, initiator: '何美玲', mode: 'self', status: 'approved', positionId: 'JOB-202611-0009', submittedAt: daysFromNowAt(-20, 10) },
  { id: 'REQ-202610-0118', version: 2, no: 'REQ-202610-0118', title: '客服主管', dept: '客服中心', type: 'replace', headcount: 1, initiator: '何美玲', mode: 'self', status: 'approved', positionId: 'JOB-202610-0044', submittedAt: daysFromNowAt(-26, 10) },
  { id: 'REQ-202610-0130', version: 3, no: 'REQ-202610-0130', title: '财务专员', dept: '财务部', type: 'new', headcount: 1, initiator: '黄丽', mode: 'self', status: 'rejected', waitingFor: '黄丽', submittedAt: daysFromNowAt(-8, 10) },
];

export const profiles: Record<string, Profile> = {
  'JOB-202611-0017': {
    positionId: 'JOB-202611-0017', version: 3, confirmedBy: '周振华',
    items: [
      { id: 'M1', type: 'must', text: '3 年以上 B2B 大客户经营经验' },
      { id: 'M2', type: 'must', text: '能独立完成年合同额 1,000 万元以上的续约谈判' },
      { id: 'M3', type: 'must', text: '常驻深圳，能接受每月 1 周华南区内出差' },
      { id: 'M4', type: 'must', text: '本科及以上学历' },
      { id: 'P1', type: 'plus', text: '有 SaaS 产品落地或增购经验', weight: '高' },
      { id: 'P2', type: 'plus', text: '有带团队经验', weight: '中' },
      { id: 'P3', type: 'plus', text: '熟悉制造业客户', weight: '低' },
      { id: 'X1', type: 'redflag', text: '近 3 年内跳槽 3 次以上' },
      { id: 'Q1', type: 'must_ask', text: '期望薪资' },
      { id: 'Q2', type: 'must_ask', text: '能否接受每月出差约 1 周' },
    ],
  },
};

export const kb: KbEntry[] = [
  { id: 'KB-03', scope: 'position', title: '办公地点', content: '深圳南山区科技园，地铁 1 号线高新园站步行 8 分钟。', disclosure: 'proactive' },
  { id: 'KB-11', scope: 'position', title: '对外薪资区间', content: '25–32K，14 薪；具体以面试结果为准。', disclosure: 'on_ask' },
  { id: 'KB-07', scope: 'company', title: '通勤与班车', content: '工作日早晚各两班班车，覆盖福田、宝安主要地铁站。', disclosure: 'on_ask' },
  { id: 'KB-15', scope: 'company', title: '五险一金', content: '按深圳最高比例缴纳五险一金，另有补充医疗保险。', disclosure: 'on_ask' },
  { id: 'KB-21', scope: 'position', title: '团队介绍', content: '华南大区客户经营团队共 9 人，直属负责人周振华。', disclosure: 'proactive' },
  { id: 'KB-30', scope: 'position', title: '年终奖', content: '仅供内部参考，不对外说明。', disclosure: 'internal' },
];

export const interviews: Interview[] = [
  { id: 'iv1', version: 1, no: 'IV-20261106-0031', candidateId: 'c1', candidateName: '陈佳怡', positionName: '华南大客户经理', round: 2, roundName: '复试', form: '现场', status: 'to_schedule', interviewers: ['周振华', '冯涛'], feedbackDone: 0, feedbackTotal: 2 },
  { id: 'iv2', version: 2, no: 'IV-20261112-0008', candidateId: 'c3', candidateName: '李婷', positionName: '客服主管', round: 1, roundName: '业务面', form: '视频', status: 'scheduling', interviewers: ['何美玲'], feedbackDone: 0, feedbackTotal: 1, conflict: '面试官 7 个工作日内无空闲' },
  { id: 'iv3', version: 3, no: 'IV-20261105-0019', candidateId: 'c6', candidateName: '黎晓', positionName: '白班客服', round: 1, roundName: '业务面', form: '现场', start: todayAt(15), end: todayAt(15, 45), status: 'confirmed', interviewers: ['何美玲'], feedbackDone: 0, feedbackTotal: 1 },
  { id: 'iv4', version: 3, no: 'IV-20261104-0022', candidateId: 'c7', candidateName: '邓可', positionName: '客服主管', round: 1, roundName: '业务面', form: '视频', start: daysFromNowAt(-1, 10), end: daysFromNowAt(-1, 11), status: 'to_feedback', interviewers: ['何美玲', '田野'], feedbackDone: 1, feedbackTotal: 2 },
  { id: 'iv5', version: 4, no: 'IV-20261104-0011', candidateId: 'c1', candidateName: '陈佳怡', positionName: '华南大客户经理', round: 1, roundName: '业务面', form: '视频', start: daysFromNowAt(-1, 14), end: daysFromNowAt(-1, 15), status: 'done', interviewers: ['周振华', '冯涛'], feedbackDone: 2, feedbackTotal: 2 },
];

export const automation: AutomationNode[] = [
  { key: 'req_draft', name: '需求起草', level: 3, allowed: [1, 3], note: 'AI 只生成草稿，提交永远由人完成' },
  { key: 'jd_publish', name: 'JD 生成与渠道发布', level: 2, allowed: [1, 2, 3], note: '开启 JD 审批时实际上限为 L2' },
  { key: 'outreach', name: '主动触达', level: 3, allowed: [1, 2, 3], note: '受每日触达上限与发送时间窗口约束' },
  { key: 'reply', name: '回复候选人', level: 3, allowed: [1, 2, 3], note: '校验拦截率 1 小时超过 20% 时自动降为 L2' },
  { key: 'advance', name: 'AI 推进到面试', level: 2, allowed: [1, 2, 3], note: '把握低于 0.6 时一律降为 L2' },
  { key: 'reject', name: '淘汰', level: 2, allowed: [1, 2], cap: '最高 L2', note: '淘汰永远需要人确认' },
  { key: 'schedule', name: '约面与改期', level: 3, allowed: [1, 2, 3], note: '无共同时段时生成约面冲突卡' },
  { key: 'feedback_remind', name: '催面评', level: 3, allowed: [1, 2, 3], note: '面试结束 24 小时未提交时提醒' },
  { key: 'hire_suggest', name: '录用建议', level: 1, allowed: [1], cap: '固定 L1', note: '录用只由用人经理决定' },
];

export const bizInbox: BizInboxItem[] = [
  { id: 'b1', kind: 'recommendation', title: '是否想见陈佳怡（复试）', detail: '华南大客户经理｜第 1 轮两位面试官均推荐｜期望 28K，在区间内', applicationId: 'APP-000038201544', dueAt: todayAt(18) },
  { id: 'b2', kind: 'requisition_approval', title: '审批：白班客服替补 2 人', detail: '客服中心｜何美玲发起、林悦代填｜在 HC 内，薪资未超带宽', dueAt: daysFromNowAt(1, 12) },
  { id: 'b3', kind: 'feedback', title: '提交邓可的面评', detail: '客服主管第 1 轮｜面试已结束 26 小时', applicationId: 'APP-000038201733', dueAt: hoursFromNow(-2) },
];

export const briefs: Record<string, CandidateBrief> = {
  'APP-000038201544': {
    applicationId: 'APP-000038201544', name: '陈佳怡', phoneMasked: '138****6721', positionName: '华南大客户经理',
    headline: '6 年大客户经营，现任客户成功高级经理，深圳，本科',
    recommendation: '建议进入复试', confidence: 0.89,
    highlights: [
      { text: '大客户续约做得扎实', quote: '负责华南区大客户续约，年续约率 92%，年合同额约 3,800 万元', ref: 'R3' },
      { text: '有 SaaS 落地与增购经验', quote: '主导 SaaS 产品在 3 家上市公司的落地', ref: 'R4' },
      { text: '能接受每月出差', quote: '每月出差一周没问题', ref: 'm-91' },
    ],
    risks: ['带团队规模较小（4 人）', '制造业客户经验不明确，复试可追问'],
    feedbacks: [
      { interviewer: '周振华', round: '第 1 轮', verdict: '推荐', summary: '对续约谈判的拆解很清楚，能直接带战略客户。' },
      { interviewer: '冯涛', round: '第 1 轮', verdict: '推荐', summary: '数据意识好，复盘有结构；管理经验需复试再看。' },
    ],
  },
};

export const portalSlots: Slot[] = [
  { id: 's1', start: daysFromNowAt(2, 14), end: daysFromNowAt(2, 15) },
  { id: 's2', start: daysFromNowAt(2, 16, 30), end: daysFromNowAt(2, 17, 30) },
  { id: 's3', start: daysFromNowAt(3, 10), end: daysFromNowAt(3, 11) },
  { id: 's4', start: daysFromNowAt(4, 15), end: daysFromNowAt(4, 16) },
];
