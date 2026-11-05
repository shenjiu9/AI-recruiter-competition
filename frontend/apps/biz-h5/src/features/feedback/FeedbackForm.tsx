import { Button, Form, Radio, Space, TextArea, Toast } from 'antd-mobile';
import { useState } from 'react';
import { useApi, useIdempotencyKey } from '@recruiter/api-client';
import { track } from '@recruiter/telemetry';

const ITEMS = [
  { key: 'team', label: '团队管理' },
  { key: 'service', label: '服务质量把控' },
  { key: 'comm', label: '沟通表达' },
];
const SCALE = ['不符合', '基本符合', '符合', '超出预期'];

/** 面评填写：按面试流程的评价项填写，面评永远由面试官本人提交（PRD 10.6） */
export function FeedbackForm({ appId, onDone }: { appId: string; onDone: () => void }) {
  const api = useApi();
  const idem = useIdempotencyKey();
  const [busy, setBusy] = useState(false);
  return (
    <Form
      layout="vertical"
      onFinish={async (values: Record<string, string>) => {
        setBusy(true);
        try {
          await api.submitFeedback(appId, values, { idempotencyKey: idem.key() });
          idem.reset();
          track('iv_feedback_submit', { ai_prefilled: false, via: 'h5' });
          Toast.show({ icon: 'success', content: '面评已提交' });
          onDone();
        } finally {
          setBusy(false);
        }
      }}
      footer={<Button block type="submit" color="primary" size="large" loading={busy}>提交面评</Button>}
    >
      <Form.Header>邓可，客服主管第 1 轮</Form.Header>
      {ITEMS.map((it) => (
        <Form.Item key={it.key} name={it.key} label={it.label} rules={[{ required: true, message: `请选择${it.label}的评价` }]}>
          <Radio.Group>
            <Space wrap>
              {SCALE.map((s) => <Radio key={s} value={s}>{s}</Radio>)}
            </Space>
          </Radio.Group>
        </Form.Item>
      ))}
      <Form.Item name="conclusion" label="建议" rules={[{ required: true, message: '请选择建议' }]}>
        <Radio.Group>
          <Space>
            <Radio value="推荐">推荐</Radio>
            <Radio value="不推荐">不推荐</Radio>
          </Space>
        </Radio.Group>
      </Form.Item>
      <Form.Item name="note" label="补充说明" rules={[{ required: true, message: '写一两句你的判断依据' }]}>
        <TextArea placeholder="比如：带过 12 人白班团队，排班思路清楚" autoSize={{ minRows: 3 }} />
      </Form.Item>
    </Form>
  );
}
