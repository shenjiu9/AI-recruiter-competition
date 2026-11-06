import { Skeleton, Popup } from 'antd-mobile';
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
      <header className="rm-inbox-hero">
        <span className="eyebrow">TEAM WORKSPACE</span>
        <h1>招聘待办</h1>
        <p>把时间留给重要的判断，其他交给协作。</p>
      </header>
      {import.meta.env.VITE_USE_MOCK === 'false' && (
        <nav className="rm-inbox-shortcuts" aria-label="更多入口">
          <Link className="rm-shortcut" to="/positions">
            <span aria-hidden="true">01</span>岗位画像与关闭确认<small>对齐团队的人才需求</small>
          </Link>
          <Link className="rm-shortcut" to="/interviews">
            <span aria-hidden="true">02</span>我的面试与面评<small>记录每一次深入交流</small>
          </Link>
          <Link className="rm-shortcut" to="/workbench">
            <span aria-hidden="true">03</span>招聘工作台与决策卡<small>掌握进展，及时决策</small>
          </Link>
          <Link className="rm-shortcut" to="/hiring">
            <span aria-hidden="true">04</span>录用决定与审批<small>迎接新的团队伙伴</small>
          </Link>
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
