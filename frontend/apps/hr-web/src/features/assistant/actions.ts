import { useCallback } from 'react';
import {
  useApi,
  type ApplicationCommand,
  type AssistantAction,
  type CandidateCommand,
  type ConversationCommand,
  type PositionCommand,
  type WriteOpts,
} from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';

export const STAGE: Record<string, string> = {
  reach: '触达',
  talking: '沟通中',
  ai_eval: 'AI 评估',
  interview: '面试',
  manager_eval: '用人经理评估',
  hired: '已录用',
};

export interface ActionExtras {
  reason: string;
  code?: ApplicationCommand['reason_code'];
  notify?: boolean;
}

/** 原因只对审计有意义的命令（候选人档案、会话归属）不要求填写 */
export const needsReason = (a: AssistantAction) =>
  a.kind !== 'message' &&
  !(a.kind === 'command' && (a.target === 'candidate' || a.target === 'conversation'));

/**
 * 执行助手给出的操作：调用和页面按钮完全相同的接口，权限、版本号、幂等和审计都不变；
 * 版本已变化时由接口拒绝。返回一句给 HR 看的结果。
 */
export function useRunAction() {
  const api = useApi();
  const session = useSession();
  return useCallback(
    async (a: AssistantAction, extra: ActionExtras, opts: WriteOpts): Promise<string> => {
      const { reason } = extra;
      switch (a.kind) {
        case 'attach': {
          const app = await api.attachCandidate(
            { candidate_id: a.candidate_id, position_id: a.position_id, source: 'hr', reason },
            opts,
          );
          return `已把${app.candidate_name ?? '候选人'}关联到“${app.position_name}”，当前阶段：触达。`;
        }
        case 'advance': {
          const app = await api.liveApplicationCommand(
            a.application_id,
            {
              action: 'advance',
              expected_version: a.expected_version,
              target_stage: a.target_stage as 'talking',
              reason,
            },
            opts,
          );
          return `已推进${app.candidate_name ?? ''}（${app.position_name}）到“${STAGE[app.stage ?? ''] ?? app.stage}”。`;
        }
        case 'reject': {
          const app = await api.liveApplicationCommand(
            a.application_id,
            {
              action: 'reject',
              expected_version: a.expected_version,
              reason,
              reason_code: extra.code,
              notify: extra.notify,
            },
            opts,
          );
          return `已淘汰${app.candidate_name ?? ''}（${app.position_name}）${extra.notify ? '，结果通知已排队' : ''}。`;
        }
        case 'message': {
          let conv = await api.liveConversation(a.candidate_id);
          if (conv.mode !== 'hr' || conv.owner_id !== session?.userId) {
            conv = (
              await api.conversationCommand(
                a.candidate_id,
                { action: 'take_over', expected_version: conv.version },
                { idempotencyKey: opts.idempotencyKey + '-take' },
              )
            ).conversation;
          }
          const result = await api.conversationCommand(
            a.candidate_id,
            {
              action: 'send',
              expected_version: conv.version,
              content: a.content,
              application_ids: a.application_ids,
            },
            { idempotencyKey: opts.idempotencyKey + '-send' },
          );
          const last = result.conversation.messages.at(-1);
          return last?.status === 'queued'
            ? '消息已排队，会在可联系时段发出。'
            : '消息已发送，会话已由你接管。';
        }
        case 'card':
          await api.resolveLiveCard(
            a.card_id,
            { expected_version: a.expected_version, option: a.option as 'dismiss', reason },
            opts,
          );
          return '决策卡已处理。';
        case 'command':
          switch (a.target) {
            case 'candidate': {
              const c = await api.candidateRecordCommand(
                a.id,
                a.body as unknown as CandidateCommand,
                opts,
              );
              return 'deleted' in c ? '候选人档案已更新。' : `已更新${c.profile.name}的档案。`;
            }
            case 'conversation':
              await api.conversationCommand(a.id, a.body as unknown as ConversationCommand, opts);
              return a.body.action === 'take_over'
                ? '已接管会话，AI 自动回复已暂停。'
                : '会话已交还给 AI。';
            case 'position': {
              const p = await api.positionCommand(
                a.id,
                { ...a.body, reason } as unknown as PositionCommand,
                opts,
              );
              return `“${p.name}”${a.body.action === 'pause' ? '已暂停招聘' : '已恢复招聘'}。`;
            }
            case 'application': {
              const app = await api.liveApplicationCommand(
                a.id,
                { ...a.body, reason } as unknown as ApplicationCommand,
                opts,
              );
              return `已撤销${app.candidate_name ?? ''}的淘汰，恢复到“${STAGE[app.stage ?? ''] ?? app.stage}”。`;
            }
          }
      }
    },
    [api, session?.userId],
  );
}
