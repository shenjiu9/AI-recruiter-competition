// 只控制显示；真正的权限校验在后端接口层（PRD 20.3）
import type { ReactNode } from 'react';
import { useSession, type Role } from '@recruiter/auth';

export type Permission =
  | 'card.resolve'
  | 'card.batch'
  | 'conversation.take_over'
  | 'candidate.reveal_contact'
  | 'candidate.mark_key'
  | 'position.transition'
  | 'requisition.create'
  | 'requisition.approve'
  | 'settings.automation'
  | 'salary.internal';

const MATRIX: Record<Permission, Role[]> = {
  'card.resolve': ['recruiting_lead', 'recruiter', 'hiring_manager'],
  'card.batch': ['recruiting_lead', 'recruiter'],
  'conversation.take_over': ['recruiting_lead', 'recruiter'],
  'candidate.reveal_contact': ['recruiting_lead', 'recruiter'],
  'candidate.mark_key': ['recruiting_lead', 'recruiter'],
  'position.transition': ['recruiting_lead', 'recruiter'],
  'requisition.create': ['recruiting_lead', 'recruiter', 'hiring_manager', 'hrbp'],
  'requisition.approve': ['recruiting_lead', 'hiring_manager', 'hrbp'],
  'settings.automation': ['recruiting_lead', 'admin'],
  'salary.internal': ['recruiting_lead', 'recruiter', 'hiring_manager', 'hrbp'],
};

export function hasPermission(roles: Role[] | undefined, perm: Permission): boolean {
  return !!roles?.some((r) => MATRIX[perm].includes(r));
}

export function usePermission(perm: Permission): boolean {
  return hasPermission(useSession()?.roles, perm);
}

export function Can({ perm, children, fallback = null }: { perm: Permission; children: ReactNode; fallback?: ReactNode }) {
  return <>{usePermission(perm) ? children : fallback}</>;
}
