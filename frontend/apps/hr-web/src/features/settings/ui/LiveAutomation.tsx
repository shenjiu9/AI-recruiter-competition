import { useState } from 'react';
import { useSession } from '@recruiter/auth';
import {
  useApi,
  useReliableWrite,
  type AutomationConfig,
  type AutomationCommand,
} from '@recruiter/api-client';
import { useLiveData } from '@recruiter/ui-kit/live-hiring';

export function LiveAutomation() {
  const api = useApi();
  const session = useSession();
  const [scope, setScope] = useState(session?.roles.includes('admin') ? 'global' : 'position');
  const [target, setTarget] = useState('');
  const [dept, setDept] = useState('');
  const query = useLiveData(JSON.stringify([scope, target, dept]), () =>
    api.liveAutomation({ scope, target, dept }),
  );
  return (
    <main style={{ maxWidth: 1000 }}>
      <h1>自动化策略与录用审批规则</h1>
      <p>
        配置按全局 → 部门序列 → 岗位覆盖。淘汰最高 L2，录用建议固定 L1；录用决定和审批始终由人完成。
      </p>
      <p>
        配置 Dify
        工作流并启动后台任务后，正常模式按策略执行；影子模式只记录结果。当前支持沟通回复和证据评估的
        L3 执行，其他组件提供待复核建议。<a href="/ai-jobs">查看连接状态与任务</a>
      </p>
      <label>
        配置范围{' '}
        <select aria-label="配置范围" value={scope} onChange={(e) => setScope(e.target.value)}>
          {session?.roles.includes('admin') && <option value="global">全局</option>}
          <option value="series">部门序列</option>
          <option value="position">岗位</option>
        </select>
      </label>
      {scope === 'series' && (
        <label>
          部门{' '}
          <input aria-label="策略部门" value={dept} onChange={(e) => setDept(e.target.value)} />
        </label>
      )}
      {scope !== 'global' && (
        <label>
          {scope === 'position' ? '岗位编号' : '序列名称'}{' '}
          <input aria-label="策略对象" value={target} onChange={(e) => setTarget(e.target.value)} />
        </label>
      )}
      {query.error && <p role="alert">{query.error}</p>}
      {query.data && (
        <Configuration
          key={query.data.id}
          initial={query.data}
          filters={{ scope, target, dept }}
          refresh={query.refresh}
          update={query.update}
        />
      )}
    </main>
  );
}
function Configuration({
  initial,
  filters,
  refresh,
  update,
}: {
  initial: AutomationConfig;
  filters: { scope: string; target: string; dept: string };
  refresh: () => Promise<AutomationConfig | undefined>;
  update: (v: AutomationConfig) => void;
}) {
  const api = useApi();
  const [draft, setDraft] = useState(initial);
  const op = useReliableWrite<AutomationCommand, AutomationConfig>(
    (b, o) => api.saveLiveAutomation(b, o),
    (v) => {
      setDraft(v);
      update(v);
    },
  );
  const save = (restore_version?: number) =>
    void op.submit({
      expected_version: draft.version,
      ...filters,
      ...(restore_version
        ? { restore_version }
        : {
            levels: draft.levels,
            ...(filters.scope === 'global'
              ? {
                  mode: draft.mode,
                  components: draft.components,
                  low_threshold: draft.low_threshold,
                  high_threshold: draft.high_threshold,
                  approval_nodes: draft.approval_nodes,
                  hrd_grade: draft.hrd_grade,
                }
              : {}),
          }),
    });
  return (
    <section style={{ background: '#fff', padding: 20, marginBlock: 16 }}>
      <p>版本 {draft.version}</p>
      <fieldset disabled={op.locked} style={{ border: 0, padding: 0 }}>
        {draft.nodes.map((n) => (
          <label style={{ display: 'block', marginBlock: 12 }} key={n.key}>
            {n.name}{' '}
            <select
              aria-label={`${n.name}等级`}
              value={draft.levels[n.key] ?? ''}
              onChange={(e) => {
                const levels = { ...draft.levels };
                if (e.target.value) levels[n.key] = Number(e.target.value);
                else delete levels[n.key];
                setDraft({ ...draft, levels });
              }}
            >
              {filters.scope !== 'global' && <option value="">继承上层配置</option>}
              {Array.from({ length: n.max - n.min + 1 }, (_, i) => i + n.min).map((l) => (
                <option key={l} value={l}>
                  L{l}
                </option>
              ))}
            </select>
          </label>
        ))}
        {filters.scope === 'global' && (
          <>
            <label>
              运行模式{' '}
              <select
                aria-label="运行模式"
                value={draft.mode}
                onChange={(e) =>
                  setDraft({ ...draft, mode: e.target.value as AutomationConfig['mode'] })
                }
              >
                <option value="manual">纯人工（有效等级 L1）</option>
                <option value="shadow">影子模式（仅建议）</option>
                <option value="normal">按配置策略</option>
              </select>
            </label>
            <p>
              把握阈值{' '}
              <label>
                低{' '}
                <input
                  aria-label="低把握阈值"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={draft.low_threshold}
                  onChange={(e) => setDraft({ ...draft, low_threshold: Number(e.target.value) })}
                />
              </label>{' '}
              <label>
                高{' '}
                <input
                  aria-label="高把握阈值"
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={draft.high_threshold}
                  onChange={(e) => setDraft({ ...draft, high_threshold: Number(e.target.value) })}
                />
              </label>
            </p>
            <p>组件开关（配置预留）</p>
            {Object.entries(draft.components).map(([name, on]) => (
              <label style={{ marginRight: 16 }} key={name}>
                <input
                  type="checkbox"
                  checked={on}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      components: { ...draft.components, [name]: e.target.checked },
                    })
                  }
                />
                {name}
              </label>
            ))}
            <h2>录用审批规则</h2>
            <p>
              新提交生效，在途审批保持提交快照。超带宽或达到高职级阈值时强制追加
              HRD；不允许本人审批。
            </p>
            {(['director', 'hrbp'] as const).map((role) => (
              <label style={{ marginRight: 16 }} key={role}>
                <input
                  type="checkbox"
                  checked={draft.approval_nodes.includes(role)}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      approval_nodes: e.target.checked
                        ? [...draft.approval_nodes, role]
                        : draft.approval_nodes.filter((r) => r !== role),
                    })
                  }
                />
                {role === 'director' ? '部门负责人审批' : 'HRBP 审批'}
              </label>
            ))}
            <p>
              <label>
                HRD 加签职级数字阈值{' '}
                <input
                  aria-label="HRD 职级阈值"
                  type="number"
                  min="1"
                  max="20"
                  value={draft.hrd_grade}
                  onChange={(e) => setDraft({ ...draft, hrd_grade: Number(e.target.value) })}
                />
              </label>
            </p>
          </>
        )}
        <p>
          <button onClick={() => save()}>保存策略配置</button>
        </p>
        <h2>历史版本</h2>
        {draft.history.map((h) => (
          <p key={h.version}>
            版本 {h.version} · {new Date(h.at).toLocaleString()}{' '}
            <button onClick={() => save(h.version)}>恢复版本 {h.version} 为新版本</button>
          </p>
        ))}
      </fieldset>
      {op.error && <p role="alert">{op.error}</p>}
      {op.retry && <button onClick={op.retryAction}>重试本次操作</button>}
      {op.conflict && (
        <button
          onClick={async () => {
            const latest = await refresh();
            if (latest) {
              setDraft((v) => ({ ...v, version: latest.version }));
              op.refreshed();
            }
          }}
        >
          刷新策略版本
        </button>
      )}
    </section>
  );
}
