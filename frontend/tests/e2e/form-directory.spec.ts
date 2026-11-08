import { test, expect, type Page, type APIRequestContext } from '@playwright/test';

test.use({ actionTimeout: 15_000 });

const root = 'http://127.0.0.1:8010/api/v1';
async function headers(request: APIRequestContext, user = 'hr') {
  const r = await request.post(`${root}/auth/dev-login`, {
    data: { user_id: user, password: 'e2e-only-password' },
  });
  expect(r.ok()).toBeTruthy();
  return {
    Authorization: `Bearer ${(await r.json()).token}`,
    'Idempotency-Key': crypto.randomUUID(),
  };
}
async function login(page: Page, user: string, base = 'http://127.0.0.1:5183') {
  await page.goto(base);
  await page.getByLabel('开发账号').selectOption(user);
  await page.getByLabel('开发登录口令').fill('e2e-only-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible();
}
async function draft(request: APIRequestContext, fields: Record<string, string> = {}) {
  const r = await request.post(`${root}/hr/requisitions/drafts`, {
    headers: await headers(request),
    data: {
      title: `目录需求-${crypto.randomUUID().slice(0, 8)}`,
      dept: '客服测试小组',
      recruitType: '社招',
      employmentType: '外包',
      reqType: '新增',
      headcount: '1',
      series: '客服',
      level: 'P3',
      city: '深圳',
      reportTo: '同名测试员工',
      salary: '8-12K/月×13',
      expectedOnboard: new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10),
      reason: '扩展团队',
      duties: '处理咨询',
      requirements: '沟通能力',
      ...fields,
    },
  });
  expect(r.status()).toBe(201);
  return r.json();
}

test('真实目录：新部门、同名人员、分页搜索、保密名单保存及失效值修复', async ({
  page,
  request,
}) => {
  const req = await draft(request);
  await login(page, 'hr');
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '编辑需求' }).click();
  await expect(page.getByText('历史值：同名测试员工，请重新选择人员')).toBeVisible();
  await expect(page.getByRole('button', { name: '提交审批', exact: true })).toBeDisabled();
  // Keyboard actions do not wait for async directory loading to enable the field.
  await expect(page.locator('#f-dept')).toBeEnabled();
  await page.locator('#f-dept').press('ArrowDown');
  await page.locator('.ant-select-tree-title').getByText('客服测试小组', { exact: true }).click();
  await page.getByRole('button', { name: '下一页人员', exact: true }).click();
  await page.locator('#f-reportTo').click();
  await expect(
    page
      .locator('.ant-select-item-option-content')
      .getByText('目录测试员工24（z-person-24）', { exact: true }),
  ).toBeVisible();
  await page.getByRole('combobox', { name: '搜索汇报对象', exact: true }).fill('同名测试员工');
  await page
    .locator('.ant-select-item-option-content')
    .getByText('同名测试员工（z-person-01）', { exact: true })
    .click();
  await page.locator('#f-confidential').click();
  await page.locator('#f-visibleTo').click();
  await page.getByRole('combobox', { name: '搜索可见人员', exact: true }).fill('z-person-02');
  await page
    .locator('.ant-select-item-option-content')
    .getByText('☐ 目录测试员工2（z-person-02）', { exact: true })
    .click();
  await page.getByRole('combobox', { name: '搜索可见人员', exact: true }).fill('人力伙伴');
  await page
    .locator('.ant-select-item-option-content')
    .getByText('☐ 人力伙伴（hrbp）', { exact: true })
    .click();
  await page.locator('#f-visibleTo').press('Escape');
  await expect(page.getByRole('button', { name: '移除 目录测试员工2' })).toBeVisible();
  await page.getByRole('button', { name: '保存草稿并返回' }).click();
  await expect(page.getByRole('link', { name: req.title, exact: true })).toBeVisible();
  const saved = await (
    await request.get(`${root}/hr/requisitions/${req.id}`, { headers: await headers(request) })
  ).json();
  expect(saved.fields.reportToId).toBe('z-person-01');
  expect(saved.fields.visibleTo).toBe('z-person-02,hrbp');
  // Revoke the selected person's scope after save. The historical ID must remain visible and removable.
  const revoked = await request.post(`${root}/admin/organization/users/z-person-02/permissions`, {
    headers: await headers(request, 'admin'),
    data: { expected_version: 1, roles: ['recruiter'], departments: [] },
  });
  expect(revoked.ok()).toBeTruthy();
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '编辑需求' }).click();
  await expect(page.getByText('z-person-02（已失效或超出范围）', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '提交审批', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '移除 z-person-02', exact: true }).click();
  await expect(page.getByRole('button', { name: '提交审批', exact: true })).toBeEnabled();
  await page.screenshot({ path: 'test-results/form-directory-draft.png', fullPage: true });
  await page.getByRole('button', { name: '提交审批', exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/requisitions/${req.id}$`));
});

for (const client of ['HR', 'H5']) {
  test(`${client} 确认：目录失败重试、人员 ID 变更及审批快照`, async ({ page, request }) => {
    const req = await draft(request, { reportToId: 'manager' });
    const submitted = await request.post(`${root}/hr/requisitions/${req.id}/submit`, {
      headers: await headers(request),
      data: { expected_version: req.version },
    });
    expect(submitted.ok()).toBeTruthy();
    if (client === 'H5') await page.setViewportSize({ width: 390, height: 844 });
    await login(
      page,
      'manager',
      client === 'HR' ? 'http://127.0.0.1:5183' : 'http://127.0.0.1:5184',
    );
    let failed = false;
    await page.route('**/requisition-form/users?*', async (route) => {
      if (!failed) {
        failed = true;
        await route.fulfill({
          status: 503,
          json: { error: { code: 'UNAVAILABLE', message: '目录临时不可用' } },
        });
      } else await route.continue();
    });
    if (client === 'HR') {
      await page.goto(`/requisitions/${req.id}`);
      await page.getByRole('button', { name: '修改并确认' }).click();
    } else
      await page
        .locator('article')
        .filter({ hasText: req.title })
        .getByRole('button', { name: '修改并确认' })
        .click();
    await expect(page.getByText('目录临时不可用', { exact: false })).toBeVisible();
    await page.getByRole('button', { name: '重试人员目录' }).click();
    await page.getByRole('combobox', { name: '搜索汇报对象', exact: true }).fill('同名测试员工');
    await page
      .locator('.ant-select-item-option-content')
      .getByText('同名测试员工（z-person-00）', { exact: true })
      .click();
    await expect(page.getByText('汇报对象：何美玲 → 同名测试员工', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '确认并继续审批' })).toBeEnabled();
    await page
      .getByRole('combobox', { name: '搜索汇报对象', exact: true })
      .evaluate((element) => element.scrollIntoView({ block: 'center' }));
    await page.screenshot({
      path: `test-results/form-directory-confirm-${client}.png`,
      fullPage: true,
    });
    await page.getByRole('button', { name: '确认并继续审批' }).click();
    await expect
      .poll(
        async () =>
          (
            await (
              await request.get(`${root}/hr/requisitions/${req.id}`, {
                headers: await headers(request),
              })
            ).json()
          ).currentNode,
      )
      .toBe(1);
    const saved = await (
      await request.get(`${root}/hr/requisitions/${req.id}`, { headers: await headers(request) })
    ).json();
    expect(saved.fields.reportToId).toBe('z-person-00');
    expect(saved.chain[0].approver_id).toBe('manager');
  });
}
