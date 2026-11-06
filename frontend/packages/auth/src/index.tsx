import { Button, Input } from 'antd';
import './auth.css';
// 三种登录：飞书网页 SSO、飞书 H5 免登、候选人签名链接（实现文档第 8 节 auth 包）
import {
  createContext,
  Fragment,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type Role =
  | 'recruiting_lead'
  | 'recruiter'
  | 'hiring_manager'
  | 'hrbp'
  | 'headcount_owner'
  | 'hrd'
  | 'compensation_owner'
  | 'interviewer'
  | 'admin'
  | 'candidate';

export interface Session {
  userId: string;
  name: string;
  roles: Role[];
  token: string;
}

interface AuthState {
  session: Session | null;
  loginWithFeishu: () => void;
  feishuH5Login: () => Promise<void>;
  loginWithCandidateLink: (token: string) => void;
  logout: () => void;
  loginDevelopment: (userId: string, password: string, baseUrl: string) => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);
const STORAGE_KEY = 'recruiter.session';

function readStored(): Session | null {
  try {
    const raw = globalThis.sessionStorage?.getItem(STORAGE_KEY);
    const session = raw ? (JSON.parse(raw) as Session) : null;
    return session?.token && session.token !== 'demo' ? session : null;
  } catch {
    return null;
  }
}

export function AuthProvider({
  children,
  mockSession,
  feishuAuthUrl,
}: {
  children: ReactNode;
  mockSession?: Session;
  feishuAuthUrl?: string;
}) {
  const [session, setSession] = useState<Session | null>(() => mockSession ?? readStored());

  const persist = useCallback((s: Session | null) => {
    setSession(s);
    try {
      if (s) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* 隐私模式下存储不可用时只保留内存会话 */
    }
  }, []);

  useEffect(() => {
    const reset = () => persist(null);
    globalThis.addEventListener('recruiter:unauthorized', reset);
    return () => globalThis.removeEventListener('recruiter:unauthorized', reset);
  }, [persist]);

  const value = useMemo<AuthState>(
    () => ({
      session,
      loginWithFeishu: () => {
        if (feishuAuthUrl)
          globalThis.location.assign(
            `${feishuAuthUrl}?redirect=${encodeURIComponent(location.href)}`,
          );
      },
      feishuH5Login: async () => {
        // 飞书 JSSDK 的免登：tt.requestAccess 取 code，再由后端换会话；mock 环境直接使用演示会话
        if (mockSession) persist(mockSession);
      },
      loginWithCandidateLink: (token) =>
        persist({ userId: 'candidate', name: '候选人', roles: ['candidate'], token }),
      logout: () => persist(null),
      loginDevelopment: async (userId, password, baseUrl) => {
        const response = await fetch(`${baseUrl}/api/v1/auth/dev-login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, password }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error?.message ?? '登录失败');
        persist(result as Session);
      },
    }),
    [session, feishuAuthUrl, mockSession, persist],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(AuthContext);
  if (!v) throw new Error('useAuth 必须在 AuthProvider 内使用');
  return v;
}

export const useSession = (): Session | null => useAuth().session;

/** Development login is offered only when the server explicitly enables it. */
export function SessionGate({
  children,
  mock,
  baseUrl,
}: {
  children: ReactNode;
  mock: boolean;
  baseUrl: string;
}) {
  const { session, logout, loginDevelopment } = useAuth();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [user, setUser] = useState('hr');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (mock) return;
    const abort = new AbortController();
    fetch(`${baseUrl}/api/v1/auth/config`, { signal: abort.signal })
      .then(async (r) => {
        if (!r.ok) throw new Error('无法读取登录配置');
        setAvailable((await r.json()).developmentLogin);
      })
      .catch((e: Error) => {
        if (e.name !== 'AbortError') setError('无法连接后端，请确认 API 已启动');
      });
    return () => abort.abort();
  }, [mock, baseUrl]);
  if (mock) return <>{children}</>;
  if (session)
    return (
      <Fragment key={session.token}>
        <div className="rc-session-bar">
          <span>
            {session.name}
            {available ? ' · 开发环境' : ''}
          </span>
          <Button
            type="text"
            size="small"
            onClick={() => {
              logout();
              setPassword('');
            }}
          >
            退出登录
          </Button>
        </div>
        {children}
      </Fragment>
    );
  return (
    <main className="rc-auth">
      <aside className="rc-auth-story">
        <div className="rc-auth-brand">
          <span className="rc-auth-symbol">r.</span>AI 招聘官
        </div>
        <div>
          <small>PEOPLE & POSSIBILITIES</small>
          <h2>
            每一个好机会，
            <br />
            都值得<em>遇见对的人。</em>
          </h2>
          <p>
            用清晰的流程连接团队，
            <br />
            用有依据的洞察，助力每一次选择。
          </p>
          <div className="rc-auth-art" aria-hidden="true">
            <div className="rc-auth-orbit" />
            <div className="rc-auth-path">
              <span>发现人才</span>
              <i />
              <span>深入了解</span>
              <i />
              <span>共同成长</span>
            </div>
          </div>
        </div>
        <div className="rc-auth-story-foot">AI ASSISTED. HUMAN DECIDED.</div>
      </aside>
      <section className="rc-auth-panel">
        <div className="rc-auth-card">
          <span className="rc-auth-eyebrow">WELCOME TO YOUR WORKSPACE</span>
          <h1>AI 招聘系统</h1>
          <p className="rc-auth-description">欢迎回来，开始今天的招聘协作。</p>
          {available === false ? (
            <p>飞书登录尚未配置，请联系管理员。</p>
          ) : (
            <form
              onSubmit={async (event) => {
                event.preventDefault();
                setBusy(true);
                setError('');
                try {
                  await loginDevelopment(user, password, baseUrl);
                  setPassword('');
                } catch (e) {
                  setError(e instanceof Error ? e.message : '登录失败');
                } finally {
                  setBusy(false);
                }
              }}
            >
              <p>开发账号登录</p>
              <label style={{ display: 'block', marginBottom: 16 }}>
                账号
                <select
                  aria-label="开发账号"
                  value={user}
                  onChange={(e) => setUser(e.target.value)}
                  style={{ width: '100%', padding: 10 }}
                >
                  <option value="hr">林悦 · 招聘 HR</option>
                  <option value="manager">何美玲 · 用人经理</option>
                  <option value="director">部门负责人</option>
                  <option value="hrbp">人力伙伴 · HRBP</option>
                  <option value="hrd">编制负责人</option>
                  <option value="salary_hrd">薪酬审批负责人 · HRD</option>
                  <option value="admin">系统管理员 · 组织与权限</option>
                  <option value="payroll">薪酬维护负责人</option>
                  <option value="analyst">田野 · 经营分析 / 财务</option>
                  <option value="sales">周振华 · 销售部</option>
                </select>
              </label>
              <label style={{ display: 'block', marginBottom: 16 }}>
                开发登录口令
                <Input.Password
                  aria-label="开发登录口令"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{ width: '100%', padding: 10, boxSizing: 'border-box' }}
                />
              </label>
              <Button
                type="primary"
                htmlType="submit"
                disabled={busy || available !== true}
                style={{ width: '100%', padding: 12 }}
              >
                {busy ? '正在登录…' : '登录'}
              </Button>
            </form>
          )}
          {error && (
            <p className="rc-auth-error" role="alert" style={{ color: '#b3362f' }}>
              {error}
            </p>
          )}
          <p className="rc-auth-footnote">
            请使用已授权的账号进入工作空间。
            <br />
            候选人请通过招聘 HR 提供的专属链接访问。
          </p>
        </div>
      </section>
    </main>
  );
}
