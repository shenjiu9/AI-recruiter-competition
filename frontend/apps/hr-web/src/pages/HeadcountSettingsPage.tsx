import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
} from 'antd';
import { useApi, type HeadcountCommand, type HeadcountPlan } from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { PageHeader } from '../shared/PageHeader';
import { useWrite } from '../shared/useWrite';

export function HeadcountSettingsPage() {
  const api = useApi();
  const session = useSession();
  const allowed = session?.roles.some((r) => r === 'hrbp' || r === 'headcount_owner');
  const [year, setYear] = useState(new Date().getFullYear());
  const [editing, setEditing] = useState<{ dept: string; row?: HeadcountPlan }>();
  const [form] = Form.useForm<HeadcountCommand & { dept: string }>();
  const query = useQuery({
    queryKey: ['headcount', year],
    queryFn: () => api.headcountPlans(year),
    enabled: !!allowed,
  });
  const save = useWrite(
    ({ dept, ...command }: HeadcountCommand & { dept: string }, opts) =>
      api.saveHeadcount(dept, command, opts),
    { invalidate: [['headcount']], success: '编制已保存' },
  );
  const open = (row?: HeadcountPlan) => {
    setEditing({ dept: row?.dept ?? '', row });
    form.setFieldsValue({
      dept: row?.dept ?? '',
      year,
      expected_version: row?.version ?? 0,
      planned: row?.planned ?? 0,
      used: row?.used ?? 0,
      frozen: row?.frozen ?? false,
      effective_from: row?.effective_from ?? `${year}-01-01`,
    });
    save.reset();
  };
  if (!allowed) return <Alert type="warning" message="仅编制负责人或 HRBP 可以维护编制" />;
  return (
    <>
      <PageHeader
        title="编制管理"
        sub="维护部门年度编制，终审通过时预占招聘名额。"
        extra={
          <Space>
            <Select
              aria-label="编制年度"
              value={year}
              onChange={setYear}
              options={[-1, 0, 1, 2].map((offset) => {
                const y = new Date().getFullYear() + offset;
                return { value: y, label: `${y} 年` };
              })}
            />
            <Button
              type="primary"
              onClick={() => open()}
              disabled={!query.data || year < new Date().getFullYear()}
            >
              新增年度编制
            </Button>
          </Space>
        }
      />
      <Alert
        style={{ marginBottom: 16 }}
        type="info"
        showIcon
        message="可用 = 计划 − 已用 − 招聘预占"
        description="审批中的需求在终审前不扣减名额；名额不足会加签编制负责人。外包和实习不占正式编制。冻结后不能提交或完成正式需求审批。"
      />
      {query.error && (
        <Alert
          type="error"
          message={query.error.message}
          action={<Button onClick={() => void query.refetch()}>重试</Button>}
        />
      )}
      <Table<HeadcountPlan>
        rowKey={(r) => `${r.dept}-${r.year}`}
        dataSource={query.data?.items}
        loading={query.isPending}
        pagination={false}
        columns={[
          { title: '部门', dataIndex: 'dept' },
          { title: '计划', dataIndex: 'planned' },
          { title: '已用', dataIndex: 'used' },
          { title: '招聘预占', dataIndex: 'reserved' },
          { title: '可用', dataIndex: 'available' },
          { title: '生效日期', dataIndex: 'effective_from' },
          {
            title: '状态',
            render: (_, row) => (
              <Space>
                {row.frozen ? <Tag color="red">冻结</Tag> : <Tag>未冻结</Tag>}
                {row.stale && <Tag color="orange">数据可能过期</Tag>}
              </Space>
            ),
          },
          { title: '版本 / 维护日期', render: (_, row) => `v${row.version} / ${row.updated_on}` },
          {
            title: '操作',
            render: (_, row) => (
              <Button disabled={year < new Date().getFullYear()} onClick={() => open(row)}>
                维护编制
              </Button>
            ),
          },
        ]}
      />
      <Modal
        title="维护年度编制"
        open={!!editing}
        onCancel={() => !save.isPending && setEditing(undefined)}
        okText="保存编制"
        cancelText="取消"
        confirmLoading={save.isPending}
        onOk={() => form.submit()}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => save.mutate(values, { onSuccess: () => setEditing(undefined) })}
        >
          <Form.Item name="dept" label="部门" rules={[{ required: true }]}>
            <Select
              disabled={!!editing?.row}
              options={query.data?.departments.map((d) => ({ value: d, label: d }))}
            />
          </Form.Item>
          <Form.Item name="year" hidden>
            <InputNumber />
          </Form.Item>
          <Form.Item name="expected_version" hidden>
            <InputNumber />
          </Form.Item>
          <Form.Item name="planned" label="计划编制" rules={[{ required: true }]}>
            <InputNumber min={0} max={1000000} precision={0} />
          </Form.Item>
          <Form.Item name="used" label="已用编制" rules={[{ required: true }]}>
            <InputNumber min={0} max={1000000} precision={0} />
          </Form.Item>
          <Form.Item name="effective_from" label="生效日期" rules={[{ required: true }]}>
            <Input type="date" />
          </Form.Item>
          <Form.Item name="frozen" label="冻结" valuePropName="checked">
            <Switch />
          </Form.Item>
          <p>招聘预占由审批自动记录，不能手工改写。当前预占：{editing?.row?.reserved ?? 0} 人。</p>
          {save.error && (
            <Alert
              type="error"
              message={save.error.message}
              description="若数据已变化，请关闭窗口并重新打开维护，核对最新版本后保存。"
            />
          )}
        </Form>
      </Modal>
    </>
  );
}
