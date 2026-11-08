import { useParams } from 'react-router-dom';
import { HiringDetail, HiringList, LiveWorkbench } from '@recruiter/ui-kit/live-hiring';
export function HiringPage() {
  const { id } = useParams();
  return id ? <HiringDetail id={id} /> : <HiringList />;
}
export function WorkbenchPage() {
  return <LiveWorkbench business />;
}
