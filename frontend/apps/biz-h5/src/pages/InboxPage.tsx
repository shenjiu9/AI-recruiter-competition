import { NavBar, Skeleton } from 'antd-mobile';
import { usePageView } from '@recruiter/telemetry';
import { InboxList, useInbox } from '../features/inbox';

export function InboxPage() {
  usePageView('BZ-01');
  const { data, isLoading } = useInbox();
  return (
    <main>
      <NavBar back={null}>招聘待办</NavBar>
      {isLoading ? <div className="rm-card"><Skeleton.Paragraph lineCount={4} animated /></div> : <InboxList items={data ?? []} />}
    </main>
  );
}
