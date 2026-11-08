import {
  BellOutlined,
  CalendarOutlined,
  FileAddOutlined,
  FundOutlined,
  DashboardOutlined,
  IdcardOutlined,
  TrophyOutlined,
  FileSearchOutlined,
  UsergroupAddOutlined,
  ApartmentOutlined,
  PayCircleOutlined,
  MenuOutlined,
  ShareAltOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Avatar, Badge, Button, Drawer, Input, Layout, Menu, Tooltip, type InputRef } from 'antd';
import { useEffect, useRef, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useApi } from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { qk } from '@recruiter/domain';
import { Can } from '@recruiter/permissions';
import { DegradeBanner, RequisitionNotices } from '@recruiter/ui-kit';
import { AssistantDock, AssistantProvider, useAssistant } from '../features/assistant';
import { useMediaQuery } from '../shared/useMediaQuery';
import './shell.css';

const { Sider, Content } = Layout;
export function Shell() {
  const session = useSession();
  return (
    <AssistantProvider key={session?.userId ?? 'anonymous'}>
      <ShellLayout />
    </AssistantProvider>
  );
}

function ShellLayout() {
  const api = useApi();
  const assistant = useAssistant();
  const nav = useNavigate();
  const loc = useLocation();
  const session = useSession();
  const compact = !useMediaQuery('(min-width: 992px)');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [noticeReveal, setNoticeReveal] = useState(0);
  const [command, setCommand] = useState('');
  const commandRef = useRef<InputRef>(null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        commandRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const onAssistant = loc.pathname === '/assistant';
  // 顶栏一句话直接交给 AI 助手：在助手页就地回答，其他页面在右侧面板回答，不打断当前页面
  const sendCommand = () => {
    const text = command.trim();
    if (!text || assistant.busy) return;
    setCommand('');
    commandRef.current?.blur();
    if (!onAssistant) assistant.setOpen(true);
    assistant.send(text);
  };
  const { setOpen } = assistant;
  useEffect(() => {
    if (onAssistant) setOpen(false);
  }, [onAssistant, setOpen]);
  useEffect(() => setDrawerOpen(false), [loc.pathname]);
  const { data: summary } = useQuery({
    queryKey: qk.workbench.summary(),
    queryFn: () => api.workbenchSummary(),
    enabled: import.meta.env.VITE_USE_MOCK !== 'false',
  });
  const selected = '/' + (loc.pathname.split('/')[1] ?? 'workbench');
  const items = [
    { key: '/assistant', icon: <ThunderboltOutlined />, label: 'AI 招聘助手' },
    { key: '/workbench', icon: <DashboardOutlined />, label: 'AI 工作台' },
    { key: '/requisitions', icon: <FileAddOutlined />, label: '招聘需求管理' },
    { key: '/positions', icon: <IdcardOutlined />, label: '岗位管理' },
    { key: '/candidates', icon: <TeamOutlined />, label: '候选人' },
    { key: '/interviews', icon: <CalendarOutlined />, label: '面试' },
    { key: '/hiring', icon: <TrophyOutlined />, label: '录用与移交' },
    { key: '/ai-jobs', icon: <FileSearchOutlined />, label: 'AI 任务与复核' },
    { key: '/channels', icon: <ShareAltOutlined />, label: '渠道' },
    { key: '/insights', icon: <FundOutlined />, label: '数据洞察' },
  ];
  const settings = [
    ...(session?.roles.some((r) => r === 'hrbp' || r === 'headcount_owner')
      ? [{ key: '/settings/headcount', icon: <UsergroupAddOutlined />, label: '编制管理' }]
      : []),
    ...(session?.roles.some((r) => r === 'admin' || r === 'recruiting_lead')
      ? [{ key: '/settings/organization', icon: <ApartmentOutlined />, label: '组织与权限' }]
      : []),
    ...(session?.roles.some((r) => r === 'recruiting_lead' || r === 'compensation_owner')
      ? [{ key: '/settings/salary', icon: <PayCircleOutlined />, label: '职级薪资表' }]
      : []),
  ];
  const navigation = (
    <>
      <a className="sidebar-brand" href="/assistant">
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
        items={items.map((item) => ({
          ...item,
          label: ['/channels', '/insights'].includes(item.key) ? (
            <span className="hr-nav-label">
              {item.label}
              <span className="hr-nav-later">二期</span>
            </span>
          ) : (
            item.label
          ),
        }))}
        onClick={(e) => nav(e.key)}
        aria-label="主导航"
      />
      <div className="nav-caption">MANAGEMENT · 管理</div>
      <Can perm="settings.automation">
        <Menu
          mode="inline"
          theme="dark"
          selectedKeys={[loc.pathname]}
          items={[
            { key: '/settings/automation', icon: <ThunderboltOutlined />, label: '自动化策略' },
          ]}
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
    </>
  );
  return (
    <Layout className="recruiter-shell">
      <a href="#main" className="sr-only">
        跳到主要内容
      </a>
      {compact ? (
        <Drawer
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          width={264}
          title="AI 招聘官"
          className="app-nav-drawer"
          styles={{ body: { padding: 0, background: '#142c32' } }}
        >
          <nav className="app-sidebar">{navigation}</nav>
        </Drawer>
      ) : (
        <Sider width={232} className="app-sidebar">
          {navigation}
        </Sider>
      )}
      <Layout style={{ minWidth: 0 }}>
        <header className="app-topbar">
          {compact && (
            <Button
              type="text"
              icon={<MenuOutlined />}
              aria-label="打开导航"
              aria-expanded={drawerOpen}
              onClick={() => setDrawerOpen(true)}
            />
          )}
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
          {!compact && (
            <Input
              className="app-command"
              prefix={<ThunderboltOutlined />}
              placeholder="让 AI 做件事…"
              aria-label="AI 指令栏"
              ref={commandRef}
              value={command}
              maxLength={4000}
              onChange={(e) => setCommand(e.target.value)}
              onPressEnter={(e) => {
                if (!e.nativeEvent.isComposing) sendCommand();
              }}
              autoComplete="off"
              suffix={<kbd>⌘ K</kbd>}
              style={{ maxWidth: 300, minWidth: 160 }}
            />
          )}
          <Button
            className="app-ai-entry"
            aria-label="AI 助手"
            icon={<ThunderboltOutlined />}
            aria-pressed={assistant.open}
            onClick={() => {
              if (onAssistant) document.getElementById('assistant-input')?.focus();
              else assistant.setOpen(!assistant.open);
            }}
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
                onClick={() => setNoticeReveal((value) => value + 1)}
              />
            </Badge>
          </Tooltip>
          <Avatar style={{ background: 'var(--rc-brand-soft)', color: 'var(--rc-brand)' }}>
            {session?.name.slice(0, 1)}
          </Avatar>
        </header>
        <DegradeBanner show={!!summary?.aiDegraded} />
        <Content id="main" tabIndex={-1} className="app-content">
          <RequisitionNotices
            revealKey={noticeReveal}
            onOpen={(id) => nav(`/requisitions/${id}`)}
          />
          <Outlet />
        </Content>
        {!onAssistant && <AssistantDock />}
      </Layout>
    </Layout>
  );
}
