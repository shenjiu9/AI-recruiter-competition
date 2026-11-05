import { test, expect, type Page, type APIRequestContext } from '@playwright/test';

test.use({ actionTimeout: 15_000 });

const API = 'http://127.0.0.1:8010/api/v1';
const DEPT = '客服中心';
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
async function requestDraft(request: APIRequestContext, title: string) {
  const response = await request.post(`${API}/hr/requisitions`, {
    headers: await headers(request, 'hr'),
    data: {
      title,
      dept: DEPT,
      recruitType: '社招',
      employmentType: '外包',
      reqType: '新增',
      headcount: '1',
      series: '客服',
      level: 'P3',
      city: '深圳',
      reportTo: '何美玲',
      salary: '8-12K/月×13',
      reason: '组织审批联调',
      duties: '客户服务',
      requirements: '沟通能力',
      expectedOnboard: new Date(Date.now() + 40 * 86400000).toISOString().slice(0, 10),
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

test('组织配置联调：授权、试算、历史恢复与在途审批快照', async ({ page, request, browser }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const old = await requestDraft(request, `旧审批配置-${Date.now()}`);
  await login(page, 'admin');
  await expect(page.getByRole('link', { name: old.title, exact: true })).toHaveCount(0);
  await page.getByRole('menuitem', { name: '组织与权限' }).click();
  await page.getByRole('tab', { name: '人员与权限' }).click();
  const payroll = page.getByRole('row').filter({ hasText: '薪酬维护负责人 (payroll)' });
  await payroll.getByRole('button', { name: '编辑权限' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('授权角色', { exact: true }).click();
  await page.locator('.ant-select-item-option-content').getByText('HRBP', { exact: true }).click();
  await page.keyboard.press('Escape');
  await dialog.getByRole('button', { name: '保存权限' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(payroll.getByText('HRBP', { exact: true })).toBeVisible();
  await payroll.getByRole('button', { name: '权限历史' }).click();
  await expect(dialog.getByRole('row')).toHaveCount(3);
  await dialog.getByRole('button', { name: 'Close' }).click();
  await page.getByRole('tab', { name: '组织与审批配置' }).click();
  const dept = page.getByRole('row').filter({ has: page.getByText(DEPT, { exact: true }) });
  await dept.getByRole('button', { name: '配置审批人' }).click();
  await dialog.getByLabel('HRBP', { exact: true }).press('ArrowDown');
  await page
    .locator('.ant-select-item-option-content')
    .getByText('薪酬维护负责人 (payroll)', { exact: true })
    .click();
  await dialog.getByRole('button', { name: '发布审批配置' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(dept.getByText('薪酬维护负责人', { exact: true })).toBeVisible();
  await dept.getByRole('button', { name: /试\s*算/ }).click();
  await dialog.getByRole('combobox').click();
  await page
    .locator('.ant-select-item-option-content')
    .getByText('林悦 (hr)', { exact: true })
    .click();
  await dialog.getByLabel('申请增编').check();
  await dialog.getByLabel('薪资超带宽').check();
  await expect(dialog.getByText('薪酬维护负责人', { exact: true })).toBeVisible();
  await expect(dialog.getByText('HRD 薪资加签', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Close' }).click();
  let fresh = await requestDraft(request, `新审批配置-${Date.now()}`);
  expect(fresh.chain[2].approver_id).toBe('payroll');
  const oldAfter = await request.get(`${API}/hr/requisitions/${old.id}`, {
    headers: await headers(request, 'hr'),
  });
  expect((await oldAfter.json()).chain[2].approver_id).toBe('hrbp');
  await dept.getByRole('button', { name: '配置历史' }).click();
  await expect(dialog.getByRole('row')).toHaveCount(3);
  await dialog.getByRole('row').last().getByRole('button', { name: '以此版本编辑' }).click();
  await dialog.getByRole('button', { name: '发布审批配置' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(dept.getByText('人力伙伴', { exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/organization-settings.png', fullPage: true });
  for (const user of ['manager', 'director']) {
    const response = await request.post(`${API}/hr/requisitions/${fresh.id}/approve`, {
      headers: await headers(request, user),
      data: { expected_version: fresh.version, node_id: fresh.chain[fresh.currentNode].id },
    });
    expect(response.ok()).toBeTruthy();
    fresh = await response.json();
  }
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const biz = await context.newPage();
  await login(biz, 'payroll', 'http://127.0.0.1:5184');
  const card = biz.locator('article').filter({ hasText: fresh.title });
  await card.getByRole('button', { name: '通过', exact: true }).click();
  await expect(card).toHaveCount(0);
  await context.close();
  await login(page, 'hr');
  await page.goto('/settings/organization');
  await expect(page.getByText('当前为只读模式，仅展示授权部门。')).toBeVisible();
  await expect(page.getByRole('button', { name: '配置审批人' })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('组织配置冲突保留输入，并阻止移除最后一名管理员', async ({ page, request }) => {
  await login(page, 'admin');
  await page.goto('/settings/organization');
  const dept = page.getByRole('row').filter({ has: page.getByText(DEPT, { exact: true }) });
  await dept.getByRole('button', { name: '配置审批人' }).click();
  const dialog = page.getByRole('dialog');
  const before = await request.get(`${API}/admin/organization/departments`, {
    headers: await headers(request, 'admin'),
  });
  const current = (await before.json()).find((d: { id: string }) => d.id === DEPT);
  const changed = await request.post(
    `${API}/admin/organization/approval?dept=${encodeURIComponent(DEPT)}`,
    {
      headers: await headers(request, 'admin'),
      data: {
        expected_version: current.version,
        director_id: 'director',
        hrbp_id: 'hrbp',
        hc_owner_id: 'hrd',
        hrd_id: 'salary_hrd',
      },
    },
  );
  expect(changed.ok()).toBeTruthy();
  await dialog.getByRole('button', { name: '发布审批配置' }).click();
  await expect(dialog.getByRole('alert')).toContainText('输入已保留');
  await expect(dialog.getByRole('button', { name: '发布审批配置' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Close' }).click();
  await page.getByRole('tab', { name: '人员与权限' }).click();
  const admin = page.getByRole('row').filter({ hasText: '系统管理员 (admin)' });
  await admin.getByRole('button', { name: '编辑权限' }).click();
  await dialog.locator('.ant-select-selection-item-remove').click();
  await dialog.getByRole('button', { name: '保存权限' }).click();
  await expect(dialog.getByRole('alert')).toContainText('至少保留一名在职系统管理员');
  await dialog.getByRole('button', { name: 'Close' }).click();
  await expect(admin.getByText('系统管理员', { exact: true })).toBeVisible();
});
