import { test, expect } from '@playwright/test';
import { headers, login, approve, projection, ready, clickAction } from './position-helpers';
test.use({ actionTimeout: 15_000 });
const API = 'http://127.0.0.1:8010/api/v1';

test('审批事件自动生成岗位：需求回链、画像确认门禁、发布暂停恢复关闭', async ({
  page,
  request,
}) => {
  const title = `岗位闭环-${Date.now()}`;
  const req = await approve(request, title);
  await login(page, 'hr');
  await page.goto(`/requisitions/${req.id}`);
  const link = page.getByRole('link', { name: `生成的岗位：${title} · 待发布` });
  await expect(link).toBeVisible();
  await link.click();
  const positionUrl = page.url();
  await expect(page.getByRole('heading', { name: `${title} 待发布` })).toBeVisible();
  await expect(page.getByRole('button', { name: '发布岗位' })).toBeDisabled();
  await expect(page.getByText('发布前请先由用人经理确认画像。')).toBeVisible();
  await page.getByRole('button', { name: '编辑画像与 JD' }).click();
  await page.getByLabel('必备条件', { exact: true }).fill('有客户服务经验，善于沟通');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await login(page, 'manager');
  await page.goto(positionUrl);
  await expect(page.getByRole('button', { name: '发布岗位' })).toHaveCount(0);
  await clickAction(page, '确认画像');
  await expect(page.getByText('画像已确认', { exact: true })).toBeVisible();
  await login(page, 'hr');
  await page.goto(positionUrl);
  await clickAction(page, '发布岗位');
  await expect(page.getByRole('heading', { name: `${title} 招聘中` })).toBeVisible();
  await page.getByRole('button', { name: '暂停招聘' }).click();
  await page.getByLabel('暂停原因', { exact: true }).fill('业务计划调整');
  await page.getByLabel('在途处理方式').selectOption('freeze');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('heading', { name: `${title} 已暂停` })).toBeVisible();
  await clickAction(page, '恢复招聘');
  await expect(page.getByRole('heading', { name: `${title} 招聘中` })).toBeVisible();
  await page.getByRole('button', { name: '关闭岗位', exact: true }).click();
  await page.getByLabel('关闭原因', { exact: true }).selectOption('需求取消');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('heading', { name: `${title} 已关闭` })).toBeVisible();
  await page.screenshot({ path: 'test-results/position-lifecycle.png', fullPage: true });
  await page.getByRole('link', { name: '返回岗位列表' }).click();
  await expect(page.getByRole('row').filter({ hasText: title })).toContainText('已关闭');
  await page.goto(`/requisitions/${req.id}`);
  await expect(page.getByRole('link', { name: `生成的岗位：${title} · 已关闭` })).toBeVisible();
});

test('同岗需求明确选择合并，响应丢失原键重试，不重复累计人数', async ({ page, request }) => {
  const title = `同岗合并-${Date.now()}`;
  const first = await ready(request, title);
  const second = await approve(request, title);
  await expect.poll(async () => (await projection(request, second.id)).status).toBe('decision');
  await login(page, 'hr');
  await page.goto(`/requisitions/${second.id}`);
  await page.getByLabel('合并到岗位').selectOption(first.pos.id);
  const keys: string[] = [];
  await page.route(`**/requisitions/${second.id}/position`, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    keys.push(route.request().headers()['idempotency-key']!);
    const response = await route.fetch();
    if (keys.length === 1)
      await route.fulfill({
        status: 503,
        json: { error: { code: 'TEMPORARY', message: '模拟合并响应丢失' } },
      });
    else await route.fulfill({ response });
  });
  await page.getByRole('button', { name: '并入选中岗位' }).click();
  await expect(page.getByText('模拟合并响应丢失', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '重试本次操作' }).click();
  await expect(page.getByRole('link', { name: `生成的岗位：${title} · 待发布` })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const pos = await (
    await request.get(`${API}/hr/positions/${first.pos.id}`, { headers: await headers(request) })
  ).json();
  expect(pos.planned).toBe(2);
  expect(pos.requisitionIds).toHaveLength(2);
});

test('岗位版本冲突保留画像输入，状态操作网络失败后原键重试', async ({ page, request }) => {
  const { pos } = await ready(request, `岗位冲突-${Date.now()}`);
  await login(page, 'hr');
  await page.goto(`/positions/${pos.id}`);
  await page.getByRole('button', { name: '编辑画像与 JD' }).click();
  await page.getByLabel('必备条件', { exact: true }).fill('未提交的本地画像');
  const update = await request.post(`${API}/hr/positions/${pos.id}/actions`, {
    headers: await headers(request, 'manager'),
    data: { expected_version: 1, action: 'confirm_profile' },
  });
  expect(update.ok()).toBeTruthy();
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('输入已保留');
  await expect(page.getByLabel('必备条件', { exact: true })).toHaveValue('未提交的本地画像');
  await expect(page.getByRole('dialog').getByRole('button', { name: '确认操作' })).toBeDisabled();
  await page.getByRole('button', { name: '关闭弹窗' }).click();
  await expect(page.getByText('画像已确认', { exact: true })).toBeVisible();
  const keys: string[] = [];
  await page.route(`**/positions/${pos.id}/actions`, async (route) => {
    keys.push(route.request().headers()['idempotency-key']!);
    const response = await route.fetch();
    if (keys.length === 1)
      await route.fulfill({
        status: 503,
        json: { error: { code: 'TEMPORARY', message: '模拟发布响应丢失' } },
      });
    else await route.fulfill({ response });
  });
  await clickAction(page, '发布岗位');
  await expect(page.getByRole('dialog').getByRole('alert')).toContainText('模拟发布响应丢失');
  await page.getByRole('button', { name: '重试本次操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const saved = await (
    await request.get(`${API}/hr/positions/${pos.id}`, { headers: await headers(request) })
  ).json();
  expect(saved.history.filter((h: { action: string }) => h.action === 'publish')).toHaveLength(1);
});
