import { Button, Drawer, Skeleton, Tabs } from 'antd';
import { useState } from 'react';
import { LiveWorkbench } from '@recruiter/ui-kit/live-hiring';
import { usePageView } from '@recruiter/telemetry';
import {
  ActivityPanel,
  AnomalyList,
  BriefLine,
  DecisionQueue,
  HandoffList,
  HealthPanel,
  useWorkbench,
} from '../features/workbench';
import { useMediaQuery } from '../shared/useMediaQuery';

/** WB-01 HR 工作台：今天有什么必须我来定？AI 替我做了什么？哪些岗位要出问题？ */
export function WorkbenchPage() {
  return import.meta.env.VITE_USE_MOCK === 'false' ? <LiveWorkbench /> : <MockWorkbenchPage />;
}
function MockWorkbenchPage() {
  usePageView('WB-01');
  const { summary, cards, activity, health, handoffs, anomalies } = useWorkbench();
  const [tab, setTab] = useState('cards');
  const [railOpen, setRailOpen] = useState(false);
  const wide = useMediaQuery('(min-width: 1440px)');

  const rail = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {health.data ? <HealthPanel items={health.data} /> : <Skeleton active />}
      {activity.data ? <ActivityPanel items={activity.data} /> : <Skeleton active />}
    </div>
  );

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: wide ? 'minmax(0, 1fr) 320px' : 'minmax(0, 1fr)',
        gap: 24,
        alignItems: 'start',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div className="hr-brief-row" style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
          {summary.data ? (
            <BriefLine
              s={summary.data}
              onGo={(t) => {
                if (t === 'activity') {
                  if (wide)
                    document.getElementById('ai-activity')?.scrollIntoView({ behavior: 'smooth' });
                  else setRailOpen(true);
                } else setTab(t);
              }}
            />
          ) : (
            <Skeleton active paragraph={{ rows: 1 }} />
          )}
          {!wide && (
            <Button style={{ marginLeft: 'auto' }} onClick={() => setRailOpen(true)}>
              岗位健康与 AI 动态
            </Button>
          )}
        </div>
        <Tabs
          activeKey={tab}
          onChange={setTab}
          items={[
            {
              key: 'cards',
              label: (
                <>
                  待决策{' '}
                  <span className="num">
                    {cards.data?.filter((c) => c.state === 'open').length ?? ''}
                  </span>
                </>
              ),
              children: cards.data ? <DecisionQueue cards={cards.data} /> : <Skeleton active />,
            },
            {
              key: 'handoffs',
              label: (
                <>
                  转人工 <span className="num">{handoffs.data?.length ?? ''}</span>
                </>
              ),
              children: <HandoffList items={handoffs.data ?? []} />,
            },
            {
              key: 'anomalies',
              label: (
                <>
                  异常 <span className="num">{anomalies.data?.length ?? ''}</span>
                </>
              ),
              children: <AnomalyList items={anomalies.data ?? []} />,
            },
          ]}
        />
      </div>
      {wide ? (
        rail
      ) : (
        <Drawer
          title="岗位健康与 AI 动态"
          open={railOpen}
          onClose={() => setRailOpen(false)}
          width={380}
        >
          {rail}
        </Drawer>
      )}
    </div>
  );
}
