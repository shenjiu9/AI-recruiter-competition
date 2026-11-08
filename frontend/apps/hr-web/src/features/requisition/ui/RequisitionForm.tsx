import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons';
import {
  Alert,
  AutoComplete,
  Form,
  Tooltip,
  App,
  Button,
  Col,
  Input,
  InputNumber,
  Progress,
  Radio,
  Row,
  Select,
  Switch,
  Steps,
} from 'antd';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useApi, toAppError, type RequisitionDetail } from '@recruiter/api-client';
import type { FieldValue, PendingDecision } from '@recruiter/domain';
import { track } from '@recruiter/telemetry';
import { FieldSourceTag, PendingDecisionField } from '@recruiter/ui-kit';
import { DirectoryPersonPicker } from '@recruiter/ui-kit/directory-person-picker';
import { DepartmentPicker } from './DepartmentPicker';
import { usePrecheck, useSaveRequisition, useSubmitRequisition } from '../api';

type Kind = 'text' | 'textarea' | 'number' | 'radio' | 'select';
interface FieldDef {
  key: string;
  label: string;
  kind: Kind;
  required: boolean;
  options?: string[];
  help?: string;
}

const GROUPS: { title: string; fields: FieldDef[] }[] = [
  {
    title: '基本信息',
    fields: [
      {
        key: 'recruitType',
        label: '招聘类型',
        kind: 'radio',
        required: true,
        options: ['社招', '校招', '活水'],
      },
      {
        key: 'dept',
        label: '需求部门',
        kind: 'select',
        required: true,
      },
      {
        key: 'employmentType',
        label: '用工类型',
        kind: 'radio',
        required: true,
        options: ['正式', '外包', '实习'],
        help: '外包、实习不占正式 HC',
      },
      {
        key: 'reqType',
        label: '需求类型',
        kind: 'radio',
        required: true,
        options: ['新增', '替补', '追加'],
      },
      { key: 'headcount', label: '招聘人数', kind: 'number', required: true },
    ],
  },
  {
    title: '职位信息',
    fields: [
      { key: 'title', label: '职位名称', kind: 'text', required: true },
      { key: 'series', label: '职位序列', kind: 'text', required: true },
      { key: 'level', label: '职级范围', kind: 'text', required: true },
      { key: 'city', label: '工作地点', kind: 'text', required: true },
      {
        key: 'reportTo',
        label: '汇报对象',
        kind: 'select',
        required: true,
      },
      {
        key: 'expectedOnboard',
        label: '期望到岗',
        kind: 'text',
        required: true,
        help: 'YYYY-MM-DD，至少提前 7 天',
      },
      {
        key: 'salary',
        label: '薪资带宽',
        kind: 'text',
        required: true,
        help: '例如 8-12K/月×13；仅内部可见',
      },
    ],
  },
  {
    title: '需求说明',
    fields: [{ key: 'reason', label: '招聘原因', kind: 'textarea', required: true }],
  },
  {
    title: '工作内容',
    fields: [
      { key: 'duties', label: '岗位职责', kind: 'textarea', required: true },
      {
        key: 'requirements',
        label: '任职资格',
        kind: 'textarea',
        required: true,
        help: '会做歧视性表述检查',
      },
    ],
  },
];
const REQUIRED = GROUPS.flatMap((g) => g.fields).filter((f) => f.required);

const PRE_ICON = {
  pass: <CheckCircleOutlined style={{ color: 'var(--rc-ok)' }} />,
  warn: <ExclamationCircleOutlined style={{ color: 'var(--rc-warn)' }} />,
  block: <CloseCircleOutlined style={{ color: 'var(--rc-bad)' }} />,
};

const CHECK_FIELDS: Record<string, string[]> = {
  dept: ['dept'],
  count: ['headcount'],
  hc: ['headcount', 'hcRequest'],
  hc_plan: ['headcount'],
  hc_frozen: ['headcount'],
  hc_stale: ['headcount'],
  salary: ['salary'],
  salary_band: ['salary'],
  salary_stale: ['salary'],
  salary_config: ['series', 'level', 'city'],
  onboard: ['expectedOnboard'],
  manager: ['reportTo'],
  visibility: ['visibleTo'],
  discrimination: ['requirements', 'duties', 'title'],
  replacement: ['reqType'],
  position: ['reqType'],
};
const targets = (key: string) => CHECK_FIELDS[key] ?? [key.replace(/^length_/, '')];

