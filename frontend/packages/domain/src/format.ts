import type { ConfidenceBand, SalaryRange } from './types';

/** 把握度分档：高 ≥ 0.85，中 0.6–0.85，低 < 0.6（PRD 5.3，阈值可配） */
export function confidenceBand(v: number, high = 0.85, low = 0.6): ConfidenceBand {
  if (v >= high) return 'high';
  if (v >= low) return 'mid';
  return 'low';
}

export const CONFIDENCE_LABEL: Record<ConfidenceBand, string> = { high: '把握高', mid: '把握中', low: '把握低' };

export function formatSalaryRange(r: SalaryRange): string {
  const months = r.months ? ` × ${r.months} 薪` : '';
  return `${r.low}–${r.high}${r.unit}${months}`;
}

/** 手机号脱敏：138****6721 */
export function maskPhone(phone: string): string {
  return phone.length >= 11 ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : phone;
}

const pad = (n: number) => String(n).padStart(2, '0');

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${pad(d.getMonth() + 1)}月${pad(d.getDate())}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const WEEKDAY = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
export function formatSlot(startIso: string, endIso: string): string {
  const s = new Date(startIso);
  const e = new Date(endIso);
  return `${s.getMonth() + 1}月${s.getDate()}日 ${WEEKDAY[s.getDay()]} ${pad(s.getHours())}:${pad(s.getMinutes())}–${pad(e.getHours())}:${pad(e.getMinutes())}`;
}

/** 时限描述：今天 18:00 / 明天 12:00 / 3 天后 / 已超时 */
export function formatDue(iso: string, now: Date = new Date()): { text: string; urgent: boolean; overdue: boolean } {
  const d = new Date(iso);
  const diffMs = d.getTime() - now.getTime();
  if (diffMs < 0) return { text: '已超时', urgent: true, overdue: true };
  const sameDay = d.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(now.getDate() + 1);
  if (sameDay) return { text: `今天 ${formatTime(iso)}`, urgent: true, overdue: false };
  if (d.toDateString() === tomorrow.toDateString()) return { text: `明天 ${formatTime(iso)}`, urgent: false, overdue: false };
  const days = Math.ceil(diffMs / 86_400_000);
  return { text: `${days} 天后`, urgent: false, overdue: false };
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const min = Math.round((now.getTime() - new Date(iso).getTime()) / 60_000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} 小时前`;
  return formatDate(iso);
}
