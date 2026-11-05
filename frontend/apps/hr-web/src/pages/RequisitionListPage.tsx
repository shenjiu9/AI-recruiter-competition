import { Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import { Can } from '@recruiter/permissions';
import { RequisitionTable, useRequisitionList } from '../features/requisition';
import { PageHeader } from '../shared/PageHeader';

export function RequisitionListPage() {
  const list = useRequisitionList();
  const nav = useNavigate();
  return (
    <div>
      <PageHeader
        title="招聘需求管理"
        sub="需求负责“申请招人”：发起、审批和留存依据。审批通过后生成或并入岗位。"
        extra={<Can perm="requisition.create"><Button type="primary" onClick={() => nav('/requisitions/new')}>发起招聘需求</Button></Can>}
      />
      <RequisitionTable rows={list.data ?? []} loading={list.isLoading} />
    </div>
  );
}
