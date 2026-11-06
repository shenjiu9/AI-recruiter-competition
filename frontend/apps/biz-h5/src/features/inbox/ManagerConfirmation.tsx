import { Button, TextArea } from 'antd-mobile';
import { DirectoryPersonPicker } from '@recruiter/ui-kit/directory-person-picker';
import {
  CONFIRMATION_FIELDS,
  confirmationFieldLabel,
  useConfirmation,
  type RequisitionDetail,
} from '@recruiter/api-client';

export function ManagerConfirmation({
  req,
  onSuccess,
}: {
  req: RequisitionDetail;
  onSuccess: () => void;
}) {
  const form = useConfirmation(req, onSuccess);
  return (
    <section>
      <h3>修改并确认</h3>
      <p>核对字段后确认。部门、保密范围和负责 HR 如需变更，请撤回修改。</p>
      <fieldset disabled={form.locked} style={{ border: 0, padding: 0, minWidth: 0 }}>
        {CONFIRMATION_FIELDS.map((field) => (
          <div key={field.key} style={{ marginBottom: 16 }}>
            <label htmlFor={`confirm-${field.key}`}>{field.label}</label>
            {field.key === 'reportTo' ? (
              <DirectoryPersonPicker
                id="confirm-reportTo"
                label="汇报对象"
                dept={req.dept}
                requisitionId={req.id}
                value={form.fields.reportToId ? [form.fields.reportToId] : []}
                legacyName={form.fields.reportTo}
                disabled={form.locked}
                onChange={(ids, name) => form.changeReporting(ids[0] ?? '', name)}
              />
            ) : field.options ? (
              <select
                id={`confirm-${field.key}`}
                style={{ width: '100%', padding: 8 }}
                value={form.fields[field.key]}
                onChange={(e) => form.change(field.key, e.target.value)}
              >
                {field.options.map((option) => (
                  <option key={option}>{option}</option>
                ))}
              </select>
            ) : (
              <TextArea
                id={`confirm-${field.key}`}
                autoSize={{ minRows: 1, maxRows: 6 }}
                value={form.fields[field.key] ?? ''}
                onChange={(value) => form.change(field.key, value)}
              />
            )}
          </div>
        ))}
      </fieldset>
      {form.error && <p role="alert">{form.error}</p>}
      {form.preview ? (
        <>
          <h3>本次修改</h3>
          {Object.entries(form.preview.changes).map(([key, value]) => (
            <p key={key}>
              {confirmationFieldLabel(key)}：{value.before || '空'} → {value.after || '空'}
            </p>
          ))}
          {!Object.keys(form.preview.changes).length && <p>按原内容确认</p>}
          {form.preview.checks
            .filter((c) => c.status !== 'pass')
            .map((c) => (
              <p role={c.status === 'block' ? 'alert' : undefined} key={c.key}>
                {c.label}：{c.detail}
              </p>
            ))}
          <h3>确认后的审批链</h3>
          <p>
            {form.preview.chain
              .slice(1)
              .map((node) => `${node.name}（${node.approver}）`)
              .join(' → ')}
          </p>
        </>
      ) : (
        !form.error && <p>正在预检…</p>
      )}
      <Button
        block
        color="primary"
        loading={form.busy}
        disabled={!form.canSubmit}
        onClick={() => void form.submit()}
      >
        {form.retry ? '重试本次确认' : '确认并继续审批'}
      </Button>
    </section>
  );
}
