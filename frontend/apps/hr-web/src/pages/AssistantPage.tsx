import { usePageView } from '@recruiter/telemetry';
import { AssistantRail, Conversation } from '../features/assistant';
import { useMediaQuery } from '../shared/useMediaQuery';

/** AI 招聘助手：HR 端首页。大部分查询、AI 任务和日常操作都在这里用对话完成。 */
export function AssistantPage() {
  usePageView('AS-01');
  const wide = useMediaQuery('(min-width: 1200px)');
  return (
    <div className="as-page">
      <section className="as-page-main" aria-label="AI 招聘助手">
        <Conversation />
      </section>
      {wide && <AssistantRail />}
    </div>
  );
}
