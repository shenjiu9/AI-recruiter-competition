import { Alert, Button, TreeSelect } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { useApi, toAppError } from '@recruiter/api-client';

export function DepartmentPicker({
  value,
  requisitionId,
  onChange,
}: {
  value: string;
  requisitionId?: string;
  onChange: (value: string) => void;
}) {
  const api = useApi();
  const query = useQuery({
    queryKey: ['requisition-form', 'departments', requisitionId],
    queryFn: () => api.formDepartments(requisitionId),
  });
  return (
    <>
      <TreeSelect
        id="f-dept"
        style={{ width: '100%' }}
        showSearch
        treeDefaultExpandAll
        treeNodeFilterProp="title"
        treeDataSimpleMode={{ id: 'id', pId: 'parent_id', rootPId: '' }}
        treeData={(query.data ?? []).map((d) => ({
          ...d,
          parent_id: d.parent_id ?? '',
          value: d.id,
          title: d.id,
        }))}
        loading={query.isFetching}
        disabled={!query.data || query.isError}
        value={value || undefined}
        placeholder="选择需求部门"
        onChange={onChange}
      />
      {query.isError && (
        <Alert
          type="error"
          role="alert"
          message={toAppError(query.error).message}
          action={<Button onClick={() => void query.refetch()}>重试部门目录</Button>}
        />
      )}
      {value && query.data && !query.data.some((d) => d.id === value) && (
        <Alert type="warning" message="原部门已失效或超出可选范围，请重新选择" />
      )}
    </>
  );
}
