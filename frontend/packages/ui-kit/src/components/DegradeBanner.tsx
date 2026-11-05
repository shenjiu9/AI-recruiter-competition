import { WarningOutlined } from '@ant-design/icons';
import { t } from '@recruiter/i18n';

/** AI 不可用时的横幅：说明影响与人工兜底（PRD 17.14、20.2） */
export function DegradeBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="rc-banner" role="status">
      <WarningOutlined aria-hidden />
      {t('banner.aiDegraded')}
    </div>
  );
}
