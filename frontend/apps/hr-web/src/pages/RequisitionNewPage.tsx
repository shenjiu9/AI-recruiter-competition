import { Breadcrumb } from 'antd';
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { track, usePageView } from '@recruiter/telemetry';
import { RequisitionForm } from '../features/requisition';
import { PageHeader } from '../shared/PageHeader';

export function RequisitionNewPage() {
  usePageView('RQ-02');
  useEffect(() => track('rq_create_start', { entry: 'list' }), []);
  return (
    <div>
      <Breadcrumb style={{ marginBottom: 12 }} items={[{ title: <Link to="/requisitions">招聘需求管理</Link> }, { title: '发起招聘需求' }]} />
      <PageHeader title="发起招聘需求" sub="提交意味着用人部门对编制和成本负责，所以 AI 只起草，提交永远由人完成。" />
      <RequisitionForm />
    </div>
  );
}
