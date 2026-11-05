import { Segmented, Table } from 'antd';
import type { AutomationNode, Level } from '@recruiter/domain';

const LEVEL_TEXT: Record<Level, string> = { 1: 'L1 只建议', 2: 'L2 需确认', 3: 'L3 自动' };

/** 各环节自动化等级；硬性上限由后端策略引擎强制，这里只禁用不允许的选项（PRD 5.2、14.1） */
export function AutomationTable({ rows, loading, onChange }: { rows: AutomationNode[]; loading: boolean; onChange: (key: string, level: Level) => void }) {
  return (
    <Table<AutomationNode>
      rowKey="key"
      loading={loading}
      dataSource={rows}
      pagination={false}
      columns={[
        { title: '环节', render: (_, n) => <strong style={{ fontWeight: 500 }}>{n.name}</strong>, width: 180 },
        {
          title: '等级',
          width: 340,
          render: (_, n) => (
            <Segmented<Level>
              aria-label={`${n.name}的自动化等级`}
              value={n.level}
              onChange={(v) => onChange(n.key, v)}
              options={([1, 2, 3] as Level[]).map((l) => ({ value: l, label: LEVEL_TEXT[l], disabled: !n.allowed.includes(l) }))}
            />
          ),
        },
        { title: '上限', width: 100, render: (_, n) => n.cap ?? <span className="muted">无</span> },
        { title: '说明', dataIndex: 'note' },
      ]}
    />
  );
}
