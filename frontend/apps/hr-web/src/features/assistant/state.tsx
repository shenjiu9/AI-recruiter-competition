import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  newIdempotencyKey,
  toAppError,
  useApi,
  type AiJob,
  type AssistantFocus,
  type AssistantReply,
} from '@recruiter/api-client';

/** 对话里的一轮。助手回复保存结构化结果；本地提示（执行结果等）只有文字。 */
export interface Turn {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  at: number;
  reply?: AssistantReply;
  job?: AiJob;
  pending?: boolean;
  error?: string;
  /** 失败重发时沿用同一个幂等键，避免同一句话被执行两次 */
  key?: string;
  tone?: 'success' | 'error';
}

interface AssistantState {
  turns: Turn[];
  busy: boolean;
  focus: AssistantFocus;
  send: (text: string) => void;
  retry: (turnId: string) => void;
  note: (text: string, tone?: Turn['tone']) => void;
  showJob: (job: AiJob, text?: string) => void;
  clear: () => void;
  open: boolean;
  setOpen: (open: boolean) => void;
}

const STORAGE = 'recruiter.assistant.v1';
const Ctx = createContext<AssistantState | null>(null);

function load(): { turns: Turn[]; focus: AssistantFocus } {
  try {
    const raw = sessionStorage.getItem(STORAGE);
    if (raw) {
      const parsed = JSON.parse(raw) as { turns: Turn[]; focus: AssistantFocus };
      // 刷新时还没回来的请求视为中断，提示可重发
      return {
        focus: parsed.focus ?? {},
        turns: (parsed.turns ?? []).map((t) =>
          t.pending ? { ...t, pending: false, error: '页面刷新时请求中断，可以重新发送' } : t,
        ),
      };
    }
  } catch {
    /* 存储不可用时从空对话开始 */
  }
  return { turns: [], focus: {} };
}

const uid = () => Math.random().toString(36).slice(2) + Date.now().toString(36);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const api = useApi();
  const initial = useRef(load());
  const [turns, setTurns] = useState<Turn[]>(initial.current.turns);
  const [focus, setFocus] = useState<AssistantFocus>(initial.current.focus);
  const [open, setOpen] = useState(false);
  const inflight = useRef(false);
  const [busy, setBusy] = useState(false);
  const focusRef = useRef(focus);
  focusRef.current = focus;

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE, JSON.stringify({ turns: turns.slice(-40), focus }));
    } catch {
      /* 存储已满或被禁用：对话仍可用，只是刷新后不保留 */
    }
  }, [turns, focus]);

  const ask = useCallback(
    async (question: Turn, answerId: string) => {
      inflight.current = true;
      setBusy(true);
      try {
        const reply = await api.assistant(
          {
            text: question.text,
            focus: {
              candidate_id: focusRef.current.candidate_id ?? '',
              position_id: focusRef.current.position_id ?? '',
            },
          },
          { idempotencyKey: question.key! },
        );
        setTurns((all) =>
          all.map((t) =>
            t.id === answerId ? { ...t, pending: false, text: reply.reply, reply } : t,
          ),
        );
        if (reply.focus.candidate_id || reply.focus.position_id)
          setFocus((f) => ({ ...f, ...reply.focus }));
      } catch (e) {
        const err = toAppError(e);
        setTurns((all) =>
          all.map((t) =>
            t.id === answerId
              ? {
                  ...t,
                  pending: false,
                  error:
                    err.code === 'BACKEND_REQUIRED'
                      ? 'AI 助手需要连接真实后端：请用 VITE_USE_MOCK=false 启动。'
                      : err.message,
                }
              : t,
          ),
        );
      } finally {
        inflight.current = false;
        setBusy(false);
      }
    },
    [api],
  );

  const send = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text || inflight.current) return;
      const question: Turn = {
        id: uid(),
        role: 'user',
        text,
        at: Date.now(),
        key: newIdempotencyKey(),
      };
      const answer: Turn = {
        id: uid(),
        role: 'assistant',
        text: '',
        at: Date.now(),
        pending: true,
      };
      setTurns((all) => [...all, question, answer]);
      void ask(question, answer.id);
    },
    [ask],
  );

  const retry = useCallback(
    (answerId: string) => {
      if (inflight.current) return;
      const index = turns.findIndex((t) => t.id === answerId);
      const question = turns[index - 1];
      if (!question || question.role !== 'user') return;
      setTurns((all) =>
        all.map((t) => (t.id === answerId ? { ...t, pending: true, error: undefined } : t)),
      );
      void ask(question, answerId);
    },
    [ask, turns],
  );

  const note = useCallback((text: string, tone?: Turn['tone']) => {
    setTurns((all) => [...all, { id: uid(), role: 'assistant', text, at: Date.now(), tone }]);
  }, []);

  const showJob = useCallback((job: AiJob, text = '') => {
    setTurns((all) => [...all, { id: uid(), role: 'assistant', text, at: Date.now(), job }]);
  }, []);

  const clear = useCallback(() => {
    setTurns([]);
    setFocus({});
  }, []);

  const value = useMemo(
    () => ({ turns, busy, focus, send, retry, note, showJob, clear, open, setOpen }),
    [turns, busy, focus, send, retry, note, showJob, clear, open],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAssistant() {
  const value = useContext(Ctx);
  if (!value) throw new Error('useAssistant must be used inside AssistantProvider');
  return value;
}
