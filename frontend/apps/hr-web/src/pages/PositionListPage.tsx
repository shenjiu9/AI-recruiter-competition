import { LivePositionList, PositionTable, usePositionList } from '../features/position';
import { PageHeader } from '../shared/PageHeader';

export function PositionListPage() {
  return import.meta.env.VITE_USE_MOCK === 'false' ? <LivePositionList /> : <MockPositionList />;
}

function MockPositionList() {
  const list = usePositionList();
  return (
    <div>
      <PageHeader
        title="岗位管理"
        sub="岗位由审批通过的招聘需求自动生成；可招人数 = 已通过需求人数之和 − 已录用人数。"
      />
      <PositionTable rows={list.data ?? []} loading={list.isLoading} />
    </div>
  );
}
