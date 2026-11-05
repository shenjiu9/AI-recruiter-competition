import { useQuery } from '@tanstack/react-query';
import { useApi } from '@recruiter/api-client';
import { qk } from '@recruiter/domain';

export function useInterviewList() {
  const api = useApi();
  return useQuery({ queryKey: qk.interview.list(), queryFn: () => api.listInterviews() });
}
