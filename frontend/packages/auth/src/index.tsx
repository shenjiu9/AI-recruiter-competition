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
        <div
          style={{
            padding: '8px 20px',
            background: '#eef2f7',
            display: 'flex',
            justifyContent: 'space-between',
          }}
        >
          <span>
            {session.name}
            {available ? ' · 开发环境' : ''}
          </span>
          <button
            onClick={() => {
              logout();
              setPassword('');
            }}
          >
            退出登录
          </button>
        </div>
        {children}
      </Fragment>
    );
  return (
    <main style={{ maxWidth: 420, margin: '12vh auto', padding: 24, fontFamily: 'sans-serif' }}>
      <h1>AI 招聘系统</h1>
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
              <option value="sales">周振华 · 销售部</option>
            </select>
          </label>
          <label style={{ display: 'block', marginBottom: 16 }}>
            开发登录口令
            <input
              aria-label="开发登录口令"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ width: '100%', padding: 10, boxSizing: 'border-box' }}
            />
          </label>
          <button
            type="submit"
            disabled={busy || available !== true}
            style={{ width: '100%', padding: 12 }}
          >
            {busy ? '正在登录…' : '登录'}
          </button>
        </form>
      )}
      {error && (
        <p role="alert" style={{ color: '#b3362f' }}>
          {error}
        </p>
      )}
    </main>
  );
}
