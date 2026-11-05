import { App, Breadcrumb, Button, Descriptions, Select, Skeleton, Space, Tabs } from 'antd';
import { Link, useParams } from 'react-router-dom';
import { POSITION_STATUS_LABEL, formatDate, formatSalaryRange } from '@recruiter/domain';
import { usePermission } from '@recruiter/permissions';
import { track, usePageView } from '@recruiter/telemetry';
import { EmptyState, HealthTag } from '@recruiter/ui-kit';
import {
  FunnelBar,
  KbPanel,
  PositionApplications,
  ProfilePanel,
  usePositionDetail,
  useTransitionPosition,
} from '../features/position';
import { PageHeader } from '../shared/PageHeader';

const CLOSE_REASONS = ['招满', '需求取消', '组织调整', '其他'];

/** JB-02 岗位详情 */
export function PositionDetailPage() {
  usePageView('JB-02');
  const { id = '' } = useParams();
  const d = usePositionDetail(id);
  const p = d.position.data;
  const transition = useTransitionPosition(p);
  const can = usePermission('position.transition');
  const { modal } = App.useApp();

  if (d.position.isLoading) return <Skeleton active />;
  if (!p)
    return (
      <EmptyState
        title="找不到这个岗位"
        why="可能已被删除，或不在你的数据范围内。"
        action={<Link to="/positions">回到岗位列表</Link>}
      />
    );

  const close = () => {
    let reason = '';
    modal.confirm({
      title: `关闭岗位“${p.name}”？`,
      content: (
        <div>
          <p>
            关闭后各渠道下线、停止主动触达。在途候选人会转为“岗位关闭终止”，用人部门评估及以后阶段的人需要逐一处理。
          </p>
          <Select
            style={{ width: '100%' }}
            placeholder="关闭原因（必填）"
            options={CLOSE_REASONS.map((r) => ({ value: r, label: r }))}
            onChange={(v: string) => (reason = v)}
          />
        </div>
      ),
      okText: '关闭岗位',
      okButtonProps: { danger: true },
      cancelText: '返回',
      onOk: () =>
        reason ? transition.mutateAsync('close') : Promise.reject(new Error('请选择关闭原因')),
    });
  };

  return (
    <div>
      <Breadcrumb
        style={{ marginBottom: 12 }}
        items={[{ title: <Link to="/positions">岗位管理</Link> }, { title: p.name }]}
      />
      <PageHeader
        title={
          <span style={{ display: 'inline-flex', gap: 12, alignItems: 'center' }}>
            {p.name}
            <span className="rc-tag">{POSITION_STATUS_LABEL[p.status]}</span>
            <HealthTag level={p.health} />
          </span>
        }
        sub={
          <span>
            {p.dept} {p.city} <span className="num">{p.id}</span>
          </span>
        }
        extra={
          can && p.status !== 'closed' ? (
            <Space>
              {p.status === 'open' && (
                <Button onClick={() => transition.mutate('pause')} loading={transition.isPending}>
                  暂停
                </Button>
              )}
              {p.status === 'paused' && (
                <Button onClick={() => transition.mutate('resume')} loading={transition.isPending}>
                  恢复招聘
                </Button>
              )}
              <Button danger onClick={close}>
                关闭岗位
              </Button>
            </Space>
          ) : null
        }
      />
      <Tabs
        items={[
          {
            key: 'overview',
            label: '概览',
            children: (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(0, 3fr) minmax(280px, 2fr)',
                  gap: 24,
                  alignItems: 'start',
                }}
              >
                <section className="panel" style={{ padding: 16 }} aria-labelledby="funnel-h">
                  <h2 id="funnel-h" style={{ fontSize: 16, fontWeight: 500, margin: '0 0 12px' }}>
                    招聘阶段
                  </h2>
                  {d.funnel.data ? (
                    <FunnelBar
                      stages={d.funnel.data}
                      onPick={(s) => track('jb_stage_click', { stage: s, from: 'detail' })}
                    />
                  ) : (
                    <Skeleton active />
                  )}
                  <p className="muted" style={{ fontSize: 12, marginBottom: 0, marginTop: 12 }}>
                    人数为到达过该阶段的累计人数；转化率 = 本阶段 ÷ 上一阶段。
                  </p>
                </section>
                <section className="panel" style={{ padding: 16 }}>
                  <Descriptions
                    column={1}
                    size="small"
                    items={[
                      {
                        label: '可招 / 计划',
                        children: (
                          <span className="num">
                            {p.planned - p.hired} / {p.planned}
                          </span>
                        ),
                      },
                      { label: '对外薪资区间', children: formatSalaryRange(p.salary) },
                      {
                        label: '期望到岗',
                        children: <span className="num">{formatDate(p.expectedOnboard)}</span>,
                      },
                      { label: '负责 HR', children: p.ownerHr },
                      { label: '用人经理', children: p.hiringManager },
                      { label: '来源需求', children: p.requisitionIds.join('、') },
                    ]}
                  />
                </section>
              </div>
            ),
          },
          {
            key: 'candidates',
            label: '候选人',
            children: (
              <PositionApplications
                rows={d.applications.data ?? []}
                loading={d.applications.isLoading}
              />
            ),
          },
          {
            key: 'profile',
            label: '画像与知识库',
            children: (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
                  gap: 24,
                  alignItems: 'start',
                }}
              >
                <section className="panel" style={{ padding: 16 }}>
                  <h2 style={{ fontSize: 16, fontWeight: 500, marginTop: 0 }}>岗位画像</h2>
                  {d.profile.data ? <ProfilePanel profile={d.profile.data} /> : <Skeleton active />}
                </section>
                <section className="panel" style={{ padding: 16 }}>
                  <h2 style={{ fontSize: 16, fontWeight: 500, marginTop: 0 }}>岗位知识库</h2>
                  {d.kb.data ? <KbPanel entries={d.kb.data} /> : <Skeleton active />}
                </section>
              </div>
            ),
          },
        ]}
      />
    </div>
  );
}
