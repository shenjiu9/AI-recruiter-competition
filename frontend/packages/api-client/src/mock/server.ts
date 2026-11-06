// 内存 mock：行为对齐后端契约——乐观锁（VERSION_CONFLICT）、幂等键、AI 身份降级等，便于前端在没有后端时完整演示。
import type {
  ApprovalNode,
  Conversation,
  Message,
  PrecheckItem,
  RequisitionDraft,
} from '@recruiter/domain';
import type { ApiClient, PortalSession, WriteOpts } from '../client';
import { AppError } from '../errors';
import * as db from './data';

const clone = <T>(v: T): T => structuredClone(v);
const wait = (ms = 250 + Math.random() * 250) => new Promise((r) => setTimeout(r, ms));
const idem = new Map<string, unknown>();

async function write<T>(opts: WriteOpts, fn: () => T | Promise<T>): Promise<T> {
  await wait();
  if (idem.has(opts.idempotencyKey)) return clone(idem.get(opts.idempotencyKey) as T);
  const result = await fn();
  idem.set(opts.idempotencyKey, result);
  return clone(result);
}

function must<T>(v: T | undefined, what: string): T {
  if (v === undefined) throw new AppError('NOT_FOUND', `${what}不存在或不在你的数据范围内`, 404);
  return v;
}

const portal: { session: PortalSession; messages: Message[] } = {
  session: {
    candidateName: '陈佳怡',
    companyName: '星汇科技',
    positionName: '华南大客户经理',
    consent: 'none',
    progress: '面试中：第 1 轮已完成，正在安排复试',
  },
  messages: [
    {
      id: 'p1',
      sender: 'ai',
      text: '陈佳怡您好，我是星汇科技的 AI 招聘助手。第 1 轮面试已经完成，面试官希望和您约第 2 轮复试。下面是可以选的时间，选一个最方便的就行。',
      at: db.hoursFromNow(-0.2),
    },
  ],
};

let seq = 1000;
const nextId = (p: string) => `${p}-${++seq}`;

