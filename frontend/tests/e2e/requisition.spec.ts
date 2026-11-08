import { expect, test, type Page, type APIRequestContext } from '@playwright/test';

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
  if (id === '#f-reportTo') {
    await page.locator(id).fill(text);
    await page
      .locator('.ant-select-item-option-content')
      .getByText(`${text}（${text === '何美玲' ? 'manager' : 'analyst'}）`, { exact: true })
      .click();
    return;
  }
  await page.locator(id).click();
  if (id === '#f-dept') {
    await page.locator('.ant-select-tree-title').getByText(text, { exact: true }).click();
    return;
  }
  await page.locator('.ant-select-item-option-content').getByText(text, { exact: true }).click();
}

const apiRoot = 'http://127.0.0.1:8010/api/v1';
async function apiHeaders(request: APIRequestContext, user: string) {
  const response = await request.post(`${apiRoot}/auth/dev-login`, {
    data: { user_id: user, password: 'e2e-only-password' },
  });
  expect(response.ok()).toBeTruthy();
  return {
    Authorization: `Bearer ${(await response.json()).token}`,
    'Idempotency-Key': crypto.randomUUID(),
  };
}
async function salesRequest(request: APIRequestContext, title: string, employmentType = '正式') {
  const response = await request.post(`${apiRoot}/hr/requisitions`, {
    headers: await apiHeaders(request, 'hr'),
    data: {
      recruitType: '社招',
      dept: '销售部 / 华南大区',
      employmentType,
      reqType: '新增',
      headcount: '1',
      title,
      series: '销售',
      level: 'P3',
      city: '深圳',
      reportTo: '周振华',
      expectedOnboard: new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10),
      salary: '8-12K/月×13',
      reason: '业务扩展',
      duties: '维护客户关系',
      requirements: '沟通能力',
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

test('审批入口常驻：说明等待原因、刷新轮转、禁止越权并完成本人审批', async ({ page, request }) => {
  // 不消耗其他审批场景共用的正式编制。
  let req = await salesRequest(request, `审批入口-${Date.now()}`, '实习');
  const path = `${apiRoot}/hr/requisitions/${req.id}`;
  await login(page, 'hrbp');
  await page.goto('/requisitions');
  await page
    .getByRole('row')
    .filter({ hasText: req.title })
    .getByRole('link', { name: '查看审批' })
    .click();
  const panel = page.getByRole('region', { name: '审批处理' });
  await expect(panel.getByText('等待周振华处理 · 用人经理确认')).toBeVisible();
  await expect(panel).toContainText('尚未轮到你的');
  for (const name of ['通过审批', '驳回需求', '转交审批', '修改并确认']) {
    await expect(panel.getByRole('button', { name, exact: true })).toBeVisible();
    await expect(panel.getByRole('button', { name, exact: true })).toBeDisabled();
  }
  const denied = await request.post(`${path}/approve`, {
    headers: await apiHeaders(request, 'hrbp'),
    data: { node_id: req.chain[req.currentNode].id, expected_version: req.version },
  });
  expect(denied.status()).toBe(403);
  await page.screenshot({ path: 'test-results/approval-waiting-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await panel.scrollIntoViewIfNeeded();
  await expect(panel.getByRole('button', { name: '通过审批', exact: true })).toBeInViewport();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: 'test-results/approval-waiting-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  for (const user of ['sales', 'director']) {
    const response = await request.post(`${path}/approve`, {
      headers: await apiHeaders(request, user),
      data: { node_id: req.chain[req.currentNode].id, expected_version: req.version },
    });
    expect(response.ok()).toBeTruthy();
    req = await response.json();
    await panel.getByRole('button', { name: '刷新进度' }).click();
    if (user === 'sales') {
      await expect(panel).toContainText('等待部门负责人处理');
      await expect(panel.getByRole('button', { name: '通过审批', exact: true })).toBeDisabled();
    }
  }
  await expect(panel).toContainText('轮到你审批了');
  await expect(panel.getByRole('button', { name: '通过审批', exact: true })).toBeEnabled();
  await login(page, 'hr');
  await page.goto(`/requisitions/${req.id}`);
  await expect(panel).toContainText('此节点由指定审批人处理');
  await expect(panel.getByRole('button', { name: '通过审批', exact: true })).toBeDisabled();
  await login(page, 'hrbp');
  await page.goto(`/requisitions/${req.id}`);
  await panel.getByRole('button', { name: '通过审批', exact: true }).click();
  await expect(panel).toContainText('审批流程已完成');
  for (const name of ['通过审批', '驳回需求', '转交审批']) {
    await expect(panel.getByRole('button', { name, exact: true })).toBeVisible();
    await expect(panel.getByRole('button', { name, exact: true })).toBeDisabled();
  }
});

test('代理修改确认：业务 H5 预检拦截、薪资加签、两端差异记录及完整审批', async ({
  page,
  request,
  browser,
}) => {
  const req = await salesRequest(request, `代理确认-${Date.now()}`);
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const biz = await context.newPage();
  const errors: string[] = [];
  biz.on('pageerror', (e) => errors.push(e.message));
  await login(biz, 'sales', 'http://127.0.0.1:5184');
  const card = biz.locator('article').filter({ hasText: req.title });
  await card.getByRole('button', { name: '修改并确认' }).click();
  await biz.locator('#confirm-headcount').fill('999');
  await expect(biz.getByText(/超出部分须填写增编申请人数/)).toBeVisible();
  await expect(biz.getByRole('button', { name: '确认并继续审批' })).toBeDisabled();
  await biz.locator('#confirm-headcount').fill('1');
  await biz.locator('#confirm-salary').fill('8-25K/月×13');
  await biz.locator('#confirm-duties').fill('维护客户并跟进合同');
  await expect(biz.getByText(/HRD 薪资加签（薪酬审批负责人）/)).toBeVisible();
  await biz.getByRole('button', { name: '确认并继续审批' }).click();
  await expect(card).toHaveCount(0);
  await login(page, 'hr');
  await page.goto(`/requisitions/${req.id}`);
  await expect(page.getByText('岗位职责：维护客户关系 → 维护客户并跟进合同')).toBeVisible();
  await expect(page.getByText('薪资带宽：8-12K/月×13 → 8-25K/月×13')).toBeVisible();
  await page.screenshot({
    path: 'test-results/manager-confirmation-differences.png',
    fullPage: true,
  });
  await login(biz, 'director', 'http://127.0.0.1:5184');
  await card.getByRole('button', { name: '查看需求 / 驳回' }).click();
  await expect(biz.getByText('岗位职责：维护客户关系 → 维护客户并跟进合同')).toBeVisible();
  await expect(biz.getByText('岗位职责：维护客户关系 → 维护客户并跟进合同')).toBeInViewport();
  await biz.screenshot({ path: 'test-results/manager-confirmation-mobile.png', fullPage: true });
  await biz.getByRole('button', { name: '关闭详情' }).click();
  for (const user of ['director', 'hrbp', 'salary_hrd']) {
    if (user !== 'director') await login(biz, user, 'http://127.0.0.1:5184');
    await card.getByRole('button', { name: '通过', exact: true }).click();
    await expect(card).toHaveCount(0);
  }
  await page.reload();
  await expect(page.getByText('需求审批已通过', { exact: true })).toBeVisible();
  await context.close();
  expect(errors).toEqual([]);
});

test('HR Web 确认：过期版本保留输入，响应丢失后用相同幂等键重试', async ({ page, request }) => {
  const req = await salesRequest(request, `版本确认-${Date.now()}`);
  await login(page, 'sales');
  await page.goto(`/requisitions/${req.id}`);
  await page.getByRole('button', { name: '修改并确认' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.locator('#confirm-duties').fill('本地尚未提交的职责');
  await expect(dialog.getByRole('button', { name: '确认并继续审批' })).toBeEnabled();
  const path = `${apiRoot}/hr/requisitions/${req.id}`;
  const withdrawn = await request.post(`${path}/withdraw`, {
    headers: await apiHeaders(request, 'hr'),
    data: { expected_version: req.version },
  });
  expect(withdrawn.ok()).toBeTruthy();
  const resubmitted = await request.post(`${path}/submit`, {
    headers: await apiHeaders(request, 'hr'),
    data: { expected_version: (await withdrawn.json()).version },
  });
  expect(resubmitted.ok()).toBeTruthy();
  await dialog.getByRole('button', { name: '确认并继续审批' }).click();
  await expect(dialog.getByRole('alert')).toContainText('修改内容已保留');
  await expect(dialog.locator('#confirm-duties')).toHaveValue('本地尚未提交的职责');
  await expect(dialog.getByRole('button', { name: '确认并继续审批' })).toBeDisabled();
  await dialog.getByRole('button', { name: 'Close' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('提交审批 ·')).toHaveCount(2);
  await page.getByRole('button', { name: '修改并确认' }).click();
  await dialog.locator('#confirm-reason').fill('经理确认后的招聘背景');
  await expect(dialog.getByRole('button', { name: '确认并继续审批' })).toBeEnabled();
  const keys: string[] = [];
  await page.route(`**/requisitions/${req.id}/confirm`, async (route) => {
    keys.push(route.request().headers()['idempotency-key']!);
    const response = await route.fetch();
    if (keys.length === 1)
      await route.fulfill({
        status: 503,
        json: { error: { code: 'TEMPORARY', message: '模拟确认响应丢失' } },
      });
    else await route.fulfill({ response });
  });
  await dialog.getByRole('button', { name: '确认并继续审批' }).click();
  await expect(dialog.getByRole('alert')).toContainText('模拟确认响应丢失');
  await expect(dialog.locator('#confirm-reason')).toBeDisabled();
  await dialog.getByRole('button', { name: '重试本次确认' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText('招聘原因：业务扩展 → 经理确认后的招聘背景')).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const result = await request.get(path, { headers: await apiHeaders(request, 'hr') });
  expect(
    (await result.json()).history.filter(
      (item: { action: string }) => item.action === 'manager_confirmed',
    ),
  ).toHaveLength(1);
});

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
  await expect(page.getByRole('region', { name: '审批处理' })).toContainText('需求尚未提交');
  await expect(page.getByRole('button', { name: '通过审批', exact: true })).toBeDisabled();
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
  await expect(page.getByRole('region', { name: '审批处理' })).toContainText('等待修改后重新提交');
  await expect(page.getByRole('button', { name: '通过审批', exact: true })).toBeDisabled();
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

test('薪资表联调：缺配置拦截、维护版本、超带宽独立 HRD 审批', async ({ page, browser }) => {
  const series = `薪资联调${Date.now()}`;
  const title = `薪资审批${Date.now()}`;
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await login(page, 'hr');
  await page.goto('/requisitions/new');
  await select(page, '#f-dept', '经营分析部');
  await page.getByText('新增', { exact: true }).click();
  await page.locator('#f-headcount').fill('2');
  await page.locator('#f-title').fill(title);
  await page.locator('#f-series').fill(series);
  await page.locator('#f-level').fill('P3');
  await page.locator('#f-city').fill('深圳');
  await select(page, '#f-reportTo', '田野');
  await page
    .locator('#f-expectedOnboard')
    .fill(new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10));
  await page.locator('#f-salary').fill('8-12K/月×13');
  await page.locator('#f-reason').fill('扩大分析团队');
  await page.locator('#f-duties').fill('分析经营数据');
  await page.locator('#f-requirements').fill('数据分析能力');
  await expect(page.getByText(new RegExp(`职级薪资表缺少已生效的 ${series}`))).toBeVisible();
  await expect(page.getByRole('button', { name: '提交审批', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '保存草稿并返回' }).click();
  await page.getByRole('link', { name: title, exact: true }).click();
  const detailUrl = page.url();

  await page.getByRole('menuitem', { name: /职级薪资表/ }).click();
  await page.getByRole('button', { name: '新增薪资配置', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('职位序列', { exact: true }).fill(series);
  await dialog.getByLabel('单个职级', { exact: true }).fill('P3');
  await dialog.getByLabel('城市', { exact: true }).fill('深圳');
  await dialog.getByLabel('月薪下限（K）', { exact: true }).fill('8');
  await dialog.getByLabel('月薪上限（K）', { exact: true }).fill('10');
  await dialog.getByRole('button', { name: '保存薪资版本' }).click();
  await expect(dialog).toHaveCount(0);
  const row = page.getByRole('row').filter({ hasText: series });
  await expect(row.getByRole('cell').nth(3)).toContainText('8–10K/月 × 13');

  await page.goto(detailUrl);
  await page.getByRole('button', { name: '编辑需求' }).click();
  await expect(page.getByText('HRD 薪资加签', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '提交审批', exact: true }).click();
  await expect(page).toHaveURL(detailUrl);
  await expect(page.getByText('HRD 薪资加签', { exact: true })).toBeVisible();

  await page.getByRole('menuitem', { name: /职级薪资表/ }).click();
  await row.getByRole('button', { name: '发布新版本' }).click();
  await dialog.getByLabel('月薪上限（K）', { exact: true }).fill('20');
  await dialog.getByRole('button', { name: '保存薪资版本' }).click();
  await expect(dialog).toHaveCount(0);
  await row.getByRole('button', { name: '版本历史' }).click();
  await expect(dialog.getByRole('cell', { name: '8–10K/月 × 13', exact: true })).toBeVisible();
  await expect(dialog.getByRole('cell', { name: '8–20K/月 × 13', exact: true })).toBeVisible();
  await page.screenshot({
    path: 'test-results/salary-history.png',
    fullPage: true,
    animations: 'disabled',
  });
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();

  const bizContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const biz = await bizContext.newPage();
  biz.on('pageerror', (e) => errors.push(e.message));
  for (const actor of ['analyst', 'director', 'hrbp']) {
    await login(biz, actor, 'http://127.0.0.1:5184');
    const card = biz.locator('article').filter({ hasText: title });
    await card.getByRole('button', { name: '通过', exact: true }).click();
    await expect(card).toHaveCount(0);
  }
  await page.goto(detailUrl);
  await expect(page.getByText('需求审批已通过', { exact: true })).toHaveCount(0);
  await expect(page.getByText(/审批中/)).toBeVisible();
  await login(biz, 'salary_hrd', 'http://127.0.0.1:5184');
  const hrdCard = biz.locator('article').filter({ hasText: title });
  await expect(hrdCard).toContainText('HRD 薪资加签');
  await hrdCard.getByRole('button', { name: '通过', exact: true }).click();
  await expect(hrdCard).toHaveCount(0);
  await page.reload();
  await expect(page.getByText('需求审批已通过', { exact: true })).toBeVisible();
  await bizContext.close();
  expect(errors).toEqual([]);
});
