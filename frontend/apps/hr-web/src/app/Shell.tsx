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
  ThunderboltOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Avatar, Badge, Button, Input, Layout, Menu, Tooltip } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useApi } from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { qk } from '@recruiter/domain';
import { Can } from '@recruiter/permissions';
import { DegradeBanner, RequisitionNotices } from '@recruiter/ui-kit';
import './shell.css';

const { Sider, Content } = Layout;
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
    { key: '/workbench', icon: <InboxOutlined />, label: 'AI 工作台' },
    { key: '/requisitions', icon: <FileAddOutlined />, label: '招聘需求管理' },
    { key: '/positions', icon: <SolutionOutlined />, label: '岗位管理' },
    { key: '/candidates', icon: <TeamOutlined />, label: '候选人' },
    { key: '/interviews', icon: <CalendarOutlined />, label: '面试' },
    { key: '/hiring', icon: <SolutionOutlined />, label: '录用与移交' },
    { key: '/ai-jobs', icon: <ThunderboltOutlined />, label: 'AI 任务与复核' },
    { key: '/channels', icon: <ShareAltOutlined />, label: '渠道' },
    { key: '/insights', icon: <FundOutlined />, label: '数据洞察' },
  ];
  const settings = [
    ...(session?.roles.some((r) => r === 'hrbp' || r === 'headcount_owner')
      ? [{ key: '/settings/headcount', icon: <TeamOutlined />, label: '编制管理' }]
      : []),
    ...(session?.roles.some((r) => r === 'admin' || r === 'recruiting_lead')
      ? [{ key: '/settings/organization', icon: <TeamOutlined />, label: '组织与权限' }]
      : []),
    ...(session?.roles.some((r) => r === 'recruiting_lead' || r === 'compensation_owner')
      ? [{ key: '/settings/salary', icon: <FundOutlined />, label: '职级薪资表' }]
      : []),
  ];
  return (
    <Layout className="recruiter-shell">
      <a href="#main" className="sr-only">
        跳到主要内容
      </a>
      <Sider width={232} className="app-sidebar" breakpoint="lg" collapsedWidth={72}>
        <a className="sidebar-brand" href="/workbench">
          <span className="brand-mark">
            r<span className="sr-only">.</span>
          </span>
          <span className="brand-copy">
            <strong>AI 招聘官</strong>
            <small>PEOPLE & POSSIBILITIES</small>
          </span>
        </a>
        <div className="nav-caption">WORKSPACE · 招聘空间</div>
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[selected]}
          items={items}
          onClick={(e) => nav(e.key)}
          aria-label="主导航"
        />
        <div className="nav-caption">MANAGEMENT · 管理</div>
        <Can perm="settings.automation">
          <Menu
            mode="inline"
            theme="dark"
            selectedKeys={[loc.pathname]}
            items={[{ key: '/settings/automation', icon: <SettingOutlined />, label: '设置' }]}
            onClick={(e) => nav(e.key)}
          />
        </Can>
        {!!settings.length && (
          <Menu
            mode="inline"
            theme="dark"
            selectedKeys={[loc.pathname]}
            items={settings}
            onClick={(e) => nav(e.key)}
          />
        )}
        <div className="sidebar-note">
          <b>
            <ThunderboltOutlined /> 与 AI 一起，发现人才
          </b>
          让信息更有条理，
          <br />
          让每一个决定有据可依。
        </div>
      </Sider>
      <Layout style={{ minWidth: 0 }}>
        <header className="app-topbar">
          <div className="app-breadcrumb">
            <span>工作空间</span>
            <RightOutlined />
            <b>{items.find((i) => i.key === selected)?.label ?? '管理设置'}</b>
          </div>
          <Input.Search
            className="app-search"
            prefix={<SearchOutlined />}
            placeholder="搜索候选人"
            allowClear
            aria-label="全局搜索"
            onSearch={(q) => {
              const key = import.meta.env.VITE_USE_MOCK === 'false' ? 'query' : 'q';
              if (q.trim()) nav(`/candidates?${key}=${encodeURIComponent(q.trim())}`);
            }}
          />
          <Button
            className="app-ai-entry"
            aria-label="AI 助手"
            icon={<ThunderboltOutlined />}
            onClick={() => nav('/ai-jobs')}
          >
            <span className="entry-copy">AI 助手</span>
          </Button>
          <Tooltip title="审批与交接消息">
            <Badge count={summary?.handoffs} size="small">
              <Button
                type="text"
                shape="circle"
                icon={<BellOutlined />}
                aria-label="消息中心"
                onClick={() => {
                  const notice = document.getElementById('requisition-notices');
                  if (notice instanceof HTMLDetailsElement) {
                    notice.open = true;
                    notice.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  }
                }}
              />
            </Badge>
          </Tooltip>
          <Avatar style={{ background: 'var(--rc-brand-soft)', color: 'var(--rc-brand)' }}>
            {session?.name.slice(0, 1)}
          </Avatar>
        </header>
        <DegradeBanner show={!!summary?.aiDegraded} />
        <Content id="main" className="app-content">
          <RequisitionNotices onOpen={(id) => nav(`/requisitions/${id}`)} />
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
