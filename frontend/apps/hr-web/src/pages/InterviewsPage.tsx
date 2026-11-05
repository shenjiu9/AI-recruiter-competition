import { InterviewTable, useInterviewList } from '../features/interview';
import { PageHeader } from '../shared/PageHeader';

export function InterviewsPage() {
  const list = useInterviewList();
  return (
    <div>
      <PageHeader title="面试" sub="跨岗位的面试日程。约面、改期由 AI 处理；没有共同空闲时会生成约面冲突卡。" />
      <InterviewTable rows={list.data ?? []} loading={list.isLoading} />
    </div>
  );
}
