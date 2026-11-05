// 文案集中管理；首期简体中文，结构支持扩展英文（PRD 20.6）
const zhCN = {
  'app.name': 'AI 招聘官',
  'common.retry': '重试',
  'common.back': '返回',
  'common.loading': '正在加载',
  'error.network': '网络连接失败。请检查网络后点“重试”。',
  'error.conflict.title': '已被其他人修改',
  'banner.aiDegraded': 'AI 服务暂时不可用。所有操作都可以手动完成，候选人的消息已转给 HR。',
} as const;

export type MessageKey = keyof typeof zhCN;
const dicts: Record<string, Partial<Record<MessageKey, string>>> = { 'zh-CN': zhCN };
let locale = 'zh-CN';

export const setLocale = (l: string) => {
  locale = l;
};

export function t(key: MessageKey, vars?: Record<string, string | number>): string {
  let s = dicts[locale]?.[key] ?? zhCN[key];
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
  return s;
}
