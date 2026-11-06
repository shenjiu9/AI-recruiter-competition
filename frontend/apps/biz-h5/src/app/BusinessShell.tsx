import { TabBar } from 'antd-mobile';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';

function NavIcon({ kind }: { kind: string }) {
  const paths: Record<string, string> = {
    inbox: 'M4 4h16v16H4z M4 13h5l1.5 3h3l1.5-3h5',
    positions: 'M3 7h18v14H3z M8 7V3h8v4 M3 12h18 M10 12v3h4v-3',
    interviews: 'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h3 M8 17h6',
    workbench: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  };
  return (
    <svg
      width="21"
      height="21"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[kind]} />
    </svg>
  );
}

export function BusinessShell() {
  const loc = useLocation();
  const nav = useNavigate();
  const active = loc.pathname.startsWith('/positions')
    ? '/positions'
    : loc.pathname.startsWith('/interviews')
      ? '/interviews'
      : ['/workbench', '/hiring', '/ai-jobs'].some((p) => loc.pathname.startsWith(p))
        ? '/workbench'
        : '/';
  return (
    <div className="rm-business-shell">
      <div className="rm-business-body">
        <Outlet />
      </div>
      <nav className="rm-bottom-nav" aria-label="业务导航">
        <TabBar activeKey={active} onChange={nav}>
          <TabBar.Item key="/" icon={<NavIcon kind="inbox" />} title="待办" />
          <TabBar.Item key="/positions" icon={<NavIcon kind="positions" />} title="岗位" />
          <TabBar.Item key="/interviews" icon={<NavIcon kind="interviews" />} title="面试" />
          <TabBar.Item key="/workbench" icon={<NavIcon kind="workbench" />} title="工作台" />
        </TabBar>
      </nav>
    </div>
  );
}
