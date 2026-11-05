import { CheckCircleOutlined, CloseCircleOutlined, ExclamationCircleOutlined } from '@ant-design/icons';
import { Alert, Button, Col, Input, InputNumber, Progress, Radio, Row, Select, Switch, Steps } from 'antd';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useApi } from '@recruiter/api-client';
import type { FieldValue, PendingDecision } from '@recruiter/domain';
import { track } from '@recruiter/telemetry';
import { FieldSourceTag, PendingDecisionField } from '@recruiter/ui-kit';
import { usePrecheck, useSubmitRequisition } from '../api';

type Kind = 'text' | 'textarea' | 'number' | 'radio' | 'select';
interface FieldDef { key: string; label: string; kind: Kind; required: boolean; options?: string[]; help?: string }

const GROUPS: { title: string; fields: FieldDef[] }[] = [
  { title: '基本信息', fields: [
    { key: 'recruitType', label: '招聘类型', kind: 'radio', required: true, options: ['社招', '校招', '活水'] },
    { key: 'dept', label: '需求部门', kind: 'select', required: true, options: ['客服中心', '销售部 / 华南大区', '经营分析部', '财务部'] },
    { key: 'employmentType', label: '用工类型', kind: 'radio', required: true, options: ['正式', '外包', '实习'], help: '外包、实习不占正式 HC' },
    { key: 'reqType', label: '需求类型', kind: 'radio', required: true, options: ['新增', '替补', '追加'] },
    { key: 'headcount', label: '招聘人数', kind: 'number', required: true },
  ] },
  { title: '职位信息', fields: [
    { key: 'title', label: '职位名称', kind: 'text', required: true },
    { key: 'level', label: '职级范围', kind: 'text', required: true },
    { key: 'city', label: '工作地点', kind: 'text', required: true },
    { key: 'reportTo', label: '汇报对象', kind: 'select', required: true, options: ['何美玲', '田野', '周振华'] },
    { key: 'expectedOnboard', label: '期望到岗', kind: 'text', required: true },
    { key: 'salary', label: '薪资带宽', kind: 'text', required: true, help: '仅内部可见，不对外发布' },
  ] },
  { title: '需求说明', fields: [{ key: 'reason', label: '招聘原因', kind: 'textarea', required: true }] },
  { title: '工作内容', fields: [
    { key: 'duties', label: '岗位职责', kind: 'textarea', required: true },
    { key: 'requirements', label: '任职资格', kind: 'textarea', required: true, help: '会做歧视性表述检查' },
  ] },
];
const REQUIRED = GROUPS.flatMap((g) => g.fields).filter((f) => f.required);

const PRE_ICON = { pass: <CheckCircleOutlined style={{ color: 'var(--rc-ok)' }} />, warn: <ExclamationCircleOutlined style={{ color: 'var(--rc-warn)' }} />, block: <CloseCircleOutlined style={{ color: 'var(--rc-bad)' }} /> };

