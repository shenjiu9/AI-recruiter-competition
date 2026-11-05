import { NavBar } from 'antd-mobile';
import { useNavigate, useParams } from 'react-router-dom';
import { FeedbackForm } from '../features/feedback';

export function FeedbackPage() {
  const { appId = '' } = useParams();
  const nav = useNavigate();
  return (
    <main>
      <NavBar onBack={() => nav('/')}>写面评</NavBar>
      <FeedbackForm appId={appId} onDone={() => nav('/')} />
    </main>
  );
}
