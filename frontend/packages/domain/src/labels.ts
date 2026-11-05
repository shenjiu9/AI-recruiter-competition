import type { CardType, EndResult, FieldSource, HealthLevel, Level, Stage } from './types';

export const STAGES: Stage[] = ['reach', 'talking', 'ai_eval', 'interview', 'manager_eval', 'hired'];

const STAGE_LABEL: Record<Stage, string> = {
  reach: 'AI 触达',
  talking: '沟通中',
  ai_eval: 'AI 评估',
  interview: '面试',
  manager_eval: '用人部门评估',
  hired: '已录用',
};
export const stageLabel = (s: Stage): string => STAGE_LABEL[s];

const END_LABEL: Record<EndResult, string> = {
  rejected: '已淘汰',
  withdrawn: '候选人放弃',
  offer_declined: '未接受 Offer',
  no_show_onboard: '未入职',
  position_closed: '岗位关闭终止',
};
export const endResultLabel = (r: EndResult): string => END_LABEL[r];

const LEVEL_LABEL: Record<Level, string> = { 1: 'L1 只建议', 2: 'L2 需确认', 3: 'L3 已自动执行' };
export const levelLabel = (l: Level): string => LEVEL_LABEL[l];

const SOURCE_LABEL: Record<FieldSource, string> = {
  description: '你的描述',
  directory: '飞书通讯录',
  headcount: '编制表',
  history: '参考历史需求',
  salary_table: '职级薪资表',
  ai: 'AI 生成',
  default: '默认值',
  edited: '已修改',
};
export const sourceLabel = (s: FieldSource): string => SOURCE_LABEL[s];

const CARD_LABEL: Record<CardType, string> = {
  screen_result: '筛选结论确认',
  reject_confirm: '淘汰确认',
  salary_over: '薪资超区间',
  schedule_conflict: '约面冲突',
  possible_duplicate: '疑似重复',
  suggest_attach: '建议挂人',
  suggest_close: '建议关闭岗位',
  profile_pending: '画像待完善',
  proxy_pending: '代发起待确认',
  multi_hire: '多岗位录用',
};
export const cardTypeLabel = (t: CardType): string => CARD_LABEL[t];

const HEALTH_LABEL: Record<HealthLevel, string> = { risk: '风险', watch: '关注', ok: '正常' };
export const healthLabel = (h: HealthLevel): string => HEALTH_LABEL[h];

export const POSITION_STATUS_LABEL = {
  to_publish: '待发布',
  open: '招聘中',
  paused: '已暂停',
  closed: '已关闭',
} as const;

export const REQ_STATUS_LABEL = {
  draft: '草稿',
  in_approval: '审批中',
  approved: '已通过',
  rejected: '已驳回',
  withdrawn: '已撤回',
} as const;

export const REQ_TYPE_LABEL = { new: '新增', replace: '替补', additional: '追加' } as const;

export const INTERVIEW_STATUS_LABEL = {
  to_schedule: '待约',
  scheduling: '约面中',
  confirmed: '已确定',
  in_progress: '进行中',
  to_feedback: '待面评',
  done: '已完成',
  cancelled: '已取消',
} as const;

export const CONCLUSION_LABEL = {
  advance: '建议进入面试',
  reject: '建议淘汰',
  need_info: '信息不足，需要补问',
  hold: '建议推进，但命中不合适信号',
} as const;

export const REJECT_REASONS = ['评估不准', '信息不全', '业务有特殊要求', '其他'] as const;
