import { test, expect, type Page, type APIRequestContext } from '@playwright/test';

test.use({ actionTimeout: 15_000 });
const API = 'http://127.0.0.1:8010/api/v1';
async function headers(request: APIRequestContext, user: string) {
  const response = await request.post(`${API}/auth/dev-login`, {
    data: { user_id: user, password: 'e2e-only-password' },
  });
  expect(response.ok()).toBeTruthy();
  return {
    Authorization: `Bearer ${(await response.json()).token}`,
    'Idempotency-Key': crypto.randomUUID(),
  };
}
async function login(page: Page, user: string, base = 'http://127.0.0.1:5183') {
  await page.goto(base);
  if (await page.getByRole('button', { name: '退出登录' }).isVisible())
    await page.getByRole('button', { name: '退出登录' }).click();
  await page.getByLabel('开发账号').selectOption(user);
  await page.getByLabel('开发登录口令').fill('e2e-only-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible();
}
async function create(request: APIRequestContext, title: string) {
  const response = await request.post(`${API}/hr/requisitions`, {
    headers: await headers(request, 'hr'),
    data: {
      title,
      dept: '客服中心',
      recruitType: '社招',
      employmentType: '外包',
      reqType: '新增',
      headcount: '1',
      series: '客服',
      level: 'P3',
      city: '深圳',
      reportTo: '何美玲',
      salary: '8-12K/月×13',
      reason: '转交联调',
      duties: '客户服务',
      requirements: '沟通能力',
      expectedOnboard: new Date(Date.now() + 40 * 86400000).toISOString().slice(0, 10),
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

test('HR 与业务 H5 转交审批、消息和历史联调', async ({ page, request, browser }) => {
  const req = await create(request, `两端审批转交-${Date.now()}`);
  await login(page, 'manager');
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '转交审批', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('combobox', { name: '转交给', exact: true }).selectOption('director');
  await expect(dialog.getByRole('button', { name: '确认转交' })).toBeDisabled();
  await dialog.getByLabel('转交原因（必填）').fill('请部门负责人代为确认');
  await dialog.getByRole('button', { name: '确认转交' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('请部门负责人代为确认', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: '转交审批', exact: true })).toHaveCount(0);
  await page.screenshot({ path: 'test-results/transfer-desktop.png', fullPage: true });

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const biz = await mobile.newPage();
  try {
    await login(biz, 'director', 'http://127.0.0.1:5184');
    await biz.getByText(/审批与交接消息（/).click();
    await expect(biz.getByRole('button', { name: `审批转交 · ${req.title}` })).toBeVisible();
    await biz.getByRole('button', { name: `审批转交 · ${req.title}` }).click();
    await expect(biz.getByText('请部门负责人代为确认', { exact: false })).toBeVisible();
    await biz.getByRole('button', { name: '转交审批', exact: true }).click();
    await biz.getByRole('combobox', { name: '转交给', exact: true }).selectOption('manager');
    await biz.getByLabel('转交原因（必填）').fill('经理已返回，由原经理确认');
    await biz.getByRole('button', { name: '确认转交' }).scrollIntoViewIfNeeded();
    await biz.screenshot({ path: 'test-results/transfer-mobile.png', fullPage: true });
    await biz.getByRole('button', { name: '确认转交' }).click();
    await expect(biz.getByRole('button', { name: '关闭详情' })).toHaveCount(0);
    await expect(biz.getByRole('article').filter({ hasText: req.title })).toHaveCount(0);
  } finally {
    await mobile.close();
  }

  await page.reload();
  await expect(page.getByRole('button', { name: '通过审批' })).toBeVisible();
  await page.getByRole('button', { name: '通过审批' }).click();
  await expect(page.getByRole('button', { name: '通过审批' })).toHaveCount(0);
  const final = await (
    await request.get(`${API}/hr/requisitions/${req.id}`, {
      headers: await headers(request, 'hr'),
    })
  ).json();
  expect(
    final.history.filter((item: { action: string }) => item.action === 'transferred'),
  ).toHaveLength(2);
  expect(final.currentNode).toBe(1);
});

test('转交冲突保留输入，响应丢失后同键重试只产生一条转交', async ({ page, request }) => {
  const req = await create(request, `转交冲突与重试-${Date.now()}`);
  await login(page, 'manager');
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '转交审批', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('combobox', { name: '转交给', exact: true }).selectOption('director');
  await dialog.getByLabel('转交原因（必填）').fill('保留我的转交原因');
  const moved = await request.post(`${API}/hr/requisitions/${req.id}/transfer`, {
    headers: await headers(request, 'manager'),
    data: {
      expected_version: req.version,
      node_id: 'manager',
      target_id: 'director',
      reason: '其他页面已转交',
    },
  });
  expect(moved.status()).toBe(200);
  await dialog.getByRole('button', { name: '确认转交' }).click();
  await expect(dialog.getByRole('alert')).toContainText('输入已保留');
  await expect(dialog.getByLabel('转交原因（必填）')).toHaveValue('保留我的转交原因');
  await expect(dialog.getByRole('button', { name: '确认转交' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Close' }).click();

  const retry = await create(request, `转交响应丢失-${Date.now()}`);
  await page.goto(`/requisitions/${retry.id}`);
  await page.getByRole('button', { name: '转交审批', exact: true }).click();
  await dialog.getByRole('combobox', { name: '转交给', exact: true }).selectOption('director');
  await dialog.getByLabel('转交原因（必填）').fill('网络重试只能转交一次');
  const keys: string[] = [];
  await page.route(`**/requisitions/${retry.id}/transfer`, async (route) => {
    keys.push(route.request().headers()['idempotency-key']!);
    if (keys.length === 1) {
      const committed = await route.fetch();
      expect(committed.status()).toBe(200);
      await route.fulfill({
        status: 503,
        json: { error: { code: 'TEST_RESPONSE_LOST', message: '模拟响应丢失' } },
      });
    } else await route.continue();
  });
  await dialog.getByRole('button', { name: '确认转交' }).click();
  await expect(dialog.getByLabel('转交原因（必填）')).toBeDisabled();
  await dialog.getByRole('button', { name: '重试转交' }).click();
  await expect(dialog).toHaveCount(0);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const final = await (
    await request.get(`${API}/hr/requisitions/${retry.id}`, {
      headers: await headers(request, 'hr'),
    })
  ).json();
  expect(
    final.history.filter((item: { action: string }) => item.action === 'transferred'),
  ).toHaveLength(1);
});
