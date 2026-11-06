import { Alert } from 'antd';
import { AutomationTable, useAutomation } from '../features/settings';
import { PageHeader } from '../shared/PageHeader';
import { LiveAutomation } from '../features/settings/ui/LiveAutomation';

export function AutomationSettingsPage() {
  return import.meta.env.VITE_USE_MOCK === 'false' ? (
    <LiveAutomation />
  ) : (
    <MockAutomationSettingsPage />
  );
}
function MockAutomationSettingsPage() {
  const { nodes, setLevel } = useAutomation();
  return (
    <div>
      <PageHeader
        title="自动化策略"
        sub="L1 AI 只建议；L2 AI 准备好动作，等人确认；L3 AI 直接执行并留痕，事后抽检。"
      />
      <Alert
        style={{ marginBottom: 16, maxWidth: 880 }}
        type="info"
        showIcon
        message="硬性上限不能被任何配置突破"
        description="淘汰最高 L2，录用建议固定 L1；AI 把握低于 0.6、关键候选人、保密岗位的所有对外动作最高 L2。"
      />
      <AutomationTable
        rows={nodes.data ?? []}
        loading={nodes.isLoading}
        onChange={(key, level) => setLevel.mutate({ key, level })}
      />
    </div>
  );
}
