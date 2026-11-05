import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Alert, Button, Form, Input, InputNumber, Modal, Space, Table, Tag } from 'antd';
import {
  useApi,
  type SalaryBand,
  type SalaryBandCommand,
  type SalaryRevision,
} from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { PageHeader } from '../shared/PageHeader';
import { useWrite } from '../shared/useWrite';

const bandText = (r: SalaryRevision | null) =>
  r ? `${r.lower}–${r.upper}K/月 × ${r.months}` : '尚未生效';

export function SalarySettingsPage() {
  const api = useApi();
  const session = useSession();
  const allowed = session?.roles.some((r) => r === 'recruiting_lead' || r === 'compensation_owner');
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<SalaryBand | 'new' | null>(null);
  const [historyId, setHistoryId] = useState<string>();
  const [form] = Form.useForm<SalaryBandCommand>();
  const query = useQuery({
    queryKey: ['salary-bands', page],
    queryFn: () => api.salaryBands(page, 20),
    enabled: !!allowed,
  });
  const history = useQuery({
    queryKey: ['salary-history', historyId],
    queryFn: () => api.salaryHistory(historyId!),
    enabled: !!allowed && !!historyId,
  });
  const save = useWrite((command: SalaryBandCommand, opts) => api.saveSalaryBand(command, opts), {
    invalidate: [['salary-bands'], ['salary-history']],
    success: '薪资版本已保存',
  });
  const open = (row?: SalaryBand) => {
    setEditing(row ?? 'new');
    form.resetFields();
    form.setFieldsValue({
      series: row?.series ?? '',
      grade: row?.grade ?? '',
      city: row?.city ?? '',
      lower: row?.latest.lower ?? 5,
      upper: row?.latest.upper ?? 20,
      months: row?.latest.months ?? 13,
      effective_from: new Date().toISOString().slice(0, 10),
      expected_version: row?.version ?? 0,
    });
    save.reset();
  };
  if (!allowed)
    return <Alert type="warning" message="仅招聘负责人或薪酬负责人可以维护职级薪资表" />;
  return (
    <>
      <PageHeader
        title="职级薪资表"
        sub="按序列、单个职级和城市维护；每次保存生成新版本，保留历史。"
        extra={
          <Button type="primary" onClick={() => open()}>
            新增薪资配置
          </Button>
        }
      />
      <Alert
        style={{ marginBottom: 16 }}
        type="info"
        showIcon
        message="缺少生效配置将阻止需求提交；月薪或年薪越界将独立加签 HRD。"
        description="职级范围需要每一级均有配置。未来生效版本不会提前影响新需求，已提交需求保留原审批链。发布立即生效的新版本会替代所有旧版本（包括旧预约版本）。"
      />
      {query.error && (
        <Alert
          type="error"
          message={query.error.message}
          action={<Button onClick={() => void query.refetch()}>重新加载</Button>}
        />
      )}
      <Table<SalaryBand>
        rowKey="id"
        dataSource={query.data?.items}
        loading={query.isPending}
        scroll={{ x: 1000 }}
        pagination={{
          current: page,
          pageSize: 20,
          total: query.data?.total,
          showSizeChanger: false,
          onChange: setPage,
        }}
        columns={[
          { title: '序列', dataIndex: 'series' },
          { title: '职级', dataIndex: 'grade' },
          { title: '城市', dataIndex: 'city' },
          {
            title: '当前生效带宽',
            render: (_, row) => (
              <>
                {bandText(row.active)}
                {row.active && (
                  <div>
                    v{row.active.version} · {row.active.effective_from}
                  </div>
                )}
              </>
            ),
          },
          {
            title: '最新版本',
            render: (_, row) => (
              <>
                {bandText(row.latest)}
                <div>
                  v{row.version} · {row.latest.effective_from}
                </div>
              </>
            ),
          },
          {
            title: '状态',
            render: (_, row) => (
              <Space>
                {row.active ? <Tag color="green">可用</Tag> : <Tag color="orange">待生效</Tag>}
                {row.stale && <Tag color="orange">数据可能过期</Tag>}
              </Space>
            ),
          },
          {
            title: '操作',
            render: (_, row) => (
              <Space>
                <Button onClick={() => open(row)}>发布新版本</Button>
                <Button onClick={() => setHistoryId(row.id)}>版本历史</Button>
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editing === 'new' ? '新增薪资配置' : '发布薪资新版本'}
        open={!!editing}
        forceRender
        onCancel={() => !save.isPending && setEditing(null)}
        okText="保存薪资版本"
        cancelText="取消"
        confirmLoading={save.isPending}
        onOk={() => form.submit()}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => save.mutate(values, { onSuccess: () => setEditing(null) })}
        >
          <Form.Item name="series" label="职位序列" rules={[{ required: true, whitespace: true }]}>
            <Input maxLength={80} disabled={editing !== 'new'} />
          </Form.Item>
          <Form.Item name="grade" label="单个职级" rules={[{ required: true, whitespace: true }]}>
            <Input
              maxLength={40}
              placeholder="例如 P3；范围需按职级逐条配置"
              disabled={editing !== 'new'}
            />
          </Form.Item>
          <Form.Item name="city" label="城市" rules={[{ required: true, whitespace: true }]}>
            <Input maxLength={80} disabled={editing !== 'new'} />
          </Form.Item>
          <Form.Item name="lower" label="月薪下限（K）" rules={[{ required: true }]}>
            <InputNumber min={0.01} max={1000} precision={2} />
          </Form.Item>
          <Form.Item name="upper" label="月薪上限（K）" rules={[{ required: true }]}>
            <InputNumber min={0.01} max={1000} precision={2} />
          </Form.Item>
          <Form.Item name="months" label="发薪月数" rules={[{ required: true }]}>
            <InputNumber min={1} max={24} precision={0} />
          </Form.Item>
          <Form.Item name="effective_from" label="生效日期" rules={[{ required: true }]}>
            <Input type="date" min={new Date().toISOString().slice(0, 10)} />
          </Form.Item>
          <Form.Item name="expected_version" hidden>
            <InputNumber />
          </Form.Item>
          {save.error && (
            <Alert
              type="error"
              message={save.error.message}
              description="若发生版本冲突，请关闭窗口并重新打开，核对最新内容后再提交。"
            />
          )}
        </Form>
      </Modal>
      <Modal
        title="薪资版本历史"
        open={!!historyId}
        onCancel={() => setHistoryId(undefined)}
        footer={null}
        width={760}
      >
        {history.error && <Alert type="error" message={history.error.message} />}
        <Table<SalaryRevision>
          rowKey="version"
          loading={history.isPending}
          dataSource={history.data}
          pagination={{ pageSize: 10 }}
          columns={[
            { title: '版本', dataIndex: 'version' },
            { title: '薪资', render: (_, row) => bandText(row) },
            { title: '生效日期', dataIndex: 'effective_from' },
            { title: '维护日期', dataIndex: 'updated_on' },
          ]}
        />
      </Modal>
    </>
  );
}
