// 三种登录：飞书网页 SSO、飞书 H5 免登、候选人签名链接（实现文档第 8 节 auth 包）
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type Role = 'recruiting_lead' | 'recruiter' | 'hiring_manager' | 'hrbp' | 'interviewer' | 'admin' | 'candidate';

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
}

const AuthContext = createContext<AuthState | null>(null);
const STORAGE_KEY = 'recruiter.session';

function readStored(): Session | null {
  try {
    const raw = globalThis.sessionStorage?.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children, mockSession, feishuAuthUrl }: { children: ReactNode; mockSession?: Session; feishuAuthUrl?: string }) {
  const [session, setSession] = useState<Session | null>(() => readStored() ?? mockSession ?? null);

  const persist = useCallback((s: Session | null) => {
    setSession(s);
    try {
      if (s) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(s));
      else sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* 隐私模式下存储不可用时只保留内存会话 */
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      session,
      loginWithFeishu: () => {
        if (feishuAuthUrl) globalThis.location.assign(`${feishuAuthUrl}?redirect=${encodeURIComponent(location.href)}`);
      },
      feishuH5Login: async () => {
        // 飞书 JSSDK 的免登：tt.requestAccess 取 code，再由后端换会话；mock 环境直接使用演示会话
        if (mockSession) persist(mockSession);
      },
      loginWithCandidateLink: (token) => persist({ userId: 'candidate', name: '候选人', roles: ['candidate'], token }),
      logout: () => persist(null),
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
