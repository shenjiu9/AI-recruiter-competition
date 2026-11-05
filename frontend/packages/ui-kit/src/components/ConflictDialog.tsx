import { Modal, Table } from 'antd';

export interface DiffRow {
  field: string;
  mine: string;
  theirs: string;
}

/** 乐观锁冲突：展示“已被 XX 修改”和差异，让用户选择覆盖或放弃（PRD 5.9） */
export function ConflictDialog({ open, by, rows, onOverwrite, onDiscard }: { open: boolean; by: string; rows: DiffRow[]; onOverwrite: () => void; onDiscard: () => void }) {
  return (
    <Modal open={open} title={`已被${by}修改`} onCancel={onDiscard} onOk={onOverwrite} okText="用我的修改覆盖" cancelText="放弃我的修改" width={560}>
      <p style={{ marginBottom: 12 }}>你编辑期间，{by}保存了新的内容。下面是两边不同的字段：</p>
      <Table
        size="small"
        pagination={false}
        rowKey="field"
        dataSource={rows}
        columns={[
          { title: '字段', dataIndex: 'field', width: 96 },
          { title: '我的修改', dataIndex: 'mine' },
          { title: `${by}的修改`, dataIndex: 'theirs' },
        ]}
      />
    </Modal>
  );
}
