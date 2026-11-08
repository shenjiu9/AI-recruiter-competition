import { test, expect } from '@playwright/test';
import { headers, login, ready } from './position-helpers';
const API = 'http://127.0.0.1:8010/api/v1/hr';
test.use({ actionTimeout: 15_000 });

test('岗位简历匹配展示逐项证据、候选人链接，复核不会自动关联', async ({ page, request }, info) => {
  const admin = await headers(request, 'admin');
  const before = await (await request.get(`${API}/automation-live`, { headers: admin })).json();
  expect(
    (
      await request.post(`${API}/automation-live`, {
        headers: admin,
        data: {
          expected_version: before.version,
          mode: 'manual',
          components: { ...before.components, A2: true },
        },
      })
    ).ok(),
  ).toBeTruthy();
  try {
    const { pos } = await ready(request, `匹配页面测试-${Date.now()}`);
    const detail = await (
      await request.get(`${API}/positions/${pos.id}`, { headers: await headers(request) })
    ).json();
    expect(
      (
        await request.post(`${API}/positions/${pos.id}/actions`, {
          headers: await headers(request, 'manager'),
          data: { action: 'confirm_profile', expected_version: detail.version },
        })
      ).ok(),
    ).toBeTruthy();
    const name = `匹配合成候选人-${Date.now()}`;
    const c = (
      await (
        await request.post(`${API}/candidates`, {
          headers: await headers(request),
          data: { profile: { name, skills: '沟通能力和客户问题解决实践' } },
        })
      ).json()
    ).candidate;
    expect(
      (
        await request.post(`${API}/candidates/${c.id}/actions`, {
          headers: await headers(request),
          data: {
            action: 'consent',
            expected_version: c.version,
            granted: true,
            evidence: '合成测试授权',
            reason: '测试',
          },
        })
      ).ok(),
    ).toBeTruthy();
    await login(page, 'hr', `/ai-jobs?component=A2&object=${pos.id}`);
    await page.getByRole('combobox', { name: '任务类型', exact: true }).selectOption('A2');
    await page.getByLabel('选择岗位', { exact: true }).selectOption(pos.id);
    await page.locator('#matching-candidates').click();
    await page.locator('#matching-candidates').fill(name);
    await page.locator('.ant-select-item-option-content').getByText(name, { exact: true }).click();
    await page.locator('#matching-candidates').press('Escape');
    await page.getByRole('button', { name: '创建 AI 任务' }).click();
    await expect(
      page.getByRole('heading', { name: '简历匹配与人才搜索 · 待人工复核' }),
    ).toBeVisible();
    const results = page.getByRole('region', { name: '简历匹配结果' });
    await expect(results.getByRole('link', { name, exact: true })).toBeVisible();
    await expect(results).toContainText('沟通能力和客户问题解决实践');
    await page.getByLabel('处理说明', { exact: true }).fill('已核对合成简历原文');
    await page.getByLabel('我已核对原文、证据和当前状态').check();
    await page.getByRole('button', { name: '确认已阅建议' }).click();
    await expect(
      page.getByRole('heading', { name: '简历匹配与人才搜索 · 已阅建议' }),
    ).toBeVisible();
    const saved = await (
      await request.get(`${API}/candidates/${c.id}`, { headers: await headers(request) })
    ).json();
    expect(saved.applications).toHaveLength(0);
    await page.screenshot({ path: info.outputPath('resume-matching.png'), fullPage: true });
  } finally {
    const latest = await (await request.get(`${API}/automation-live`, { headers: admin })).json();
    await request.post(`${API}/automation-live`, {
      headers: await headers(request, 'admin'),
      data: { expected_version: latest.version, mode: before.mode, components: before.components },
    });
  }
});

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

test('one sentence in the AI command bar starts the matching task for the named candidate', async ({
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
    const name = '林语晨' + String(Date.now()).slice(-4);
    const response = await request.post(`${API}/candidates`, {
      headers: await headers(request),
      data: { profile: { name, skills: 'Excel 数据分析' } },
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
    await login(page, 'hr', '/requisitions');
    await page.keyboard.press('Control+k');
    await expect(page.getByLabel('AI 指令栏')).toBeFocused();
    await page.keyboard.type(`帮我提取${name}的简历信息`);
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/ai-jobs$/);
    await expect(page.getByRole('status').filter({ hasText: '识别为' })).toContainText(
      '简历字段提取',
    );
    await expect(page.getByRole('heading', { name: '简历字段提取 · 待人工复核' })).toBeVisible();
    await expect(page.getByText('Excel 数据分析').first()).toBeVisible();
    await page.screenshot({ path: info.outputPath('ai-command-started.png'), fullPage: true });

    // Reloading must not start the same command again.
    const total = (
      await (await request.get(`${API}/ai-jobs`, { headers: await headers(request) })).json()
    ).total;
    await page.reload();
    await expect(page.getByRole('heading', { name: 'AI 任务与复核' })).toBeVisible();
    await page.waitForTimeout(1000);
    expect(
      (await (await request.get(`${API}/ai-jobs`, { headers: await headers(request) })).json())
        .total,
    ).toBe(total);

    // Without a name the panel asks which candidate, then starts on the pick.
    await page.getByLabel('用一句话让 AI 做事').fill('帮我提取简历字段');
    await page.getByRole('button', { name: '交给 AI' }).click();
    await expect(page.getByText('没从这句话里找到候选人姓名')).toBeVisible();
    await page.getByRole('button', { name, exact: true }).click();
    await expect(page.getByText('已开始“简历字段提取”')).toBeVisible();
    await expect(page.getByRole('heading', { name: /^简历字段提取 · / })).toBeVisible();
    await page.screenshot({ path: info.outputPath('ai-command-choose.png'), fullPage: true });
  } finally {
    const latest = await (await request.get(`${API}/automation-live`, { headers: admin })).json();
    await request.post(`${API}/automation-live`, {
      headers: { ...admin, 'Idempotency-Key': crypto.randomUUID() },
      data: { expected_version: latest.version, mode: before.mode, components: before.components },
    });
  }
});
