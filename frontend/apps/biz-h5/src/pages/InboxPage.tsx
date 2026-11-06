import { NavBar, Skeleton, Popup } from 'antd-mobile';
import { useState } from 'react';
import { RequisitionNotices } from '@recruiter/ui-kit/requisition-notices';
import { RequisitionReview } from '../features/inbox/RequisitionReview';
import { usePageView } from '@recruiter/telemetry';
import { InboxList, useInbox } from '../features/inbox';
import { Link } from 'react-router-dom';

export function InboxPage() {
  usePageView('BZ-01');
  const { data, isLoading } = useInbox();
  const [noticeId, setNoticeId] = useState<string | null>(null);
  return (
    <main>
      <NavBar back={null}>招聘待办</NavBar>
      {import.meta.env.VITE_USE_MOCK === 'false' && (
        <nav className="rm-quick" aria-label="更多入口">
          <Link to="/positions">岗位画像与关闭确认</Link>
          <Link to="/interviews">我的面试与面评</Link>
          <Link to="/workbench">招聘工作台与决策卡</Link>
          <Link to="/hiring">录用决定与审批</Link>
        </nav>
      )}
      <RequisitionNotices onOpen={setNoticeId} />
      <Popup
        visible={noticeId !== null}
        onMaskClick={() => setNoticeId(null)}
        bodyStyle={{ maxHeight: '90vh', overflowY: 'auto' }}
      >
        {noticeId && <RequisitionReview id={noticeId} onClose={() => setNoticeId(null)} />}
      </Popup>
      {isLoading ? (
        <div className="rm-card">
          <Skeleton.Paragraph lineCount={4} animated />
        </div>
      ) : (
        <InboxList items={data ?? []} />
      )}
    </main>
  );
}
