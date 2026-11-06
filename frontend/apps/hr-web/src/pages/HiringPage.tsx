import { useParams, useSearchParams } from 'react-router-dom';
import { HiringDetail, HiringList } from '@recruiter/ui-kit/live-hiring';
export function HiringPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  return id ? <HiringDetail id={id} /> : <HiringList filters={Object.fromEntries(params)} />;
}
