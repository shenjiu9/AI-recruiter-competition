import { expect, test, type Page } from '@playwright/test';

async function login(page: Page, user: string, base = 'http://127.0.0.1:5183') {
  await page.goto(base);
  if (await page.getByRole('button', { name: '退出登录' }).isVisible())
    await page.getByRole('button', { name: '退出登录' }).click();
  await page.getByLabel('开发账号').selectOption(user);
  await page.getByLabel('开发登录口令').fill('e2e-only-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible();
}

async function select(page: Page, id: string, text: string) {
  await page.locator(id).click();
  await page.locator('.ant-select-item-option-content').getByText(text, { exact: true }).click();
}

test('真实 API：HR 保存恢复草稿、提交、业务方驳回、重提、三级审批', async ({ page, browser }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const title = `联调客服-${Date.now()}`;
  await login(page, 'hr');
  await page.getByRole('button', { name: '发起招聘需求', exact: true }).click();
  await select(page, '#f-dept', '客服中心');
  await page.getByText('新增', { exact: true }).click();
  await page.locator('#f-headcount').fill('2');
  await page.locator('#f-title').fill(title);
  await page.locator('#f-series').fill('客服');
  await page.locator('#f-level').fill('P3');
  await page.locator('#f-city').fill('深圳');
  await select(page, '#f-reportTo', '何美玲');
  await page
    .locator('#f-expectedOnboard')
    .fill(new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10));
  await page.locator('#f-salary').fill('8-12K/月×13');
  await page.locator('#f-reason').fill('客户服务团队扩编');
  await page.locator('#f-duties').fill('处理客户咨询和问题');
  await page.locator('#f-requirements').fill('具有沟通和问题解决能力');
  await page.getByRole('button', { name: '保存草稿并返回' }).click();
  await expect(page.getByRole('link', { name: title, exact: true })).toBeVisible();
  await page.reload();
  await page.getByRole('link', { name: title, exact: true }).click();
  const detailUrl = page.url();
  await page.getByRole('button', { name: '编辑需求' }).click();
  await expect(page.locator('#f-duties')).toHaveValue('处理客户咨询和问题');
  await page.getByRole('button', { name: '提交审批', exact: true }).click();
  await expect(page).toHaveURL(detailUrl);
  await expect(page.getByText(/审批中/)).toBeVisible();

  const bizContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const biz = await bizContext.newPage();
  biz.on('pageerror', (error) => errors.push(error.message));
  await login(biz, 'manager', 'http://127.0.0.1:5184');
  const card = biz.locator('article').filter({ hasText: title });
  await card.getByRole('button', { name: '查看需求 / 驳回' }).click();
  await biz.getByPlaceholder('说明需要调整的内容').fill('请补充业务扩展原因');
  await biz.getByRole('button', { name: '确认驳回' }).click();
  await expect(card).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(/已驳回/)).toBeVisible();
  await page.getByRole('button', { name: '编辑需求' }).click();
  await page.locator('#f-reason').fill('新增两条客户服务业务线，需要扩大团队');
  await page.getByRole('button', { name: '提交审批', exact: true }).click();
  await expect(page).toHaveURL(detailUrl);

  for (const actor of ['manager', 'director', 'hrbp']) {
    await login(biz, actor, 'http://127.0.0.1:5184');
    await biz
      .locator('article')
      .filter({ hasText: title })
      .getByRole('button', { name: '通过', exact: true })
      .click();
    await expect(biz.locator('article').filter({ hasText: title })).toHaveCount(0);
  }
  await page.reload();
  await expect(page.getByText('需求审批已通过', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/requisition-approved.png', fullPage: true });
  await bizContext.close();
  expect(errors).toEqual([]);
});

test('AI 未配置时明确降级，手工内容保留', async ({ page }) => {
  await login(page, 'hr');
  await page.goto('/requisitions/new');
  await page.locator('#f-title').fill('手工保留的职位');
  await page.getByRole('button', { name: '让 AI 填写' }).click();
  await expect(page.getByText('AI 填表尚未配置，请手工填写；已填写的内容不会丢失')).toBeVisible();
  await expect(page.locator('#f-title')).toHaveValue('手工保留的职位');
});

test('编制维护联调：终审不足加签，补足后才能审批并预占', async ({ page, request }) => {
  const api = 'http://127.0.0.1:8010/api/v1';
  const headers = async (user: string) => {
    const response = await request.post(`${api}/auth/dev-login`, {
      data: { user_id: user, password: 'e2e-only-password' },
    });
    expect(response.ok()).toBeTruthy();
    return {
      Authorization: `Bearer ${(await response.json()).token}`,
      'Idempotency-Key': crypto.randomUUID(),
    };
  };
  const response = await request.post(`${api}/hr/requisitions`, {
    headers: await headers('hr'),
    data: {
      recruitType: '社招',
      dept: '财务部',
      employmentType: '正式',
      reqType: '新增',
      headcount: '2',
      title: '编制复核联调',
      series: '财务',
      level: 'P3',
      city: '深圳',
      reportTo: '田野',
      expectedOnboard: new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10),
      salary: '8-12K/月×13',
      reason: '业务扩展',
      duties: '财务分析',
      requirements: '财务知识',
    },
  });
  expect(response.status()).toBe(201);
  let req = await response.json();
  for (const user of ['analyst', 'director']) {
    const approved = await request.post(`${api}/hr/requisitions/${req.id}/approve`, {
      headers: await headers(user),
      data: { node_id: req.chain[req.currentNode].id, expected_version: req.version },
    });
    expect(approved.ok()).toBeTruthy();
    req = await approved.json();
  }
  await login(page, 'hrbp');
  await page.getByText('编制管理', { exact: true }).click();
  const row = page.getByRole('row').filter({ hasText: '财务部' });
  await row.getByRole('button', { name: '维护编制', exact: true }).click();
  await page.getByLabel('计划编制', { exact: true }).fill('0');
  await page.getByRole('button', { name: '保存编制' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '通过审批', exact: true }).click();
  await expect(page.getByText('终审编制复核中', { exact: true })).toBeVisible();
  await login(page, 'hrd');
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '通过审批', exact: true }).click();
  await expect(page.getByText(/编制不足、冻结或尚未生效，请先维护编制/)).toBeVisible();
  await page.getByText('编制管理', { exact: true }).click();
  await row.getByRole('button', { name: '维护编制', exact: true }).click();
  await page.getByLabel('计划编制', { exact: true }).fill('2');
  await page.getByRole('button', { name: '保存编制' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '通过审批', exact: true }).click();
  await expect(page.getByText('需求审批已通过', { exact: true })).toBeVisible();
  await page.getByText('编制管理', { exact: true }).click();
  await expect(row.getByRole('cell').nth(3)).toHaveText('2');
  await expect(row.getByRole('cell').nth(4)).toHaveText('0');
  await expect(page.getByRole('button', { name: '新增年度编制' })).toBeEnabled();
  await page.screenshot({
    path: 'test-results/headcount-management.png',
    fullPage: true,
    animations: 'disabled',
  });
});
