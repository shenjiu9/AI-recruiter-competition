import { Input } from 'antd';
import { useSearchParams } from 'react-router-dom';
import { CandidateTable, useCandidateList } from '../features/candidate';
import { PageHeader } from '../shared/PageHeader';
import { LiveCandidateList } from '../features/candidate/ui/LiveCandidates';

export function CandidateListPage() {
  return import.meta.env.VITE_USE_MOCK === 'false' ? <LiveCandidateList /> : <MockCandidateList />;
}

function MockCandidateList() {
  const [params, setParams] = useSearchParams();
  const q = params.get('q') ?? undefined;
  const list = useCandidateList(q);
  return (
    <div>
      <PageHeader
        title="候选人"
        sub="全部候选人，包括当前与历史应聘。人才库中未挂岗位的人对全部正式 HR 可见。"
      />
      <Input.Search
        allowClear
        defaultValue={q}
        placeholder="按姓名、公司或标签搜索"
        style={{ maxWidth: 360, marginBottom: 16 }}
        onSearch={(v) => setParams(v ? { q: v } : {})}
        aria-label="搜索候选人"
      />
      <CandidateTable rows={list.data ?? []} loading={list.isLoading} />
    </div>
  );
}
