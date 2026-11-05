import { Alert, Spin } from 'antd';
import { Link, useParams } from 'react-router-dom';
import { RequisitionForm, useRequisitionDetail } from '../features/requisition';
import { PageHeader } from '../shared/PageHeader';

export function RequisitionEditPage() {
  const { id = '' } = useParams();
  const query = useRequisitionDetail(id);
  if (query.isPending) return <Spin />;
  if (!query.data) return <Alert type="error" message={query.error?.message ?? '需求不存在'} />;
  if (!['draft', 'rejected', 'withdrawn'].includes(query.data.status))
    return <Alert type="warning" message="当前状态不能编辑，请返回详情查看。" />;
  return (
    <div>
      <Link to={`/requisitions/${id}`}>返回详情</Link>
      <PageHeader title="编辑招聘需求" sub="修改后可保存草稿，或重新提交审批。" />
      <RequisitionForm key={`${id}-${query.data.version}`} initial={query.data} />
    </div>
  );
}
