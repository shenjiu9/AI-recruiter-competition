import {
  BellOutlined,
  CalendarOutlined,
  FileAddOutlined,
  FundOutlined,
  InboxOutlined,
  SettingOutlined,
  ShareAltOutlined,
  SolutionOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Avatar, Badge, Input, Layout, Menu } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useApi } from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { qk } from '@recruiter/domain';
import { Can } from '@recruiter/permissions';
import { DegradeBanner } from '@recruiter/ui-kit';

const { Header, Sider, Content } = Layout;

export function Shell() {
  const api = useApi();
  const nav = useNavigate();
  const loc = useLocation();
  const session = useSession();
  const { data: summary } = useQuery({
    queryKey: qk.workbench.summary(),
    queryFn: () => api.workbenchSummary(),
    enabled: import.meta.env.VITE_USE_MOCK !== 'false',
  });
  const selected = '/' + (loc.pathname.split('/')[1] ?? 'workbench');

  const items = [
    {
      key: '/workbench',
      icon: <InboxOutlined />,
      label: (
        <span style={{ display: 'flex' }}>
          AI 工作台
          <span style={{ marginLeft: 'auto', fontSize: 12 }}>
            {summary?.pendingDecisions ?? ''}
          </span>
        </span>
      ),
    },
    { key: '/requisitions', icon: <FileAddOutlined />, label: '招聘需求管理' },
    { key: '/positions', icon: <SolutionOutlined />, label: '岗位管理' },
    { key: '/candidates', icon: <TeamOutlined />, label: '候选人' },
    { key: '/interviews', icon: <CalendarOutlined />, label: '面试' },
    { key: '/channels', icon: <ShareAltOutlined />, label: '渠道' },
    { key: '/insights', icon: <FundOutlined />, label: '数据洞察' },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <a href="#main" className="sr-only">
        跳到主要内容
      </a>
      <Header
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          borderBottom: '1px solid var(--rc-line)',
          position: 'sticky',
          top: 0,
          zIndex: 5,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: 184, fontWeight: 500 }}>
          <img src="/favicon.svg" width={24} height={24} alt="" />
          AI 招聘官
        </div>
        <Input.Search
          placeholder="搜人名、手机号、需求编号、岗位"
          style={{ width: 300 }}
          aria-label="全局搜索"
          onSearch={(q) => q && nav(`/candidates?q=${encodeURIComponent(q)}`)}
        />
        <Input
          placeholder="让 AI 做件事，或者问个问题，比如“白班客服还差几个人”"
          style={{ flex: 1, maxWidth: 520 }}
          aria-label="AI 指令栏"
          suffix={<span className="rc-kbd">⌘K</span>}
        />
        <span style={{ flex: 1 }} />
        <Badge count={summary?.handoffs} size="small">
          <BellOutlined style={{ fontSize: 18, color: 'var(--rc-ink-2)' }} aria-label="消息中心" />
        </Badge>
        <Avatar style={{ background: 'var(--rc-brand-soft)', color: 'var(--rc-brand)' }}>
          {session?.name.slice(0, 1)}
        </Avatar>
      </Header>
      <DegradeBanner show={!!summary?.aiDegraded} />
      <Layout>
        <Sider
          width={208}
          style={{ borderRight: '1px solid var(--rc-line)' }}
          breakpoint="lg"
          collapsedWidth={64}
        >
          <Menu
            mode="inline"
            selectedKeys={[selected]}
            items={items}
            onClick={(e) => nav(e.key)}
            style={{ paddingTop: 12, borderInlineEnd: 0 }}
            aria-label="主导航"
          />
          <Can perm="settings.automation">
            <Menu
              mode="inline"
              selectedKeys={[selected]}
              items={[{ key: '/settings', icon: <SettingOutlined />, label: '设置' }]}
              onClick={() => nav('/settings/automation')}
              style={{ borderInlineEnd: 0 }}
            />
          </Can>
        </Sider>
        <Content id="main" style={{ padding: 24, minWidth: 0 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
