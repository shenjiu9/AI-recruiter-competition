import { CloseOutlined, ExpandOutlined, RobotOutlined } from '@ant-design/icons';
import { Button, Drawer, Skeleton } from 'antd';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toAppError, useApi, type LiveWorkbench } from '@recruiter/api-client';
import { Conversation } from './Chat';
import { useAssistant } from './state';

const live = import.meta.env.VITE_USE_MOCK === 'false';

/** 助手页右侧：今天的数字和岗位进度。点哪一项就把对应问题发给助手。 */
export function AssistantRail() {
  const api = useApi();
  const { send, busy } = useAssistant();
  const [data, setData] = useState<LiveWorkbench>();
  const [error, setError] = useState('');
  useEffect(() => {
    if (!live) return;
    let alive = true;
    const load = () =>
      api
        .liveWorkbench()
        .then((d) => alive && (setData(d), setError('')))
        .catch((e) => alive && setError(toAppError(e).message));
    void load();
    const timer = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [api]);
  if (!live)
    return (
      <aside className="as-rail">
        <div className="as-card">
          <p className="as-muted">
            演示模式没有连接后端。用 VITE_USE_MOCK=false 启动后，这里显示今日数据。
          </p>
        </div>
      </aside>
    );
  const c = data?.counts;
  const tiles: { label: string; value?: number; ask: string; tone?: string }[] = [
    {
      label: '待处理决策',
      value: c?.cards,
      ask: '今天有什么要处理',
      tone: c?.cards ? 'warning' : '',
    },
    { label: '还差人数', value: c?.remaining, ask: '岗位招聘进度' },
    {
      label: '待我审批',
      value: c?.my_approvals,
      ask: '今天有什么要处理',
      tone: c?.my_approvals ? 'warning' : '',
    },
    {
      label: '待移交 / 回填',
      value: (c?.pending_handoffs ?? 0) + (c?.pending_results ?? 0),
      ask: '录用进展',
    },
  ];
  return (
    <aside className="as-rail" aria-label="今日看板">
      <div className="as-card">
        <div className="as-card-h">
          <span className="as-card-title">今日看板</span>
          <span className="as-muted as-push">点击即问助手</span>
        </div>
        {error && (
          <p role="alert" className="as-error">
            {error}
          </p>
        )}
        {!data && !error ? (
          <Skeleton active paragraph={{ rows: 2 }} />
        ) : (
          <div className="as-metrics as-metrics-2">
            {tiles.map((t) => (
              <button
                key={t.label}
                type="button"
                className={`as-metric as-metric-btn${t.tone ? ' as-tone-' + t.tone : ''}`}
                onClick={() => send(t.ask)}
                disabled={busy}
              >
                <div className="as-metric-v num">{t.value ?? 0}</div>
                <div className="as-metric-l">{t.label}</div>
              </button>
            ))}
          </div>
        )}
      </div>
      {!!data?.positions.length && (
        <div className="as-card">
          <div className="as-card-h">
            <span className="as-card-title">岗位进度</span>
          </div>
          <ul className="as-rows">
            {data.positions.slice(0, 8).map((p) => (
              <li key={p.id} className="as-row">
                <button
                  type="button"
                  className="as-pos"
                  onClick={() => send(`${p.name}还差几个人`)}
                  disabled={busy}
                >
                  <span className="as-pos-name">{p.name}</span>
                  <span className="as-pos-bar" aria-hidden>
                    <span style={{ width: `${p.planned ? (p.hired / p.planned) * 100 : 0}%` }} />
                  </span>
                  <span className="as-pos-num num">
                    {p.hired}/{p.planned}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="as-card as-tips">
        <div className="as-card-title">换个说法也行</div>
        <ul>
          <li>“张三到哪一步了” → 推进 / 评估 / 回复都能接着说“他”</li>
          <li>“给张三发消息：明天上午 10 点电话沟通”</li>
          <li>“整理李四的面试记录：（粘贴原文）”</li>
          <li>“客服专员为什么招得慢”</li>
        </ul>
      </div>
    </aside>
  );
}

/** 其他页面右侧的助手面板：不遮挡页面，可边看详情边对话 */
export function AssistantDock() {
  const { open, setOpen } = useAssistant();
  const nav = useNavigate();
  return (
    <Drawer
      open={open}
      onClose={() => setOpen(false)}
      mask={false}
      placement="right"
      width={440}
      className="as-dock"
      closable={false}
      styles={{
        body: { padding: 0, display: 'flex', flexDirection: 'column' },
        wrapper: { maxWidth: '100vw' },
      }}
      title={
        <div className="as-dock-h">
          <RobotOutlined aria-hidden className="as-ai-icon" />
          <span>AI 招聘助手</span>
          <Button
            size="small"
            type="text"
            icon={<ExpandOutlined />}
            aria-label="全屏打开助手"
            onClick={() => {
              setOpen(false);
              nav('/assistant');
            }}
          />
          <Button
            size="small"
            type="text"
            icon={<CloseOutlined />}
            aria-label="关闭助手"
            onClick={() => setOpen(false)}
          />
        </div>
      }
    >
      <Conversation compact />
    </Drawer>
  );
}