/** RQ-02：一张表单 + 右侧固定栏。三种填法都落在同一张表单上，字段带来源标签，待决定项就地给选项。 */
export function RequisitionForm() {
  const api = useApi();
  const nav = useNavigate();
  const [fields, setFields] = useState<Record<string, FieldValue>>({ recruitType: { value: '社招', source: 'default' }, employmentType: { value: '正式', source: 'default' } });
  const [pending, setPending] = useState<PendingDecision[]>([]);
  const [desc, setDesc] = useState('客服中心要招 3 个白班客服，深圳，12 月中到岗');
  const [filling, setFilling] = useState(false);
  const [confidential, setConfidential] = useState(false);
  const flat = useMemo(() => Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, v.value])), [fields]);
  const { precheck, chain } = usePrecheck(flat);
  const submit = useSubmitRequisition();

  const filled = REQUIRED.filter((f) => (fields[f.key]?.value ?? '').trim()).length;
  const blocking = (precheck.data ?? []).filter((p) => p.status === 'block');
  const canSubmit = filled === REQUIRED.length && pending.length === 0 && blocking.length === 0;

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
        for (const [k, v] of Object.entries(draft.fields)) if (cur[k]?.source !== 'edited') next[k] = v;
        return next;
      });
      setPending(draft.pending);
      track('rq_ai_fill', { input_len: desc.length, filled_count: Object.keys(draft.fields).length, pending_count: draft.pending.length, latency_ms: Math.round(performance.now() - t0) });
    } finally {
      setFilling(false);
    }
  };

  const choose = (p: PendingDecision, option: string) => {
    track('rq_pending_answer', { field: p.field, option });
    setPending((list) => list.filter((x) => x !== p));
    if (p.field === 'headcount') {
      if (option.startsWith('按')) setFields((f) => ({ ...f, headcount: { value: '2', source: 'edited' } }));
      else setFields((f) => ({ ...f, hcRequest: { value: '1', source: 'edited' } }));
    } else {
      setFields((f) => ({ ...f, [p.field]: { value: option, source: 'edited' } }));
    }
  };

  const renderControl = (d: FieldDef) => {
    const v = fields[d.key]?.value ?? '';
    const common = { id: `f-${d.key}`, 'aria-required': d.required };
    switch (d.kind) {
      case 'radio':
        return <Radio.Group {...common} value={v} onChange={(e) => set(d.key, e.target.value as string)} options={d.options} optionType="button" />;
      case 'select':
        return <Select {...common} style={{ width: '100%' }} value={v || undefined} placeholder="请选择" options={d.options?.map((o) => ({ value: o, label: o }))} onChange={(x: string) => set(d.key, x)} />;
      case 'number':
        return <InputNumber {...common} min={1} max={999} value={v ? Number(v) : undefined} onChange={(x) => set(d.key, x ? String(x) : '')} style={{ width: 160 }} addonAfter="人" />;
      case 'textarea':
        return <Input.TextArea {...common} autoSize={{ minRows: 2, maxRows: 6 }} value={v} onChange={(e) => set(d.key, e.target.value)} />;
      default:
        return <Input {...common} value={v} onChange={(e) => set(d.key, e.target.value)} />;
    }
  };

  return (
    <Row gutter={24} align="top">
      <Col flex="1 1 640px" style={{ minWidth: 0 }}>
        <section className="panel" style={{ padding: 16, marginBottom: 16 }} aria-labelledby="ai-fill-h">
          <div id="ai-fill-h" style={{ fontWeight: 500, marginBottom: 8 }}>
            <span className="rc-tag rc-ai" style={{ marginRight: 8 }}>AI</span>用一句话描述，AI 帮你填表
          </div>
          <Input.TextArea aria-labelledby="ai-fill-h" autoSize={{ minRows: 2 }} value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="比如：客服中心要招 3 个白班客服，深圳，12 月中到岗" />
          <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center' }}>
            <Button type="primary" loading={filling} disabled={!desc.trim()} onClick={aiFill}>让 AI 填写</Button>
            <Button>从历史需求复制</Button>
            <span className="muted" style={{ fontSize: 12 }}>AI 只填它能确定的字段；你改过的字段不会被覆盖。</span>
          </div>
        </section>

        {GROUPS.map((g) => (
          <section key={g.title} className="panel" style={{ marginBottom: 16 }} aria-labelledby={`g-${g.title}`}>
            <div className="panel-h" id={`g-${g.title}`}>{g.title}</div>
            <div style={{ padding: '8px 16px 16px' }}>
              {g.fields.map((d) => {
                const fv = fields[d.key];
                const p = pending.find((x) => x.field === d.key);
                return (
                  <div key={d.key} style={{ padding: '10px 0' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <label htmlFor={`f-${d.key}`}>
                        {d.label}
                        {d.required && <span style={{ color: 'var(--rc-bad)', marginLeft: 2 }} aria-hidden>*</span>}
                      </label>
                      {fv && fv.value && <FieldSourceTag source={fv.source} detail={fv.sourceDetail} />}
                      {d.help && <span className="muted" style={{ fontSize: 12 }}>{d.help}</span>}
                    </div>
                    {renderControl(d)}
                    {p && <PendingDecisionField pending={p} onChoose={(o) => choose(p, o)} />}
                  </div>
                );
              })}
              {g.title === '基本信息' && (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', paddingTop: 10 }}>
                  <Switch id="f-confidential" checked={confidential} onChange={setConfidential} />
                  <label htmlFor="f-confidential">保密需求</label>
                  <span className="muted" style={{ fontSize: 12 }}>开启后只对指定人员可见，不在公开渠道发布</span>
                </div>
              )}
            </div>
          </section>
        ))}
      </Col>

      <Col flex="0 0 320px">
        <aside style={{ position: 'sticky', top: 80, display: 'flex', flexDirection: 'column', gap: 16 }} aria-label="提交前检查">
          <section className="panel" style={{ padding: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontWeight: 500 }}>必填进度</span>
              <span className="num">{filled} / {REQUIRED.length}</span>
            </div>
            <Progress percent={Math.round((filled / REQUIRED.length) * 100)} showInfo={false} size="small" />
            {pending.length > 0 && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--rc-warn)' }}>还有 {pending.length} 个待决定项，处理完才能提交</div>}
          </section>

          <section className="panel" aria-labelledby="pre-h">
            <div className="panel-h" id="pre-h"><span className="rc-tag rc-ai">AI</span>预检</div>
            <div style={{ padding: '8px 16px' }}>
              {(precheck.data ?? []).map((p) => (
                <div key={p.key} style={{ display: 'grid', gridTemplateColumns: '18px 1fr', gap: 8, padding: '6px 0' }}>
                  {PRE_ICON[p.status]}
                  <div>
                    <div>{p.label}</div>
                    <div className="muted" style={{ fontSize: 12 }}>{p.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="panel" aria-labelledby="chain-h">
            <div className="panel-h" id="chain-h">审批链预览</div>
            <div style={{ padding: 16 }}>
              <Steps direction="vertical" size="small" current={-1} items={(chain.data ?? []).map((n) => ({ title: n.name, description: `${n.approver}${n.note ? `，${n.note}` : ''}` }))} />
            </div>
          </section>

          {blocking.length > 0 && <Alert type="error" showIcon message={`${blocking.length} 项预检未通过：${blocking.map((b) => b.label).join('、')}`} />}
          <Button
            type="primary"
            size="large"
            block
            disabled={!canSubmit}
            loading={submit.isPending}
            onClick={async () => {
              await submit.mutateAsync({ ...flat, confidential: confidential ? '1' : '' });
              track('rq_submit', { mode: 'self', precheck_warnings: (precheck.data ?? []).filter((p) => p.status === 'warn').length });
              nav('/requisitions');
            }}
          >
            提交审批
          </Button>
          <Button block onClick={() => nav('/requisitions')}>保存草稿并返回</Button>
        </aside>
      </Col>
    </Row>
  );
}
