import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Checkbox,
  Descriptions,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
} from 'antd';
import {
  useApi,
  isConflict,
  toAppError,
  type OrganizationDepartment,
  type OrganizationUser,
  type ApprovalPolicyCommand,
  type PermissionCommand,
} from '@recruiter/api-client';
import { useSession } from '@recruiter/auth';
import { useWrite } from '../shared/useWrite';
import { PageHeader } from '../shared/PageHeader';

const ROLES: Record<string, string> = {
  admin: '系统管理员',
  recruiting_lead: '招聘负责人',
  recruiter: '招聘 HR',
  hrbp: 'HRBP',
  headcount_owner: '编制负责人',
  hrd: 'HRD',
  compensation_owner: '薪酬负责人',
  interviewer: '面试官',
  hiring_manager: '用人经理（目录）',
};
const ASSIGNED = Object.entries(ROLES)
  .filter(([key]) => key !== 'hiring_manager')
  .map(([value, label]) => ({ value, label }));
const NODES = {
  director_id: '部门负责人',
  hrbp_id: 'HRBP',
  hc_owner_id: '编制负责人',
  hrd_id: 'HRD',
} as const;

function DirectorySelect({
  value,
  onChange,
  id,
  disabled,
}: {
  value?: string;
  onChange?: (v: string) => void;
  id?: string;
  disabled?: boolean;
}) {
  const api = useApi();
  const [search, setSearch] = useState('');
  const users = useQuery({
    queryKey: ['organization', 'picker', search],
    queryFn: () => api.organizationUsers(1, 100, search),
  });
  return (
    <Select
      id={id}
      value={value}
      onChange={onChange}
      disabled={disabled}
      showSearch
      filterOption={false}
      onSearch={setSearch}
      loading={users.isFetching}
      notFoundContent={users.error?.message ?? '未找到在职人员'}
      options={users.data?.items
        .filter((u) => u.active)
        .map((u) => ({ value: u.id, label: `${u.name} (${u.id})` }))}
    />
  );
}

