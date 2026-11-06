import {
  ApartmentOutlined,
  BellOutlined,
  CalendarOutlined,
  DashboardOutlined,
  FileAddOutlined,
  FileSearchOutlined,
  FundOutlined,
  IdcardOutlined,
  MenuOutlined,
  PayCircleOutlined,
  RobotOutlined,
  ShareAltOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  TrophyOutlined,
  UsergroupAddOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Avatar, Badge, Button, Drawer, Input, Layout, Menu, type MenuProps } from 'antd';
import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useApi } from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { qk } from '@recruiter/domain';
import { usePermission } from '@recruiter/permissions';
import { DegradeBanner, RequisitionNotices } from '@recruiter/ui-kit';
import { useMediaQuery } from '../shared/useMediaQuery';

const { Header, Sider, Content } = Layout;

type MenuItem = Required<MenuProps>['items'][number];

/** 二期模块：保留入口但标明状态，不让人点进去才发现是空的 */
function Later({ children }: { children: string }) {
  return (
    <span className="hr-nav-label">
      {children}
      <span className="hr-nav-later">二期</span>
    </span>
  );
}

export function Shell() {
  const api = useApi();
  const nav = useNavigate();
  const loc = useLocation();
  const session = useSession();
  const canAutomation = usePermission('settings.automation');
  const compact = !useMediaQuery('(min-width: 992px)');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { data: summary } = useQuery({
    queryKey: qk.workbench.summary(),
    queryFn: () => api.workbenchSummary(),
    enabled: import.meta.env.VITE_USE_MOCK !== 'false',
  });

  useEffect(() => setDrawerOpen(false), [loc.pathname]);

  const first = '/' + (loc.pathname.split('/')[1] || 'workbench');
  const selected = first === '/settings' ? loc.pathname : first;
  const roles = session?.roles ?? [];
  const hasRole = (...want: string[]) => roles.some((role) => want.includes(role));

  const settings: MenuItem[] = [
    canAutomation && {
      key: '/settings/automation',
      icon: <ThunderboltOutlined />,
      label: '自动化策略',
    },
    hasRole('hrbp', 'headcount_owner') && {
      key: '/settings/headcount',
      icon: <UsergroupAddOutlined />,
      label: '编制管理',
    },
    hasRole('admin', 'recruiting_lead') && {
      key: '/settings/organization',
      icon: <ApartmentOutlined />,
      label: '组织与权限',
    },
    hasRole('recruiting_lead', 'compensation_owner') && {
      key: '/settings/salary',
      icon: <PayCircleOutlined />,
      label: '职级薪资表',
    },
  ].filter(Boolean) as MenuItem[];

  const pending = summary?.pendingDecisions;
  const items: MenuItem[] = [
    {
      key: '/workbench',
      icon: <DashboardOutlined />,
      label: (
        <span className="hr-nav-label">
          AI 工作台
          {!!pending && (
            <span className="hr-nav-count" aria-label={`${pending} 件待决策`}>
              {pending}
            </span>
          )}
        </span>
      ),
    },
    {
      type: 'group',
      label: '招聘流程',
      children: [
        { key: '/requisitions', icon: <FileAddOutlined />, label: '招聘需求管理' },
        { key: '/positions', icon: <IdcardOutlined />, label: '岗位管理' },
        { key: '/candidates', icon: <TeamOutlined />, label: '候选人' },
        { key: '/interviews', icon: <CalendarOutlined />, label: '面试' },
        { key: '/hiring', icon: <TrophyOutlined />, label: '录用与移交' },
        { key: '/ai-jobs', icon: <FileSearchOutlined />, label: 'AI 任务与复核' },
      ],
    },
    {
      type: 'group',
      label: '更多',
      children: [
        { key: '/channels', icon: <ShareAltOutlined />, label: <Later>渠道</Later> },
        { key: '/insights', icon: <FundOutlined />, label: <Later>数据洞察</Later> },
      ],
    },
    ...(settings.length ? [{ type: 'group' as const, label: '设置', children: settings }] : []),
  ];

  const menu = (
    <Menu
      mode="inline"
      selectedKeys={[selected]}
      items={items}
      onClick={(e) => nav(e.key)}
      className="hr-nav"
      aria-label="主导航"
    />
  );

  return (
    <Layout className="hr-shell">
      <a href="#main" className="sr-only">
        跳到主要内容
      </a>
      <Header className="hr-header">
        {compact && (
          <Button
            type="text"
            icon={<MenuOutlined />}
            aria-label="打开导航"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          />
        )}
        <a
          className="hr-brand"
          href="/workbench"
          onClick={(e) => {
            e.preventDefault();
            nav('/workbench');
          }}
        >
          <img src="/favicon.svg" width={24} height={24} alt="" />
          <span translate="no">AI 招聘官</span>
        </a>
        <Input.Search
          className="hr-search"
          placeholder="搜人名、手机号、需求编号、岗位…"
          aria-label="全局搜索"
          name="q"
          autoComplete="off"
          spellCheck={false}
          onSearch={(q) => q && nav(`/candidates?q=${encodeURIComponent(q)}`)}
        />
        {!compact && (
          <Input
            className="hr-command"
            prefix={<RobotOutlined aria-hidden style={{ color: 'var(--rc-ai)' }} />}
            placeholder="让 AI 做件事，或者问个问题，比如“白班客服还差几个人”"
            aria-label="AI 指令栏"
            autoComplete="off"
            suffix={<kbd className="rc-kbd">⌘&nbsp;K</kbd>}
          />
        )}
        <span className="hr-header-end">
          <Badge count={summary?.handoffs} size="small" offset={[-6, 6]}>
            <Button
              type="text"
              shape="circle"
              icon={<BellOutlined style={{ fontSize: 18 }} />}
              aria-label={
                summary?.handoffs ? `消息中心，${summary.handoffs} 个会话转给了你` : '消息中心'
              }
              onClick={() => nav('/workbench')}
            />
          </Badge>
          <Avatar
            style={{ background: 'var(--rc-brand-soft)', color: 'var(--rc-brand)', flex: 'none' }}
            aria-label={session?.name}
          >
            {session?.name.slice(0, 1)}
          </Avatar>
        </span>
      </Header>
      <DegradeBanner show={!!summary?.aiDegraded} />
      <Layout>
        {compact ? (
          <Drawer
            placement="left"
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            width={264}
            title="AI 招聘官"
            styles={{ body: { padding: 0 } }}
          >
            {menu}
          </Drawer>
        ) : (
          <Sider width={216} className="hr-sider">
            {menu}
          </Sider>
        )}
        <Content id="main" tabIndex={-1} className="hr-main">
          <RequisitionNotices onOpen={(id) => nav(`/requisitions/${id}`)} />
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
