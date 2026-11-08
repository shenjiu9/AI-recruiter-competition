import {
  Alert,
  Button,
  Card,
  Descriptions,
  Input,
  Modal,
  Space,
  Spin,
  Steps,
  Timeline,
} from 'antd';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useSession } from '@recruiter/auth';
import { confirmationFieldLabel } from '@recruiter/api-client';
import { ApprovalTransfer, TRANSFER_ACTIONS } from '@recruiter/ui-kit';
import { ManagerConfirmation } from '../features/requisition/ui/ManagerConfirmation';
import { REQ_STATUS_LABEL } from '@recruiter/domain';
import { useRequisitionAction, useRequisitionDetail } from '../features/requisition';
import { PageHeader } from '../shared/PageHeader';
import { PositionGenerationPanel } from '../features/position';

export function RequisitionDetailPage() {
  const { id = '' } = useParams();
  const query = useRequisitionDetail(id);
  const qc = useQueryClient();
  const action = useRequisitionAction(query.data);
  const session = useSession();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [transferring, setTransferring] = useState(false);
  if (query.isPending) return <Spin />;
  if (!query.data) return <Alert type="error" message={query.error?.message ?? '需求不存在'} />;
  const req = query.data;
  const owner = session?.userId === req.ownerId || session?.userId === req.managerId;
  const current = req.chain[req.currentNode];
  const approver =
    req.status === 'in_approval' && !!current && current.approver_id === session?.userId;
  const upcoming = req.chain
    .slice(req.currentNode + 1)
    .find((node) => node.approver_id === session?.userId);
  const approvalMessage =
    req.status === 'in_approval'
      ? approver
        ? '轮到你审批了'
        : current
          ? `等待${current.approver}处理 · ${current.name}`
          : '暂时无法确认当前审批人'
      : {
          draft: '需求尚未提交',
          approved: '审批流程已完成',
          rejected: '本次审批已结束，等待修改后重新提交',
          withdrawn: '申请已撤回，等待重新提交',
        }[req.status];
  const approvalDescription =
    req.status === 'in_approval'
      ? approver
        ? `请核对下方需求信息，再选择通过、驳回或转交。当前节点：${current.name}。`
        : !current
          ? '请刷新进度；如果仍无法显示，请联系管理员检查审批配置。'
          : upcoming
            ? `当前登录：${session?.name ?? '未登录'}。尚未轮到你的「${upcoming.name}」节点；前序审批通过后，这里的按钮会开放。`
            : `当前登录：${session?.name ?? '未登录'}。此节点由指定审批人处理，同一角色的其他账号也不能代为审批。你可以查看进度和处理记录。`
      : {
          draft: '提交后才会开始审批，请由需求发起人或用人经理完善并提交。',
          approved: '无需再次审批，可查看下方生成的岗位和处理记录。',
          rejected: '请查看处理记录中的驳回原因，由需求发起人或用人经理修改后重新提交。',
          withdrawn: '当前没有待处理的审批，可由需求发起人或用人经理编辑后重新提交。',
        }[req.status];
  const approvalDisabled = !approver || action.isPending || query.isFetching || query.isError;
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
            {session?.userId === (req.ownerId || req.creatorId) && req.status === 'in_approval' && (
              <Button
                loading={action.isPending}
                onClick={() => action.mutate({ action: 'withdraw' })}
              >
                撤回需求
              </Button>
            )}
          </Space>
        }
      />
      <section aria-label="审批处理" style={{ marginBottom: 24 }}>
        <Card
          title="审批处理"
          extra={
            <Button loading={query.isFetching} onClick={() => void query.refetch()}>
              刷新进度
            </Button>
          }
        >
          <div aria-live="polite">
            <Alert
              showIcon
              type={req.status === 'approved' ? 'success' : 'info'}
              message={approvalMessage}
              description={<div id="approval-explanation">{approvalDescription}</div>}
              style={{ marginBottom: 16 }}
            />
            {query.isError && <Alert type="error" message="进度刷新失败，请刷新成功后再审批。" />}
          </div>
          <Space wrap>
            <Button
              type="primary"
              disabled={approvalDisabled}
              loading={action.isPending}
              aria-describedby="approval-explanation"
              onClick={() => action.mutate({ action: 'approve' })}
            >
              通过审批
            </Button>
            <Button
              danger
              disabled={approvalDisabled}
              aria-describedby="approval-explanation"
              onClick={() => setRejecting(true)}
            >
              驳回需求
            </Button>
            <Button
              disabled={approvalDisabled}
              aria-describedby="approval-explanation"
              onClick={() => setTransferring(true)}
            >
              转交审批
            </Button>
            {req.status === 'in_approval' && current?.id === 'manager' && (
              <Button
                disabled={approvalDisabled}
                aria-describedby="approval-explanation"
                onClick={() => setConfirming(true)}
              >
                修改并确认
              </Button>
            )}
          </Space>
        </Card>
      </section>
      {req.status === 'approved' && (
        <Alert
          style={{ marginBottom: 20 }}
          type="success"
          message="需求审批已通过"
          description={<PositionGenerationPanel reqId={req.id} />}
        />
      )}
      {req.status === 'in_approval' && req.chain[req.currentNode]?.id === 'hc_final' && (
        <Alert
          style={{ marginBottom: 20 }}
          type="warning"
          showIcon
          message="终审编制复核中"
          description={
            <>
              <p>
                这不是表单填写错误。申请增编只是提出增加名额，不会自动增加年度编制；审批通过前还需确认实际可用名额。
              </p>
              <p>
                请编制负责人到「编制管理」核对 {req.dept}{' '}
                的本年度计划、已占用名额、生效日期与冻结状态，补足名额后返回这里再次审批。
              </p>
              <Link to="/settings/headcount">前往编制管理</Link>
            </>
          }
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
          .filter(([key]) => !['confidential', 'visibleTo', 'reportToId'].includes(key))
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
          children: (
            <div>
              {ACTIONS[item.action] ?? item.action} · {new Date(item.at).toLocaleString()}
              {item.comment ? ` · ${item.comment}` : ''}
              {item.to_id && (
                <p>
                  {item.from_name ?? item.from_id} → {item.to_name ?? item.to_id}
                </p>
              )}
              {Object.entries(item.changes ?? {}).map(([key, value]) => (
                <p key={key}>
                  {confirmationFieldLabel(key)}：{value.before || '空'} → {value.after || '空'}
                </p>
              ))}
            </div>
          ),
        }))}
      />
      <Modal
        title="转交审批"
        open={transferring}
        footer={null}
        destroyOnClose
        onCancel={() => {
          setTransferring(false);
          void query.refetch();
        }}
      >
        <ApprovalTransfer
          req={req}
          onSuccess={() => {
            setTransferring(false);
            void qc.invalidateQueries({ queryKey: ['requisition'] });
          }}
        />
      </Modal>
      <Modal
        title="用人经理确认"
        open={confirming}
        footer={null}
        destroyOnClose
        onCancel={() => {
          setConfirming(false);
          void query.refetch();
        }}
      >
        <ManagerConfirmation
          req={req}
          onSuccess={() => {
            setConfirming(false);
            void qc.invalidateQueries({ queryKey: ['requisition'] });
          }}
        />
      </Modal>
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
  ...TRANSFER_ACTIONS,
  submitted: '提交审批',
  approved: '节点通过',
  rejected: '驳回',
  withdrawn: '撤回',
  hc_review_added: '加签编制负责人',
  manager_confirmed: '用人经理确认',
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