export function createMockClient(): ApiClient {
  const backendOnly = async (): Promise<never> => {
    throw new AppError('BACKEND_REQUIRED', '此操作需要切换到真实 API 模式', 501);
  };
  return {
    candidatePage: backendOnly,
    liveInterviews: backendOnly,
    liveInterview: backendOnly,
    interviewCommand: backendOnly,
    interviewAvailability: backendOnly,
    saveInterviewAvailability: backendOnly,
    candidateInterviews: backendOnly,
    candidateInterviewCommand: backendOnly,
    liveConversation: backendOnly,
    conversationCommand: backendOnly,
    livePortal: backendOnly,
    livePortalCommand: backendOnly,
    candidateRecord: backendOnly,
    createCandidateRecord: backendOnly,
    candidateRecordCommand: backendOnly,
    revealCandidateContacts: backendOnly,
    uploadCandidateResume: backendOnly,
    downloadCandidateResume: backendOnly,
    attachCandidate: backendOnly,
    livePositionApplications: backendOnly,
    liveApplicationCommand: backendOnly,
    positionPage: backendOnly,
    positionKnowledgePreview: backendOnly,
    positionDetail: backendOnly,
    positionCommand: backendOnly,
    positionGeneration: backendOnly,
    resolvePositionGeneration: backendOnly,
    formDepartments: backendOnly,
    formUsers: backendOnly,
    salaryBands: backendOnly,
    salaryHistory: backendOnly,
    saveSalaryBand: backendOnly,
    headcountPlans: backendOnly,
    saveHeadcount: backendOnly,
    async requisitionPage(page, size) {
      return {
        items: clone(db.requisitions.slice((page - 1) * size, page * size)),
        total: db.requisitions.length,
        page,
        size,
      };
    },
    getRequisition: backendOnly,
    transferCandidates: backendOnly,
    transferRequisition: backendOnly,
    requisitionNotifications: async () => [],
    createRequisitionDraft: backendOnly,
    updateRequisitionDraft: backendOnly,
    submitRequisitionDraft: backendOnly,
    withdrawRequisition: backendOnly,
    approveRequisition: backendOnly,
    organizationDepartments: backendOnly,
    organizationUsers: backendOnly,
    savePermissions: backendOnly,
    saveApprovalPolicy: backendOnly,
    organizationHistory: backendOnly,
    trialApproval: backendOnly,
    previewConfirmation: backendOnly,
    confirmRequisition: backendOnly,
    rejectRequisition: backendOnly,
    async workbenchSummary() {
      await wait(150);
      const open = db.cards.filter((c) => c.state === 'open');
      const today = new Date().toDateString();
      return {
        userName: '林悦',
        pendingDecisions: open.length,
        dueToday: open.filter((c) => new Date(c.dueAt).toDateString() === today).length,
        handoffs: db.handoffs.length,
        aiActionsToday: 128,
        hiredThisWeek: 2,
        aiDegraded: new URLSearchParams(globalThis.location?.search ?? '').get('degraded') === '1',
      };
    },
    async listOpenCards() {
      await wait(200);
      return clone(
        db.cards.filter((c) => c.state !== 'done').sort((a, b) => a.dueAt.localeCompare(b.dueAt)),
      );
    },
    resolveCard(id, body, opts) {
      return write(opts, () => {
        const card = must(
          db.cards.find((c) => c.id === id),
          '决策卡',
        );
        if (card.state === 'void')
          throw new AppError(
            'CARD_INVALIDATED',
            card.voidReason ?? '情况已变化，这张卡已失效',
            409,
          );
        if (card.version !== body.expectedVersion)
          throw new AppError('VERSION_CONFLICT', '这张卡已被其他人处理或已更新', 409, {
            current: clone(card),
          });
        const opt = must(
          card.options.find((o) => o.key === body.option),
          '选项',
        );
        card.state = 'done';
        card.version += 1;
        card.resolvedNote = body.selected ? `${opt.label}：${body.selected.length} 人` : opt.label;
        return card;
      });
    },
    batchResolve(ids, option, opts) {
      return write(opts, () =>
        ids.map((id) => {
          const card = must(
            db.cards.find((c) => c.id === id),
            '决策卡',
          );
          card.state = 'done';
          card.version += 1;
          card.resolvedNote = card.options.find((o) => o.key === option)?.label ?? option;
          return card;
        }),
      );
    },
    async aiActivity() {
      await wait(150);
      return clone(db.activity);
    },
    undoAction(actionId, opts) {
      return write(opts, () => {
        const a = must(
          db.activity.find((x) => x.actionId === actionId),
          'AI 动作',
        );
        if (!a.reversible)
          throw new AppError('NOT_REVERSIBLE', '已发出的消息无法撤销，可以选择“纠正”', 422);
        a.undone = true;
        return a;
      });
    },
    correctAction(actionId, _note, opts) {
      return write(opts, () => {
        const a = must(
          db.activity.find((x) => x.actionId === actionId),
          'AI 动作',
        );
        a.corrected = true;
        return a;
      });
    },
    async positionHealth() {
      await wait(150);
      return clone(db.health);
    },
    async handoffs() {
      await wait(150);
      return clone(db.handoffs);
    },
    async anomalies() {
      await wait(150);
      return clone(db.anomalies);
    },

    async listCandidates(q) {
      await wait();
      const list = db.candidates
        .filter(
          (c) =>
            !q ||
            c.name.includes(q) ||
            c.currentCompany.includes(q) ||
            c.tags.some((t) => t.includes(q)),
        )
        .map((c) => ({
          ...c,
          latest: db.applications.find((a) => a.candidateId === c.id && !a.ended),
        }));
      return clone(list);
    },
    async getCandidate(id) {
      await wait();
      return clone(
        must(
          db.candidates.find((c) => c.id === id),
          '候选人',
        ),
      );
    },
    async listApplications(candidateId) {
      await wait();
      return clone(
        db.applications
          .filter((a) => a.candidateId === candidateId)
          .sort((a, b) => Number(!!a.ended) - Number(!!b.ended)),
      );
    },
    async getResume(candidateId) {
      await wait();
      return clone(must(db.resumes[candidateId], '简历'));
    },
    async getEvaluation(applicationId) {
      await wait();
      return clone(db.evaluations[applicationId] ?? null);
    },
    async getConversation(candidateId) {
      await wait();
      const conv: Conversation = db.conversations[candidateId] ?? {
        candidateId,
        mode: 'ai',
        messages: [],
      };
      return clone(conv);
    },
    async operationLogs(candidateId) {
      await wait();
      return clone(db.operationLogs[candidateId] ?? []);
    },
    takeOver(candidateId, opts) {
      return write(opts, () => {
        const conv = (db.conversations[candidateId] ??= { candidateId, mode: 'ai', messages: [] });
        conv.mode = 'taken_over';
        return conv;
      });
    },
    handBack(candidateId, opts) {
      return write(opts, () => {
        const conv = must(db.conversations[candidateId], '会话');
        conv.mode = 'ai';
        conv.messages = conv.messages.filter((m) => !m.draft);
        return conv;
      });
    },
    sendAsHr(candidateId, text, opts) {
      return write(opts, () => {
        const conv = must(db.conversations[candidateId], '会话');
        const msg: Message = {
          id: nextId('m'),
          sender: 'hr',
          senderName: '林悦',
          text,
          at: new Date().toISOString(),
          status: 'sent',
        };
        conv.messages = conv.messages.filter((m) => !m.draft).concat(msg);
        return msg;
      });
    },
    revealContact(candidateId, opts) {
      return write(opts, () => {
        must(
          db.candidates.find((c) => c.id === candidateId),
          '候选人',
        );
        return { phone: '13800136721', email: 'chenjiayi@163.com' };
      });
    },
    setKey(candidateId, isKey, expectedVersion, opts) {
      return write(opts, () => {
        const c = must(
          db.candidates.find((x) => x.id === candidateId),
          '候选人',
        );
        if (c.version !== expectedVersion)
          throw new AppError('VERSION_CONFLICT', '候选人信息已被其他人修改', 409, {
            current: clone(c),
          });
        c.isKey = isKey;
        c.version += 1;
        return c;
      });
    },

    async listPositions() {
      await wait();
      return clone(db.positions);
    },
    async getPosition(id) {
      await wait();
      return clone(
        must(
          db.positions.find((p) => p.id === id),
          '岗位',
        ),
      );
    },
    async positionFunnel(id) {
      await wait();
      const base: Record<string, number[]> = {
        'JOB-202611-0017': [86, 41, 23, 7, 2, 1],
        'JOB-202611-0009': [214, 96, 51, 4, 1, 1],
        'JOB-202610-0044': [38, 19, 9, 3, 0, 0],
        'JOB-202610-0021': [52, 27, 12, 5, 2, 1],
      };
      const reached = base[id] ?? [0, 0, 0, 0, 0, 0];
      const stages = ['reach', 'talking', 'ai_eval', 'interview', 'manager_eval', 'hired'] as const;
      return stages.map((stage, i) => ({
        stage,
        reached: reached[i] ?? 0,
        current: Math.round((reached[i] ?? 0) * 0.3),
      }));
    },
    async positionApplications(id) {
      await wait();
      return clone(
        db.applications
          .filter((a) => a.positionId === id)
          .map((a) => ({
            ...a,
            candidateName: db.candidates.find((c) => c.id === a.candidateId)?.name ?? '',
            confidence: db.evaluations[a.id]?.confidence,
          })),
      );
    },
    async getProfile(positionId) {
      await wait();
      return clone(db.profiles[positionId] ?? { positionId, version: 0, items: [] });
    },
    async listKb() {
      await wait();
      return clone(db.kb);
    },
    transitionPosition(id, action, expectedVersion, opts) {
      return write(opts, () => {
        const p = must(
          db.positions.find((x) => x.id === id),
          '岗位',
        );
        if (p.version !== expectedVersion)
          throw new AppError('VERSION_CONFLICT', '岗位已被其他人修改', 409, { current: clone(p) });
        p.status = action === 'pause' ? 'paused' : action === 'resume' ? 'open' : 'closed';
        p.version += 1;
        return p;
      });
    },

    async listRequisitions() {
      await wait();
      return clone(db.requisitions);
    },
    async aiFillRequisition(text) {
      await wait(900);
      const n = Number(/(\d+)\s*个/.exec(text)?.[1] ?? 3);
      const draft: RequisitionDraft = {
        fields: {
          recruitType: { value: '社招', source: 'default' },
          dept: { value: '客服中心', source: 'description', sourceDetail: '从“客服中心”识别' },
          employmentType: { value: '正式', source: 'default' },
          reqType: { value: '新增', source: 'ai', sourceDetail: '描述中没有提到替补或离职' },
          title: { value: '白班客服', source: 'description' },
          headcount: { value: String(n), source: 'description' },
          city: { value: '深圳', source: 'description' },
          level: { value: 'P3–P4', source: 'history', sourceDetail: '参考 REQ-202611-0031' },
          salary: {
            value: '7–9K × 13 薪',
            source: 'salary_table',
            sourceDetail: '职级薪资表 + 近 3 次录用',
          },
          expectedOnboard: {
            value: '12 月 15 日',
            source: 'description',
            sourceDetail: '从“12 月中”识别',
          },
          reportTo: { value: '', source: 'directory' },
          reason: {
            value: '双十二大促后咨询量预计上升 40%，现有白班 18 人排班不足。',
            source: 'ai',
          },
          duties: {
            value:
              '负责电商平台售前售后咨询，处理订单、物流与退换货问题；按排班完成在线与电话接待。',
            source: 'history',
            sourceDetail: '参考 REQ-202611-0031',
          },
          requirements: {
            value: '1 年以上客服经验；能接受早 8 点到晚 5 点白班排班；普通话流利。',
            source: 'history',
            sourceDetail: '参考 REQ-202611-0031',
          },
        },
        pending: [
          ...(n > 2
            ? [
                {
                  field: 'headcount',
                  question: `客服中心可用 HC 只有 2 个，你要招 ${n} 人。`,
                  options: ['按 2 人提交', `同时申请 ${n - 2} 个 HC（审批链加签编制负责人）`],
                },
              ]
            : []),
          {
            field: 'reportTo',
            question: '客服中心有两位客服主管，这个岗位汇报给谁？',
            options: ['何美玲', '田野'],
          },
        ],
      };
      return draft;
    },
    async precheckRequisition(fields) {
      await wait(300);
      const n = Number(fields.headcount ?? 0);
      const items: PrecheckItem[] = [
        {
          key: 'hc',
          label: '编制',
          status: n > 2 && !fields.hcRequest ? 'block' : n > 2 ? 'warn' : 'pass',
          detail:
            n > 2
              ? fields.hcRequest
                ? `超出的 ${n - 2} 个 HC 已加入申请，审批链会加签编制负责人`
                : `可用 HC 2 个，需求 ${n} 人`
              : '在可用 HC 内',
        },
        {
          key: 'salary',
          label: '薪资带宽',
          status: 'pass',
          detail: '7–9K 在 P3–P4 带宽内，近 3 次录用中位数 8K',
        },
        {
          key: 'jd',
          label: '歧视性表述',
          status: /男|女|已婚|未婚|岁以下/.test(fields.requirements ?? '') ? 'block' : 'pass',
          detail: /男|女|已婚|未婚|岁以下/.test(fields.requirements ?? '')
            ? '任职资格中有涉及性别、婚育或年龄的表述，请改写'
            : '未发现',
        },
        {
          key: 'onboard',
          label: '到岗时间',
          status: 'warn',
          detail: '同序列同城市近 3 次招满平均 26 天，需在 11 月 19 日前审批并发布',
        },
      ];
      return items;
    },
    async approvalChain(fields) {
      await wait(150);
      const chain: ApprovalNode[] = [
        { name: '部门负责人', approver: '何美玲' },
        { name: 'HRBP', approver: '方启明' },
      ];
      if (fields.hcRequest)
        chain.push({ name: '编制负责人', approver: '黄丽', note: '因申请新增 HC 加签' });
      return chain;
    },
    submitRequisition(fields, opts) {
      return write(opts, () => {
        const no = `REQ-202611-00${60 + db.requisitions.length}`;
        const req = {
          id: no,
          version: 1,
          no,
          title: fields.title ?? '未命名',
          dept: fields.dept ?? '',
          type: 'new' as const,
          headcount: Number(fields.headcount ?? 1),
          initiator: '林悦',
          mode: 'self' as const,
          status: 'in_approval' as const,
          waitingFor: '何美玲',
          waitingDays: 0,
          submittedAt: new Date().toISOString(),
        };
        db.requisitions.unshift(req);
        return req;
      });
    },

    async listInterviews() {
      await wait();
      return clone(db.interviews);
    },

    async automationNodes() {
      await wait();
      return clone(db.automation);
    },
    setAutomationLevel(key, level, opts) {
      return write(opts, () => {
        const n = must(
          db.automation.find((x) => x.key === key),
          '环节',
        );
        if (!n.allowed.includes(level))
          throw new AppError('RULE_VIOLATION', `${n.name}${n.cap ?? '不允许该等级'}`, 422);
        n.level = level;
        return n;
      });
    },

    async bizInbox() {
      await wait();
      return clone(db.bizInbox);
    },
    bizAct(itemId, action, opts) {
      return write(opts, () => {
        const item = must(
          db.bizInbox.find((x) => x.id === itemId),
          '待办',
        );
        item.done = action;
        return item;
      });
    },
    async candidateBrief(applicationId) {
      await wait();
      return clone(must(db.briefs[applicationId], '候选人'));
    },
    submitFeedback(_applicationId, _items, opts) {
      return write(opts, () => undefined);
    },

    async portalSession() {
      await wait(200);
      return clone(portal.session);
    },
    portalConsent(_token, granted, opts) {
      return write(opts, () => {
        portal.session.consent = granted ? 'granted' : 'none';
        return portal.session;
      });
    },
    async portalMessages() {
      await wait(150);
      return clone(portal.messages);
    },
    portalSend(_token, text, opts) {
      return write(opts, () => {
        const msg: Message = {
          id: nextId('p'),
          sender: 'candidate',
          text,
          at: new Date().toISOString(),
        };
        portal.messages.push(msg);
        setTimeout(() => {
          const human = /人工|真人/.test(text);
          portal.messages.push({
            id: nextId('p'),
            sender: 'ai',
            at: new Date().toISOString(),
            text: human
              ? '已为您转接招聘顾问，工作时间 2 小时内会回复您。'
              : /地址|地点|在哪/.test(text)
                ? '复试在深圳南山区科技园 B 座 12 楼，地铁 1 号线高新园站步行约 8 分钟。'
                : '收到，我确认后回复您。如果着急，可以点右上角“转人工”。',
          });
        }, 1200);
        return msg;
      });
    },
    portalAskHuman(_token, opts) {
      return write(opts, () => {
        const msg: Message = {
          id: nextId('p'),
          sender: 'ai',
          text: '已为您转接招聘顾问林悦，工作时间 2 小时内会回复您。在这之前我不会再自动回复。',
          at: new Date().toISOString(),
        };
        portal.messages.push(msg);
        return msg;
      });
    },
    async portalSlots() {
      await wait(200);
      return clone(db.portalSlots);
    },
    portalPickSlot(_token, slotId, opts) {
      return write(opts, () => {
        const slot = must(
          db.portalSlots.find((s) => s.id === slotId),
          '时段',
        );
        const d = new Date(slot.start);
        const msg: Message = {
          id: nextId('p'),
          sender: 'ai',
          at: new Date().toISOString(),
          text: `已为您确认复试：${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}，地点深圳南山区科技园 B 座 12 楼。前一天 18:00 我会再提醒您。`,
        };
        portal.messages.push(msg);
        portal.session.progress = '面试中：复试时间已确认';
        return msg;
      });
    },
  };
}