/** RQ-02：一张表单 + 右侧固定栏。三种填法都落在同一张表单上，字段带来源标签，待决定项就地给选项。 */
export function RequisitionForm({ initial }: { initial?: RequisitionDetail }) {
  const api = useApi();
  const nav = useNavigate();
  const [fields, setFields] = useState<Record<string, FieldValue>>(() =>
    initial
      ? Object.fromEntries(
          Object.entries(initial.fields).map(([key, value]) => [
            key,
            { value, source: 'edited' as const },
          ]),
        )
      : {
          recruitType: { value: '社招', source: 'default' },
          employmentType: { value: '正式', source: 'default' },
        },
  );
  const [pending, setPending] = useState<PendingDecision[]>([]);
  const [desc, setDesc] = useState('客服中心要招 3 个白班客服，深圳，12 月中到岗');
  const [filling, setFilling] = useState(false);
  const [confidential, setConfidential] = useState(initial?.fields.confidential === '1');
  const { message } = App.useApp();
  const flat = useMemo<Record<string, string>>(
    () => ({
      ...Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.value])),
      confidential: confidential ? '1' : '',
    }),
    [fields, confidential],
  );
  const { precheck, chain } = usePrecheck(flat);
  const salaryOptions = useQuery({
    queryKey: ['requisition-salary-options', flat.dept, initial?.id],
    enabled: !!flat.dept && import.meta.env.VITE_USE_MOCK === 'false',
    queryFn: async () => {
      const first = await api.formSalaryOptions(flat.dept!, 1, initial?.id);
      const rows = [...first.items];
      for (let page = 2; page <= Math.ceil(first.total / 100); page++) {
        rows.push(...(await api.formSalaryOptions(flat.dept!, page, initial?.id)).items);
      }
      return rows;
    },
  });
  const fieldChecks = (key: string) =>
    (precheck.data ?? []).filter((p) => p.status !== 'pass' && targets(p.key).includes(key));
  const locate = (key: string) => {
    const el = document.getElementById(`f-${targets(key)[0]}`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    el?.focus({ preventScroll: true });
  };
  const submit = useSubmitRequisition(initial);
  const save = useSaveRequisition(initial);

  const filled = REQUIRED.filter((f) => (fields[f.key]?.value ?? '').trim()).length;
  const blocking = (precheck.data ?? []).filter((p) => p.status === 'block');
  const canSubmit =
    filled === REQUIRED.length &&
    pending.length === 0 &&
    blocking.length === 0 &&
    !precheck.isFetching &&
    !precheck.isError &&
    !chain.isError &&
    !save.isPending &&
    !submit.isPending;

  const set = (key: string, value: string) => {
    setFields((f) => ({ ...f, [key]: { value, source: 'edited' } }));
    track('rq_field_edit', { field: key, prev_source: fields[key]?.source });
  };

  const aiFill = async () => {
    setFilling(true);
    const t0 = performance.now();
    try {
      const draft = await api.aiFillRequisition(desc);
      // 用户改过的字段不被 AI 覆盖
      setFields((cur) => {
        const next = { ...cur };
        for (const [k, v] of Object.entries(draft.fields))
          if (cur[k]?.source !== 'edited') next[k] = v;
        return next;
      });
      setPending(draft.pending);
      track('rq_ai_fill', {
        input_len: desc.length,
        filled_count: Object.keys(draft.fields).length,
        pending_count: draft.pending.length,
        latency_ms: Math.round(performance.now() - t0),
      });
    } catch (error) {
      message.warning(toAppError(error).message);
    } finally {
      setFilling(false);
    }
  };

  const choose = (p: PendingDecision, option: string) => {
    track('rq_pending_answer', { field: p.field, option });
    setPending((list) => list.filter((x) => x !== p));
    if (p.field === 'headcount') {
      if (option.startsWith('按'))
        setFields((f) => ({ ...f, headcount: { value: '2', source: 'edited' } }));
      else setFields((f) => ({ ...f, hcRequest: { value: '1', source: 'edited' } }));
    } else {
      setFields((f) => ({ ...f, [p.field]: { value: option, source: 'edited' } }));
    }
  };

  const renderControl = (d: FieldDef) => {
    const v = fields[d.key]?.value ?? '';
    const common = {
      id: `f-${d.key}`,
      'aria-required': d.required,
      'aria-invalid': fieldChecks(d.key).some((p) => p.status === 'block'),
      'aria-describedby': `feedback-${d.key}`,
    };
    if (['series', 'level', 'city', 'salary'].includes(d.key)) {
      const values = (salaryOptions.data ?? [])
        .filter(
          (row) =>
            (d.key === 'series' || !flat.series || row.series === flat.series) &&
            (['series', 'city'].includes(d.key) || !flat.city || row.city === flat.city),
        )
        .map((row) =>
          d.key === 'level'
            ? row.grade
            : d.key === 'salary'
              ? `${row.active!.lower}-${row.active!.upper}K/月×${row.active!.months}`
              : row[d.key as 'series' | 'city'],
        );
      return (
        <AutoComplete
          {...common}
          value={v}
          style={{ width: '100%' }}
          options={[...new Set(values)].map((value) => ({ value }))}
          filterOption={(input, option) =>
            String(option?.value).toLowerCase().includes(input.toLowerCase())
          }
          onChange={(value) => set(d.key, value)}
          placeholder="选择薪资表配置，或手动填写"
        />
      );
    }
    if (d.key === 'dept')
      return (
        <DepartmentPicker
          value={v}
          requisitionId={initial?.id}
          onChange={(value) => set('dept', value)}
        />
      );
    if (d.key === 'reportTo')
      return (
        <DirectoryPersonPicker
          id="f-reportTo"
          label="汇报对象"
          dept={fields.dept?.value ?? ''}
          requisitionId={initial?.id}
          value={fields.reportToId?.value ? [fields.reportToId.value] : []}
          legacyName={v}
          onChange={(ids, name) =>
            setFields((old) => ({
              ...old,
              reportToId: { value: ids[0] ?? '', source: 'edited' },
              reportTo: { value: name, source: 'edited' },
            }))
          }
        />
      );
    switch (d.kind) {
      case 'radio':
        return (
          <Radio.Group
            {...common}
            value={v}
            onChange={(e) => set(d.key, e.target.value as string)}
            options={d.options}
            optionType="button"
          />
        );
      case 'select':
        return (
          <Select
            {...common}
            style={{ width: '100%' }}
            value={v || undefined}
            placeholder="请选择"
            options={d.options?.map((o) => ({ value: o, label: o }))}
            onChange={(x: string) => set(d.key, x)}
          />
        );
      case 'number':
        return (
          <InputNumber
            {...common}
            min={1}
            max={999}
            value={v ? Number(v) : undefined}
            onChange={(x) => set(d.key, x ? String(x) : '')}
            style={{ width: 160 }}
            addonAfter="人"
          />
        );
      case 'textarea':
        return (
          <Input.TextArea
            {...common}
            autoSize={{ minRows: 2, maxRows: 6 }}
            value={v}
            onChange={(e) => set(d.key, e.target.value)}
          />
        );
      default:
        return <Input {...common} value={v} onChange={(e) => set(d.key, e.target.value)} />;
    }
  };

  return (
    <Row gutter={24} align="top">
      <Col flex="1 1 640px" style={{ minWidth: 0 }}>
        <section
          className="panel"
          style={{ padding: 16, marginBottom: 16 }}
          aria-labelledby="ai-fill-h"
        >
          <div id="ai-fill-h" style={{ fontWeight: 500, marginBottom: 8 }}>
            <span className="rc-tag rc-ai" style={{ marginRight: 8 }}>
              AI
            </span>
            用一句话描述，AI 帮你填表
          </div>
          <Input.TextArea
            aria-labelledby="ai-fill-h"
            autoSize={{ minRows: 2 }}
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="比如：客服中心要招 3 个白班客服，深圳，12 月中到岗"
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
            <Button type="primary" loading={filling} disabled={!desc.trim()} onClick={aiFill}>
              让 AI 填写
            </Button>
            <Button disabled title="后续批次接入历史复制">
              从历史需求复制
            </Button>
            <span className="muted" style={{ fontSize: 12 }}>
              AI 只填它能确定的字段；你改过的字段不会被覆盖。
            </span>
          </div>
        </section>

        {GROUPS.map((g) => (
          <section
            key={g.title}
            className="panel"
            style={{ marginBottom: 16 }}
            aria-labelledby={`g-${g.title}`}
          >
            <div className="panel-h" id={`g-${g.title}`}>
              {g.title}
            </div>
            <div style={{ padding: '8px 16px 16px' }}>
              {g.title === '职位信息' && import.meta.env.VITE_USE_MOCK === 'false' && (
                <div style={{ marginBlock: 12 }}>
                  <label htmlFor="salary-template">从职级薪资表选择配置</label>
                  <Select
                    id="salary-template"
                    showSearch
                    optionFilterProp="label"
                    style={{ width: '100%', marginTop: 6 }}
                    value={undefined}
                    disabled={!flat.dept}
                    loading={salaryOptions.isFetching}
                    placeholder="选择后填写序列、职级、城市和薪资，可继续修改"
                    options={(salaryOptions.data ?? []).map((row) => ({
                      value: row.id,
                      label: `${row.series} · ${row.grade} · ${row.city} · ${row.active!.lower}-${row.active!.upper}K/月×${row.active!.months}`,
                    }))}
                    onChange={(id) => {
                      const row = salaryOptions.data?.find((r) => r.id === id);
                      if (!row?.active) return;
                      setFields((cur) => ({
                        ...cur,
                        ...Object.fromEntries(
                          Object.entries({
                            series: row.series,
                            level: row.grade,
                            city: row.city,
                            salary: `${row.active!.lower}-${row.active!.upper}K/月×${row.active!.months}`,
                          }).map(([key, value]) => [key, { value, source: 'edited' as const }]),
                        ),
                      }));
                    }}
                  />
                  {salaryOptions.isError && (
                    <Alert
                      type="warning"
                      message="薪资表暂时无法加载，可重试或继续手工填写。"
                      action={
                        <Button onClick={() => void salaryOptions.refetch()}>重试薪资表</Button>
                      }
                    />
                  )}
                </div>
              )}
              {g.fields.map((d) => {
                const fv = fields[d.key];
                const p = pending.find((x) => x.field === d.key);
                return (
                  <div key={d.key} style={{ padding: '10px 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <label htmlFor={`f-${d.key}`}>
                        {d.label}
                        {d.required && (
                          <span style={{ color: 'var(--rc-bad)', marginLeft: 2 }} aria-hidden>
                            *
                          </span>
                        )}
                      </label>
                      {fv && fv.value && (
                        <FieldSourceTag source={fv.source} detail={fv.sourceDetail} />
                      )}
                      {d.help && (
                        <span className="muted" style={{ fontSize: 12 }}>
                          {d.help}
                        </span>
                      )}
                    </div>
                    <Form.Item
                      style={{ marginBottom: 0 }}
                      validateStatus={
                        fieldChecks(d.key).some((p) => p.status === 'block')
                          ? 'error'
                          : fieldChecks(d.key).length
                            ? 'warning'
                            : ''
                      }
                      help={
                        fieldChecks(d.key).some((p) => targets(p.key)[0] === d.key) ? (
                          <div id={`feedback-${d.key}`}>
                            {fieldChecks(d.key)
                              .filter((p) => targets(p.key)[0] === d.key)
                              .map((p) => (
                                <div key={p.key}>{p.detail}</div>
                              ))}
                          </div>
                        ) : undefined
                      }
                    >
                      <Tooltip
                        title={fieldChecks(d.key)
                          .map((p) => p.detail)
                          .join('；')}
                      >
                        <div>{renderControl(d)}</div>
                      </Tooltip>
                    </Form.Item>
                    {p && <PendingDecisionField pending={p} onChoose={(o) => choose(p, o)} />}
                  </div>
                );
              })}
              {g.title === '基本信息' && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingTop: 10 }}>
                  <Switch id="f-confidential" checked={confidential} onChange={setConfidential} />
                  <label htmlFor="f-confidential">保密需求</label>
                  <span className="muted" style={{ fontSize: 12 }}>
                    开启后只对指定人员可见，不在公开渠道发布
                  </span>
                </div>
              )}
              {g.title === '基本信息' && (
                <div style={{ marginTop: 16 }}>
                  <label htmlFor="f-hcRequest">同时申请增编人数</label>
                  <InputNumber
                    id="f-hcRequest"
                    min={0}
                    max={999}
                    value={Number(fields.hcRequest?.value || 0)}
                    onChange={(value) => set('hcRequest', String(value ?? 0))}
                    style={{ marginLeft: 12 }}
                  />
                  <p className="muted">
                    增编申请不会自动增加可用名额；审批后仍需编制负责人在「编制管理」中落实年度计划。
                  </p>
                  {fields.reqType?.value === '替补' && (
                    <Alert
                      style={{ marginTop: 12 }}
                      type="info"
                      message="替补需求将在人员关系校验接通后开放，目前可以保存草稿。"
                    />
                  )}
                  {fields.reqType?.value === '追加' && (
                    <Alert
                      style={{ marginTop: 12 }}
                      type="info"
                      message="追加需求将在岗位模块接通后开放，目前可以保存草稿。"
                    />
                  )}
                  {confidential && (
                    <div style={{ marginTop: 12 }}>
                      <label htmlFor="f-visibleTo">可见人员</label>
                      <DirectoryPersonPicker
                        id="f-visibleTo"
                        label="可见人员"
                        multiple
                        dept={fields.dept?.value ?? ''}
                        requisitionId={initial?.id}
                        value={(fields.visibleTo?.value ?? '').split(',').filter(Boolean)}
                        onChange={(values: string[]) => set('visibleTo', values.join(','))}
                      />
                      <p className="muted">
                        发起人、归属经理、交接负责人及审批链自动包含，无需重复选择。
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>
        ))}
      </Col>

      <Col flex="0 0 320px">
        <aside
          style={{ position: 'sticky', top: 80, display: 'flex', flexDirection: 'column', gap: 16 }}
          aria-label="提交前检查"
        >
          <section className="panel" style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontWeight: 500 }}>必填进度</span>
              <span className="num">
                {filled} / {REQUIRED.length}
              </span>
            </div>
            <Progress
              percent={Math.round((filled / REQUIRED.length) * 100)}
              showInfo={false}
              size="small"
            />
            {pending.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 12, color: 'var(--rc-warn)' }}>
                还有 {pending.length} 个待决定项，处理完才能提交
              </div>
            )}
          </section>

          <section className="panel" aria-labelledby="pre-h">
            <div className="panel-h" id="pre-h">
              提交前预检
            </div>
            <div style={{ padding: '8px 16px' }}>
              {(precheck.data ?? []).map((p) => (
                <div
                  key={p.key}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '18px 1fr',
                    gap: 8,
                    padding: '6px 0',
                  }}
                >
                  {PRE_ICON[p.status]}
                  <div>
                    <div>{p.label}</div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {p.status !== 'pass' &&
                      targets(p.key).some((key) =>
                        GROUPS.some((g) => g.fields.some((d) => d.key === key)),
                      ) ? (
                        <Button type="link" size="small" onClick={() => locate(p.key)}>
                          定位并修改
                        </Button>
                      ) : (
                        p.detail
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="panel" aria-labelledby="chain-h">
            <div className="panel-h" id="chain-h">
              审批链预览
            </div>
            <div style={{ padding: 16 }}>
              <Steps
                direction="vertical"
                size="small"
                current={-1}
                items={(chain.data ?? []).map((n) => ({
                  title: n.name,
                  description: `${n.approver}${n.note ? `，${n.note}` : ''}`,
                }))}
              />
            </div>
          </section>

          {blocking.length > 0 && (
            <Alert
              type="error"
              showIcon
              message={`${blocking.length} 项预检未通过：${blocking.map((b) => b.label).join('、')}`}
            />
          )}
          {(precheck.isError || chain.isError) && (
            <Alert
              type="error"
              showIcon
              message={toAppError(precheck.error ?? chain.error).message}
            />
          )}
          <Button
            type="primary"
            size="large"
            block
            disabled={!canSubmit}
            loading={submit.isPending}
            onClick={() =>
              submit.mutate(flat, {
                onSuccess: (result) => {
                  track('rq_submit', {
                    mode: 'self',
                    precheck_warnings: (precheck.data ?? []).filter((p) => p.status === 'warn')
                      .length,
                  });
                  nav(`/requisitions/${result.id}`);
                },
              })
            }
          >
            提交审批
          </Button>
          <Button
            block
            loading={save.isPending}
            disabled={submit.isPending || save.isPending}
            onClick={() => save.mutate(flat, { onSuccess: () => nav('/requisitions') })}
          >
            保存草稿并返回
          </Button>
        </aside>
      </Col>
    </Row>
  );
}
