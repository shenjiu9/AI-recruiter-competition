import { Alert, Button } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Can } from '@recruiter/permissions';
import { RequisitionTable, useRequisitionList } from '../features/requisition';
import { PageHeader } from '../shared/PageHeader';

export function RequisitionListPage() {
  const [page, setPage] = useState(1);
  const list = useRequisitionList(page);
  const nav = useNavigate();
  return (
    <div>
      <PageHeader
        title="招聘需求管理"
        sub="需求负责“申请招人”：发起、审批和留存依据。审批通过后生成或并入岗位。"
        extra={
          <Can perm="requisition.create">
            <Button type="primary" onClick={() => nav('/requisitions/new')}>
              发起招聘需求
            </Button>
          </Can>
        }
      />
      {list.isError && (
        <Alert
          type="error"
          message={list.error.message}
          action={<Button onClick={() => void list.refetch()}>重试</Button>}
        />
      )}
      <RequisitionTable
        rows={list.data?.items ?? []}
        loading={list.isLoading}
        page={page}
        total={list.data?.total ?? 0}
        onPageChange={setPage}
      />
    </div>
  );
}
