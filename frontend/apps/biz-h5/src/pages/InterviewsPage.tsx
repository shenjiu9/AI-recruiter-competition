import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import {
  useApi,
  useReliableWrite,
  toAppError,
  type InterviewAvailability,
} from '@recruiter/api-client';
import { InterviewDetails, INTERVIEW_STATUS } from '@recruiter/ui-kit/interview-details';

export function InterviewsPage() {
  const api = useApi();
  const cache = useQueryClient();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ['biz-interviews', page],
    queryFn: () => api.liveInterviews(page, { mine: 'true' }),
    refetchInterval: 5000,
  });
  const pref = useQuery({
    queryKey: ['interview-availability'],
    queryFn: () => api.interviewAvailability(),
  });
  return (
    <main style={{ maxWidth: 700, margin: 'auto', padding: 16 }}>
      <Link to="/">返回招聘待办</Link>
      <h1>我的面试</h1>
      {query.isError && <p role="alert">{toAppError(query.error).message}</p>}
      {query.data?.items.map((iv) => (
        <article key={iv.id} className="rm-card">
          <h2>{iv.candidate_name}</h2>
          <p>
            {iv.position_name} · {iv.round_name}
          </p>
          <p>
            {INTERVIEW_STATUS[iv.status]} ·{' '}
            {iv.start ? new Date(iv.start).toLocaleString() : '待约'}
          </p>
          <Link to={`/interviews/${iv.id}`}>准备与面评</Link>
        </article>
      ))}
      {query.data?.total === 0 && <p>暂无分配给您的面试。</p>}
      <button disabled={page === 1} onClick={() => setPage(page - 1)}>
        上一页
      </button>
      <span> 第 {page} 页 </span>
      <button disabled={page * 20 >= (query.data?.total ?? 0)} onClick={() => setPage(page + 1)}>
        下一页
      </button>
      {pref.data && (
        <AvailabilityForm
          initial={pref.data}
          onSaved={(data) => cache.setQueryData(['interview-availability'], data)}
        />
      )}
    </main>
  );
}
function AvailabilityForm({
  initial,
  onSaved,
}: {
  initial: InterviewAvailability;
  onSaved: (v: InterviewAvailability) => void;
}) {
  const api = useApi();
  const [value, setValue] = useState(initial);
  const op = useReliableWrite<
    Omit<InterviewAvailability, 'version'> & { expected_version: number },
    InterviewAvailability
  >(
    (body, opts) => api.saveInterviewAvailability(body, opts),
    (result) => {
      setValue(result);
      onSaved(result);
    },
  );
  const labels = {
    start_hour: '可面开始小时',
    end_hour: '可面结束小时',
    daily_limit: '每日场次上限',
    weekly_limit: '每周场次上限',
    buffer_minutes: '前后缓冲分钟',
  };
  return (
    <section className="rm-card">
      <h2>我的可面设置</h2>
      <p>工作时段使用北京时间；只约束本系统排期，外部日历由 HR 核实。</p>
      <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
        {['周一', '周二', '周三', '周四', '周五', '周六', '周日'].map((label, n) => (
          <label key={n} style={{ display: 'inline-block', margin: 6 }}>
            <input
              type="checkbox"
              checked={value.weekdays.includes(n)}
              onChange={(e) =>
                setValue({
                  ...value,
                  weekdays: e.target.checked
                    ? [...value.weekdays, n]
                    : value.weekdays.filter((v) => v !== n),
                })
              }
            />
            {label}
          </label>
        ))}
        {(Object.keys(labels) as (keyof typeof labels)[]).map((key) => (
          <label key={key} style={{ display: 'block', marginBlock: 12 }}>
            {labels[key]}{' '}
            <input
              aria-label={labels[key]}
              type="number"
              value={value[key]}
              onChange={(e) => setValue({ ...value, [key]: Number(e.target.value) })}
              style={{ width: 80 }}
            />
          </label>
        ))}
        <button
          onClick={() => {
            const { version, ...body } = value;
            void op.submit({ ...body, expected_version: version });
          }}
        >
          保存可面设置
        </button>
      </fieldset>
      {op.error && <p role="alert">{op.error}</p>}
      {op.retry && <button onClick={op.retryAction}>重试本次操作</button>}
      {op.conflict && (
        <button
          onClick={async () => {
            const latest = await api.interviewAvailability();
            setValue((v) => ({ ...v, version: latest.version }));
            op.refreshed();
          }}
        >
          刷新设置版本
        </button>
      )}
    </section>
  );
}
export function InterviewPage() {
  const { id = '' } = useParams();
  const api = useApi();
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ['biz-interview', id],
    queryFn: () => api.liveInterview(id),
    refetchInterval: 5000,
  });
  return (
    <main style={{ padding: 16 }}>
      <Link to="/interviews">返回我的面试</Link>
      {query.isError ? (
        <p role="alert">{toAppError(query.error).message}</p>
      ) : query.data ? (
        <InterviewDetails
          key={id}
          interview={query.data}
          refresh={query.refetch}
          onUpdated={(iv) => {
            cache.setQueryData(['biz-interview', id], iv);
            void cache.invalidateQueries({ queryKey: ['biz-interviews'] });
          }}
        />
      ) : (
        <p>正在加载…</p>
      )}
    </main>
  );
}
