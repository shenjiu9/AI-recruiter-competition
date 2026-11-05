import { NavBar } from 'antd-mobile';
import { useNavigate, useParams } from 'react-router-dom';
import { usePageView } from '@recruiter/telemetry';
import { BriefView } from '../features/brief';

export function BriefPage() {
  usePageView('BZ-02');
  const { appId = '' } = useParams();
  const nav = useNavigate();
  return (
    <main>
      <NavBar onBack={() => nav('/')}>候选人推荐</NavBar>
      <BriefView appId={appId} onDone={() => nav('/')} />
    </main>
  );
}
