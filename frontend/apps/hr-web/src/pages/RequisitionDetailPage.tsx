import { Alert, Button, Descriptions, Input, Modal, Space, Spin, Steps, Timeline } from 'antd';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useSession } from '@recruiter/auth';
import { REQ_STATUS_LABEL } from '@recruiter/domain';
import { useRequisitionAction, useRequisitionDetail } from '../features/requisition';
import { PageHeader } from '../shared/PageHeader';

export function RequisitionDetailPage() {
  const { id = '' } = useParams();
  const query = useRequisitionDetail(id);
  const action = useRequisitionAction(query.data);
  const session = useSession();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  if (query.isPending) return <Spin />;
  if (!query.data) return <Alert type="error" message={query.error?.message ?? '需求不存在'} />;
  const req = query.data;
  const owner = session?.userId === req.creatorId || session?.userId === req.managerId;
  const approver =
    req.status === 'in_approval' && req.chain[req.currentNode]?.approver_id === session?.userId;
  return (
    <div>
      <Link to="/requisitions">返回招聘需求</Link>
      <PageHeader
        title={req.title}
        sub={`${req.no} · ${REQ_STATUS_LABEL[req.status]}`}
        extra={
          <Space>
            {owner && ['draft', 'rejected', 'withdrawn'].includes(req.status) && (
              <Link to={`/requisitions/${req.id}/edit`}>
                <Button type="primary">编辑需求</Button>
              </Link>
            )}
            {owner && req.status === 'in_approval' && (
              <Button
                loading={action.isPending}
                onClick={() => action.mutate({ action: 'withdraw' })}
              >
                撤回需求
              </Button>
            )}
            {approver && (
              <>
                <Button
                  type="primary"
                  loading={action.isPending}
                  onClick={() => action.mutate({ action: 'approve' })}
                >
                  通过审批
                </Button>
                <Button danger disabled={action.isPending} onClick={() => setRejecting(true)}>
                  驳回需求
                </Button>
              </>
            )}
          </Space>
        }
      />
      {req.status === 'approved' && (
        <Alert
          style={{ marginBottom: 20 }}
          type="success"
          message="需求审批已通过"
          description="岗位尚未生成，请在岗位创建完成后继续招聘。"
        />
      )}
      {req.status === 'in_approval' && req.chain[req.currentNode]?.id === 'hc_final' && (
        <Alert
          style={{ marginBottom: 20 }}
          type="warning"
          showIcon
          message="终审编制复核中"
          description="名额不足、冻结或未生效，尚未预占招聘名额。请编制负责人维护编制后，再通过此节点。"
        />
      )}
      {!!req.chain.length && (
        <Steps
          style={{ marginBottom: 24 }}
          current={req.currentNode}
          status={req.status === 'rejected' ? 'error' : 'process'}
          items={req.chain.map((node) => ({
            title: node.name,
            description: `${node.approver}${node.note ? ` · ${node.note}` : ''}`,
          }))}
        />
      )}
      <Descriptions
        bordered
        column={2}
        items={Object.entries(req.fields)
          .filter(([key]) => key !== 'confidential' && key !== 'visibleTo')
          .map(([key, value]) => ({
            key,
            label: FIELD_LABELS[key] ?? key,
            children: value || '—',
          }))}
      />
      <h2 style={{ marginTop: 24 }}>处理记录</h2>
      <Timeline
        items={req.history.map((item, i) => ({
          key: i,
          children: `${ACTIONS[item.action] ?? item.action} · ${new Date(item.at).toLocaleString()}${item.comment ? ` · ${item.comment}` : ''}`,
        }))}
      />
      <Modal
        title="驳回需求"
        open={rejecting}
        okText="确认驳回"
        cancelText="返回"
        confirmLoading={action.isPending}
        okButtonProps={{ disabled: !reason.trim() }}
        onCancel={() => setRejecting(false)}
        onOk={() =>
          action.mutate(
            { action: 'reject', reason },
            {
              onSuccess: () => {
                setRejecting(false);
                setReason('');
              },
            },
          )
        }
      >
        <label htmlFor="reject-reason">驳回原因</label>
        <Input.TextArea
          id="reject-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={1000}
        />
      </Modal>
    </div>
  );
}

const ACTIONS: Record<string, string> = {
  submitted: '提交审批',
  approved: '节点通过',
  rejected: '驳回',
  withdrawn: '撤回',
  hc_review_added: '加签编制负责人',
};
const FIELD_LABELS: Record<string, string> = {
  title: '职位名称',
  dept: '需求部门',
  recruitType: '招聘类型',
  employmentType: '用工类型',
  reqType: '需求类型',
  headcount: '招聘人数',
  series: '职位序列',
  level: '职级范围',
  city: '工作地点',
  reportTo: '汇报对象',
  expectedOnboard: '期望到岗',
  salary: '薪资带宽',
  reason: '招聘原因',
  duties: '岗位职责',
  requirements: '任职资格',
  hcRequest: '申请增编人数',
  replacementIds: '被替补人',
};