export function OrganizationSettingsPage() {
  const api = useApi();
  const session = useSession();
  const admin = session?.roles.includes('admin');
  const allowed = admin || session?.roles.includes('recruiting_lead');
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [editingUser, setEditingUser] = useState<OrganizationUser>();
  const [editingDept, setEditingDept] = useState<OrganizationDepartment>();
  const [historyTarget, setHistoryTarget] = useState<{
    kind: 'permissions' | 'approval';
    id: string;
  }>();
  const [historyPage, setHistoryPage] = useState(1);
  const [trial, setTrial] = useState<OrganizationDepartment>();
  const [actor, setActor] = useState('');
  const [hc, setHc] = useState(false);
  const [salary, setSalary] = useState(false);
  const [permissionForm] = Form.useForm<PermissionCommand>();
  const [policyForm] = Form.useForm<ApprovalPolicyCommand>();
  const departments = useQuery({
    queryKey: ['organization', 'departments'],
    queryFn: () => api.organizationDepartments(),
    enabled: !!allowed,
  });
  const users = useQuery({
    queryKey: ['organization', 'users', page, search],
    queryFn: () => api.organizationUsers(page, 20, search),
    enabled: !!allowed,
  });
  const history = useQuery({
    queryKey: ['organization', 'history', historyTarget, historyPage],
    queryFn: () => api.organizationHistory(historyTarget!.kind, historyTarget!.id, historyPage),
    enabled: !!allowed && !!historyTarget,
  });
  const preview = useQuery({
    queryKey: ['organization', 'trial', trial?.id, actor, hc, salary],
    queryFn: () => api.trialApproval(trial!.id, actor, hc, salary),
    enabled: !!trial && !!actor,
  });
  const permissionSave = useWrite(
    (command: PermissionCommand, opts) => api.savePermissions(editingUser!.id, command, opts),
    { invalidate: [['organization']], success: '权限已保存，下次请求按新权限校验' },
  );
  const policySave = useWrite(
    (command: ApprovalPolicyCommand, opts) =>
      api.saveApprovalPolicy(editingDept!.id, command, opts),
    { invalidate: [['organization']], success: '审批配置已发布，仅影响新提交的需求' },
  );
  const locked = (error: unknown, pending: boolean) =>
    pending ||
    (!!error &&
      (isConflict(error) || toAppError(error).status === 0 || toAppError(error).status >= 500));
  const openUser = (user: OrganizationUser, values = user) => {
    setEditingUser(user);
    permissionSave.reset();
    permissionForm.resetFields();
    permissionForm.setFieldsValue({
      expected_version: user.version,
      roles: values.roles.filter((r) => r !== 'hiring_manager'),
      departments: values.departments,
    });
  };
  const openDept = (dept: OrganizationDepartment, values = dept) => {
    setEditingDept(dept);
    policySave.reset();
    policyForm.resetFields();
    policyForm.setFieldsValue({
      expected_version: dept.version,
      ...Object.fromEntries(
        Object.keys(NODES).map((key) => [key, values.policy[key as keyof typeof NODES] ?? '']),
      ),
    });
  };
  const showHistory = (kind: 'permissions' | 'approval', id: string) => {
    setHistoryPage(1);
    setHistoryTarget({ kind, id });
  };
  if (!allowed) return <Alert type="warning" message="仅系统管理员和招聘负责人可查看组织配置" />;
  return (
    <>
      <PageHeader
        title="组织与权限"
        sub="组织、人员和用人经理来自通讯录；在此维护角色授权与招聘需求审批配置。"
      />
      <Alert
        type="info"
        showIcon
        message={
          admin
            ? '管理员维护配置；单独的管理员角色不授予招聘业务查看权。'
            : '当前为只读模式，仅展示授权部门。'
        }
        description="目录同步接入尚未完成，当前展示已导入目录。部门授权包含下级；目录派生角色不会被手动授权覆盖。"
        style={{ marginBottom: 16 }}
      />
      {(users.error || departments.error) && (
        <Alert type="error" message={(users.error || departments.error)?.message} />
      )}
      <Tabs
        items={[
          {
            key: 'departments',
            label: '组织与审批配置',
            children: (
              <Table<OrganizationDepartment>
                rowKey="id"
                dataSource={departments.data}
                loading={departments.isPending}
                scroll={{ x: 1350 }}
                columns={[
                  { title: '部门', dataIndex: 'id', fixed: 'left', width: 170 },
                  { title: '上级部门', dataIndex: 'parent_id', render: (v) => v || '—' },
                  {
                    title: '用人经理',
                    render: (_, d) => (
                      <span title={d.policy.manager_id}>
                        {d.approver_names?.manager_id ?? d.policy.manager_id}
                      </span>
                    ),
                  },
                  ...Object.entries(NODES).map(([key, title]) => ({
                    title,
                    render: (_: unknown, d: OrganizationDepartment) => (
                      <span title={d.policy[key as keyof typeof NODES] ?? undefined}>
                        {d.approver_names?.[key] || d.policy[key as keyof typeof NODES] || '未配置'}
                      </span>
                    ),
                  })),
                  { title: '版本', dataIndex: 'version' },
                  {
                    title: '操作',
                    fixed: 'right',
                    width: 270,
                    render: (_, d) => (
                      <Space wrap>
                        {admin && <Button onClick={() => openDept(d)}>配置审批人</Button>}
                        <Button onClick={() => showHistory('approval', d.id)}>配置历史</Button>
                        <Button
                          onClick={() => {
                            setTrial(d);
                            setActor('');
                            setHc(false);
                            setSalary(false);
                          }}
                        >
                          试算
                        </Button>
                      </Space>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: 'users',
            label: '人员与权限',
            children: (
              <>
                <Input.Search
                  aria-label="搜索人员"
                  placeholder="姓名或用户 ID"
                  onSearch={(q) => {
                    setPage(1);
                    setSearch(q);
                  }}
                  style={{ maxWidth: 360, marginBottom: 16 }}
                />
                <Table<OrganizationUser>
                  rowKey="id"
                  dataSource={users.data?.items}
                  loading={users.isPending}
                  pagination={{
                    current: page,
                    pageSize: 20,
                    total: users.data?.total,
                    onChange: setPage,
                    showSizeChanger: false,
                  }}
                  columns={[
                    { title: '人员', render: (_, u) => `${u.name} (${u.id})` },
                    { title: '状态', render: (_, u) => (u.active ? '在职' : '已离职') },
                    {
                      title: '目录角色',
                      render: (_, u) =>
                        u.directory_roles.map((r) => <Tag key={r}>{ROLES[r] ?? r}</Tag>),
                    },
                    {
                      title: '授权角色',
                      render: (_, u) =>
                        u.roles
                          .filter((r) => r !== 'hiring_manager')
                          .map((r) => <Tag key={r}>{ROLES[r] ?? r}</Tag>),
                    },
                    {
                      title: '部门范围（含下级）',
                      render: (_, u) =>
                        [...new Set([...u.directory_departments, ...u.departments])].join('、') ||
                        '无',
                    },
                    { title: '版本', dataIndex: 'version' },
                    {
                      title: '操作',
                      render: (_, u) =>
                        admin && (
                          <Space>
                            <Button disabled={!u.active} onClick={() => openUser(u)}>
                              编辑权限
                            </Button>
                            <Button onClick={() => showHistory('permissions', u.id)}>
                              权限历史
                            </Button>
                          </Space>
                        ),
                    },
                  ]}
                />
              </>
            ),
          },
        ]}
      />
      <Modal
        title={`编辑权限：${editingUser?.name ?? ''}`}
        open={!!editingUser}
        onCancel={() => setEditingUser(undefined)}
        footer={null}
        destroyOnClose
      >
        <p>
          目录角色：{editingUser?.directory_roles.map((r) => ROLES[r] ?? r).join('、') || '无'}
          ；目录部门：{editingUser?.directory_departments.join('、') || '无'}
        </p>
        <Form
          form={permissionForm}
          layout="vertical"
          disabled={locked(permissionSave.error, permissionSave.isPending)}
          onFinish={(values) =>
            permissionSave.mutate(values, { onSuccess: () => setEditingUser(undefined) })
          }
        >
          <Form.Item name="expected_version" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="roles" label="授权角色">
            <Select mode="multiple" options={ASSIGNED} />
          </Form.Item>
          <Form.Item name="departments" label="授权部门（含下级）">
            <Select
              mode="multiple"
              options={departments.data?.map((d) => ({ value: d.id, label: d.id }))}
            />
          </Form.Item>
        </Form>
        {permissionSave.error && (
          <Alert
            type="error"
            message={permissionSave.error.message}
            description={
              isConflict(permissionSave.error)
                ? '输入已保留，请关闭后重新打开核对最新版本。'
                : undefined
            }
          />
        )}
        <Button
          type="primary"
          loading={permissionSave.isPending}
          disabled={isConflict(permissionSave.error)}
          onClick={() => permissionForm.submit()}
        >
          保存权限
        </Button>
      </Modal>
      <Modal
        title={`审批人配置：${editingDept?.id ?? ''}`}
        open={!!editingDept}
        onCancel={() => setEditingDept(undefined)}
        footer={null}
        destroyOnClose
      >
        <p>
          用人经理：{editingDept?.policy.manager_id}
          （通讯录）；保存后生成新版本，在途审批保留原审批人。
        </p>
        <Form
          form={policyForm}
          layout="vertical"
          disabled={locked(policySave.error, policySave.isPending)}
          onFinish={(values) =>
            policySave.mutate(values, { onSuccess: () => setEditingDept(undefined) })
          }
        >
          <Form.Item name="expected_version" hidden>
            <Input />
          </Form.Item>
          {Object.entries(NODES).map(([name, label]) => (
            <Form.Item
              key={name}
              name={name}
              label={label}
              rules={[{ required: true, message: '请选择在职审批人' }]}
            >
              <DirectorySelect disabled={locked(policySave.error, policySave.isPending)} />
            </Form.Item>
          ))}
        </Form>
        {policySave.error && (
          <Alert
            type="error"
            message={policySave.error.message}
            description={
              isConflict(policySave.error)
                ? '输入已保留，请关闭后重新打开核对最新版本。'
                : undefined
            }
          />
        )}
        <Button
          type="primary"
          loading={policySave.isPending}
          disabled={isConflict(policySave.error)}
          onClick={() => policyForm.submit()}
        >
          发布审批配置
        </Button>
      </Modal>
      <Modal
        title="配置历史"
        open={!!historyTarget}
        onCancel={() => setHistoryTarget(undefined)}
        footer={null}
        width={800}
      >
        {history.error && <Alert type="error" message={history.error.message} />}
        <Table
          rowKey="version"
          dataSource={history.data?.items}
          loading={history.isPending}
          pagination={{
            current: historyPage,
            pageSize: 20,
            total: history.data?.total,
            onChange: setHistoryPage,
          }}
          columns={[
            { title: '版本', dataIndex: 'version' },
            {
              title: '记录时间',
              dataIndex: 'at',
              render: (v: string) => new Date(v).toLocaleString(),
            },
            { title: '操作人', dataIndex: 'actor_id', render: (v) => v || '初始快照' },
            {
              title: '配置内容',
              render: (_, r) =>
                'policy' in r.data
                  ? Object.entries(NODES)
                      .map(
                        ([key, label]) =>
                          `${label}：${(r.data as OrganizationDepartment).policy[key as keyof typeof NODES]}`,
                      )
                      .join('；')
                  : `${r.data.roles.map((role) => ROLES[role] ?? role).join('、')} / ${r.data.departments.join('、')}`,
            },
            {
              title: '操作',
              render: (_, r) =>
                admin && (
                  <Button
                    onClick={() => {
                      if ('policy' in r.data) {
                        const current = departments.data?.find((d) => d.id === historyTarget?.id);
                        if (current) openDept(current, r.data);
                      } else {
                        const current = users.data?.items.find((u) => u.id === historyTarget?.id);
                        if (current) openUser(current, r.data);
                      }
                      setHistoryTarget(undefined);
                    }}
                  >
                    以此版本编辑
                  </Button>
                ),
            },
          ]}
        />
      </Modal>
      <Modal
        title={`审批试算：${trial?.id ?? ''}`}
        open={!!trial}
        onCancel={() => setTrial(undefined)}
        footer={null}
        destroyOnClose
      >
        <p>试算已发布配置，不会创建需求；真实提交仍执行编制与薪资预检。</p>
        <Form layout="vertical">
          <Form.Item label="试算发起人">
            <DirectorySelect value={actor || undefined} onChange={setActor} />
          </Form.Item>
        </Form>
        <Space>
          <Checkbox checked={hc} onChange={(e) => setHc(e.target.checked)}>
            申请增编
          </Checkbox>
          <Checkbox checked={salary} onChange={(e) => setSalary(e.target.checked)}>
            薪资超带宽
          </Checkbox>
        </Space>
        {preview.error && <Alert type="error" message={preview.error.message} />}
        {actor && preview.data && (
          <>
            <p>配置版本 {preview.data.version}</p>
            <Descriptions
              column={1}
              items={preview.data.chain.map((n) => ({
                key: n.id,
                label: n.name,
                children: `${n.approver}${n.note ? ` · ${n.note}` : ''}`,
              }))}
            />
          </>
        )}
      </Modal>
    </>
  );
}
