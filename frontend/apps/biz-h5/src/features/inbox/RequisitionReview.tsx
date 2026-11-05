import { Button, TextArea } from 'antd-mobile';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi, confirmationFieldLabel } from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { ManagerConfirmation } from './ManagerConfirmation';
import { qk } from '@recruiter/domain';
import { useWrite } from '../../shared/useWrite';

export function RequisitionReview({ id, onClose }: { id: string; onClose: () => void }) {
  const api = useApi();
  const session = useSession();
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ['biz', 'requisition', id],
    queryFn: () => api.getRequisition(id),
  });
  const [reason, setReason] = useState('');
  const reject = useWrite(
    async (text: string, opts) => {
      const req = detail.data;
      if (!req) throw new Error('需求尚未加载');
      return api.rejectRequisition(req.id, req.chain[req.currentNode]!.id, req.version, text, opts);
    },
    { invalidate: [qk.biz.inbox(), ['biz', 'requisition', id]], success: '已驳回' },
  );
  const req = detail.data;
  return (
    <section style={{ padding: 24 }}>
      <Button onClick={onClose}>关闭详情</Button>
      {detail.isError && <p role="alert">{detail.error.message}</p>}
      {req && (
        <>
          <h2>{req.title}</h2>
          {req.chain[req.currentNode]?.id === 'hc_final' && (
            <p role="alert">
              终审编制不足、冻结或未生效，尚未预占名额。请在 HR Web
              的编制管理中补足并解冻，再通过审批。
            </p>
          )}
          <p>
            {req.dept} · {req.headcount} 人
          </p>
          <p>招聘原因：{req.fields.reason}</p>
          <p>薪资带宽：{req.fields.salary}</p>
          <p>岗位职责：{req.fields.duties}</p>
          <p>任职资格：{req.fields.requirements}</p>
          {req.history
            .filter((item) => item.action === 'manager_confirmed')
            .map((item, index) => (
              <div key={index}>
                <h3>用人经理确认 · {new Date(item.at).toLocaleString()}</h3>
                {Object.entries(item.changes ?? {}).map(([key, value]) => (
                  <p key={key}>
                    {confirmationFieldLabel(key)}：{value.before || '空'} → {value.after || '空'}
                  </p>
                ))}
              </div>
            ))}
          {req.status === 'in_approval' &&
            req.chain[req.currentNode]?.id === 'manager' &&
            req.chain[req.currentNode]?.approver_id === session?.userId && (
              <ManagerConfirmation
                req={req}
                onSuccess={() => {
                  void qc.invalidateQueries({ queryKey: qk.biz.inbox() });
                  void qc.invalidateQueries({ queryKey: ['biz', 'requisition', id] });
                  onClose();
                }}
              />
            )}
          <label htmlFor="biz-reject-reason">驳回原因（必填）</label>
          <TextArea
            id="biz-reject-reason"
            value={reason}
            onChange={setReason}
            maxLength={1000}
            placeholder="说明需要调整的内容"
          />
          <Button
            block
            color="danger"
            disabled={!reason.trim() || reject.isPending}
            onClick={() => reject.mutate(reason, { onSuccess: onClose })}
          >
            确认驳回
          </Button>
        </>
      )}
    </section>
  );
}
