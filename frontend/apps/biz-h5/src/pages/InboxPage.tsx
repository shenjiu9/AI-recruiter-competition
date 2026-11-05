import { NavBar, Skeleton, Popup } from 'antd-mobile';
import { useState } from 'react';
import { RequisitionNotices } from '@recruiter/ui-kit/requisition-notices';
import { RequisitionReview } from '../features/inbox/RequisitionReview';
import { usePageView } from '@recruiter/telemetry';
import { InboxList, useInbox } from '../features/inbox';

export function InboxPage() {
  usePageView('BZ-01');
  const { data, isLoading } = useInbox();
  const [noticeId, setNoticeId] = useState<string | null>(null);
  return (
    <main>
      <NavBar back={null}>招聘待办</NavBar>
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
