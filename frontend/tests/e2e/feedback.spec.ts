import { test, expect } from '@playwright/test';
import { headers, login } from './position-helpers';
test.use({ actionTimeout: 15_000 });

test('反馈回归：薪资带入、字段预检、工作台审批入口与撤回权限', async ({ page, request }, info) => {
  const root = 'http://127.0.0.1:8010/api/v1/hr';
  await login(page, 'hr', '/requisitions/new');
  await page.locator('#f-dept').click();
  await page.locator('.ant-select-tree-title').getByText('客服中心', { exact: true }).click();
  const salary = await (
    await request.get(
      `${root}/requisition-form/salary-options?dept=${encodeURIComponent('客服中心')}`,
      { headers: await headers(request) },
    )
  ).json();
  const band = salary.items.find(
    (item: { series: string; grade: string; city: string }) =>
      item.series === '客服' && item.grade === 'P3' && item.city === '深圳',
  );
  expect(band).toBeTruthy();
  await page.locator('#salary-template').click();
  await page
    .locator('.ant-select-item-option-content')
    .filter({ hasText: '客服 · P3 · 深圳' })
    .click();
  await expect(page.locator('#f-series')).toHaveValue('客服');
  await expect(page.locator('#f-level')).toHaveValue('P3');
  await expect(page.locator('#f-city')).toHaveValue('深圳');
  await expect(page.locator('#f-salary')).not.toHaveValue('');
  await page.locator('#f-salary').fill('不合法金额');
  await expect(page.locator('#f-salary')).toHaveAttribute('aria-invalid', 'true');
  await page.locator('#f-salary').press('Tab');
  await expect(
    page.locator('.ant-form-item').filter({ has: page.locator('#f-salary') }),
  ).toContainText('填写下限');
  await page.screenshot({ path: info.outputPath('field-precheck.png'), fullPage: true });

  const title = `合成反馈审批-${Date.now()}`;
  const response = await request.post(`${root}/requisitions`, {
    headers: await headers(request),
    data: {
      title,
      dept: '客服中心',
      employmentType: '外包',
      recruitType: '社招',
      reqType: '新增',
      headcount: '1',
      series: '客服',
      level: 'P3',
      city: '深圳',
      reportToId: 'manager',
      reportTo: '何美玲',
      salary: '8-12K/月×13',
      expectedOnboard: new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10),
      reason: '合成反馈测试',
      duties: '处理咨询',
      requirements: '沟通能力',
    },
  });
  expect(response.status()).toBe(201);
  const req = await response.json();
  await login(page, 'manager', '/workbench');
  const link = page.getByRole('link', { name: `${title} · 去审批`, exact: true });
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/requisitions/${req.id}$`));
  await expect(page.getByRole('button', { name: '撤回需求', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '驳回需求', exact: true })).toBeEnabled();
  await page.screenshot({ path: info.outputPath('approval-owner-only.png'), fullPage: true });
  await login(page, 'manager', 'http://127.0.0.1:5184/workbench');
  await page.getByRole('link', { name: `${title} · 去审批`, exact: true }).click();
  await expect(page.getByRole('button', { name: '确认驳回', exact: true })).toBeVisible();
});
