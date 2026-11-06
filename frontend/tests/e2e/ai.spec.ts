import { test, expect } from '@playwright/test';
import { headers, login } from './position-helpers';
const API = 'http://127.0.0.1:8010/api/v1/hr';

test('AI extraction task replays lost response, displays evidence and applies only after review', async ({
  page,
  request,
}, info) => {
  const admin = await headers(request, 'admin');
  const before = await (await request.get(`${API}/automation-live`, { headers: admin })).json();
  const configured = await request.post(`${API}/automation-live`, {
    headers: { ...admin, 'Idempotency-Key': crypto.randomUUID() },
    data: {
      expected_version: before.version,
      mode: 'manual',
      components: { ...before.components, A3: true },
    },
  });
  expect(configured.ok()).toBeTruthy();
  try {
    const response = await request.post(`${API}/candidates`, {
      headers: await headers(request),
      data: { profile: { name: 'AI复核联调候选人', skills: 'Python 实践' } },
    });
    expect(response.ok()).toBeTruthy();
    const c = (await response.json()).candidate;
    expect(
      (
        await request.post(`${API}/candidates/${c.id}/actions`, {
          headers: await headers(request),
          data: {
            action: 'consent',
            expected_version: c.version,
            granted: true,
            evidence: '本人签名',
            reason: '测试招聘评估',
          },
        })
      ).ok(),
    ).toBeTruthy();
    await login(page, 'hr', `/candidates/${c.id}`);
    await page.getByRole('link', { name: 'AI 提取复核' }).click();
    await expect(page.getByLabel('选择候选人', { exact: true })).toHaveValue(c.id);
    const keys: string[] = [];
    await page.route('**/api/v1/hr/ai-jobs', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      keys.push(route.request().headers()['idempotency-key']);
      if (keys.length === 1) {
        await route.fetch();
        await route.abort('failed');
      } else await route.continue();
    });
    await page.getByRole('button', { name: '创建 AI 任务' }).click();
    await page.getByRole('button', { name: '重试同一次提交' }).click();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await expect(page.getByRole('heading', { name: '简历字段提取 · 待人工复核' })).toBeVisible();
    await expect(page.getByRole('button', { name: '确认并执行' })).toBeDisabled();
    await page.getByLabel('处理说明', { exact: true }).fill('逐项核实了技能原文');
    await page.getByLabel('我已核对原文、证据和当前状态').check();
    await page.getByRole('button', { name: '确认并执行' }).click();
    await expect(page.getByRole('heading', { name: '简历字段提取 · 已执行' })).toBeVisible();
    await page.screenshot({ path: info.outputPath('ai-evidence-review.png'), fullPage: true });
  } finally {
    const latest = await (await request.get(`${API}/automation-live`, { headers: admin })).json();
    await request.post(`${API}/automation-live`, {
      headers: { ...admin, 'Idempotency-Key': crypto.randomUUID() },
      data: { expected_version: latest.version, mode: before.mode, components: before.components },
    });
  }
});
