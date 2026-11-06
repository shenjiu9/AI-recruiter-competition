import { test, expect, type APIRequestContext } from '@playwright/test';
import { ready, login, headers, clickAction } from './position-helpers';

const API = 'http://127.0.0.1:8010/api/v1';
const BIZ = 'http://127.0.0.1:5184';
test.use({ actionTimeout: 15_000 });

async function get(request: APIRequestContext, id: string) {
  const response = await request.get(`${API}/hr/positions/${id}`, {
    headers: await headers(request),
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}
async function act(
  request: APIRequestContext,
  id: string,
  actor: string,
  action: string,
  extra: Record<string, unknown> = {},
) {
  const pos = await get(request, id);
  const response = await request.post(`${API}/hr/positions/${id}/actions`, {
    headers: await headers(request, actor),
    data: { action, expected_version: pos.version, ...extra },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

test('在招画像保留旧版，手机确认后生效；知识库披露、修订与失效', async ({ page, request }) => {
  const { pos } = await ready(request, `版本知识-${Date.now()}`);
  await act(request, pos.id, 'manager', 'confirm_profile');
  await act(request, pos.id, 'hr', 'publish');
  await login(page, 'hr');
  await page.goto(`/positions/${pos.id}`);
  await page.getByRole('button', { name: '编辑画像与 JD' }).click();
  await page.getByLabel('必备条件', { exact: true }).fill('三年服务经验');
  await page.getByLabel('加分项', { exact: true }).fill('英文沟通\n系统操作');
  await page.getByLabel('第 1 项权重').selectOption('high');
  await page.getByLabel('第 2 项权重').selectOption('low');
  await page.getByLabel('必问项', { exact: true }).fill('能否接受轮班');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect((await get(request, pos.id)).activeProfile.version).toBe(1);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'manager', BIZ);
  await page.getByRole('link', { name: '岗位画像与关闭确认' }).click();
  await page.getByRole('link', { name: new RegExp('版本知识-') }).click();
  await expect(page.getByText('当前生效：第 1 版')).toBeVisible();
  const keys: string[] = [];
  await page.route(`**/positions/${pos.id}/actions`, async (route) => {
    keys.push(route.request().headers()['idempotency-key']!);
    const response = await route.fetch();
    if (keys.length === 1)
      await route.fulfill({
        status: 503,
        json: { error: { code: 'TEMPORARY', message: '模拟确认响应丢失' } },
      });
    else await route.fulfill({ response });
  });
  await page.getByRole('button', { name: '确认第 2 版画像' }).click();
  await expect(page.getByRole('alert')).toContainText('模拟确认响应丢失');
  await expect(page.getByRole('button', { name: '确认第 2 版画像' })).toBeDisabled();
  await page.getByRole('button', { name: '重试本次操作' }).click();
  await expect(page.getByText('当前生效：第 2 版')).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  await page.unroute(`**/positions/${pos.id}/actions`);
  await page.getByText('修改并确认画像', { exact: true }).click();
  await page.getByLabel('修改必备条件', { exact: true }).fill('三年客服经验，能独立处理复杂问题');
  await page.getByRole('button', { name: '保存修改并确认' }).click();
  await expect(page.getByText('当前生效：第 3 版')).toBeVisible();
  await page.getByLabel('知识内容', { exact: true }).fill('内部团队调配计划');
  await page.getByLabel('知识来源', { exact: true }).fill('用人经理确认');
  await page.getByRole('button', { name: '保存知识条目' }).click();
  await expect(page.locator('article').filter({ hasText: '内部团队调配计划' })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/position-mobile-review.png', fullPage: true });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1280, height: 900 });
  await login(page, 'hr', 'http://127.0.0.1:5183');
  await page.goto(`/positions/${pos.id}`);
  await page.getByRole('button', { name: '新增知识条目' }).click();
  await page.getByLabel('知识内容', { exact: true }).fill('办公地点在深圳');
  await page.getByLabel('知识来源', { exact: true }).fill('招聘说明');
  await page.getByLabel('披露级别', { exact: true }).selectOption('proactive');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: '对外答复预览' }).click();
  const preview = page.getByLabel('对外知识预览');
  await expect(preview).toContainText('办公地点在深圳');
  await expect(preview).not.toContainText('内部团队调配计划');
  await page
    .getByRole('row')
    .filter({ hasText: '办公地点在深圳' })
    .getByRole('button', { name: '修订条目' })
    .click();
  await page.getByLabel('知识内容', { exact: true }).fill('办公地点在深圳南山');
  await page.getByLabel('披露级别', { exact: true }).selectOption('asked');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(preview).not.toContainText('办公地点');
  await page.getByLabel('候选人已问到').check();
  await expect(preview).toContainText('办公地点在深圳南山');
  const saved = await get(request, pos.id);
  expect(saved.knowledge.filter((e: { active: boolean }) => !e.active)).toHaveLength(1);
  await page.getByText('画像版本历史与对比', { exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: 'test-results/position-content-desktop.png', fullPage: true });
});

test('共享 HR 编辑 JD，负责人审批发布，经理在手机确认关闭', async ({ page, request }) => {
  const { pos } = await ready(request, `审批协作-${Date.now()}`);
  await login(page, 'hr');
  await page.goto(`/positions/${pos.id}`);
  await page.getByRole('button', { name: '共享协作', exact: true }).click();
  await page.getByLabel('搜索共享 HR').fill('hrbp');
  await expect(page.locator('#shared-hr option[value="hrbp"]')).toHaveCount(1);
  await page.locator('#shared-hr').selectOption('hrbp');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: '发布审批设置' }).click();
  await page.getByLabel('发布与更新 JD 需招聘负责人审批').check();
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await login(page, 'hrbp');
  await page.goto(`/positions/${pos.id}`);
  await page.getByRole('button', { name: '编辑 JD', exact: true }).click();
  await page.getByLabel('JD 正文').fill('解决复杂客户问题，维护服务知识');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await act(request, pos.id, 'manager', 'confirm_profile');
  await login(page, 'hr');
  await page.goto(`/positions/${pos.id}`);
  await expect(page.getByRole('button', { name: '发布岗位' })).toBeDisabled();
  await clickAction(page, '批准 JD');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await clickAction(page, '发布岗位');
  await expect(page.getByRole('heading', { name: /审批协作-.*招聘中/ })).toBeVisible();
  await login(page, 'hrbp');
  await page.goto(`/positions/${pos.id}`);
  await page.getByRole('button', { name: '申请关闭', exact: true }).click();
  await page.getByLabel('关闭原因', { exact: true }).selectOption('需求取消');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByText('待用人经理确认关闭：需求取消')).toBeVisible();
  expect((await get(request, pos.id)).status).toBe('open');
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, 'manager', BIZ);
  await page.goto(`${BIZ}/positions/${pos.id}`);
  await page.getByRole('button', { name: '确认关闭岗位' }).click();
  await expect(page.getByText('已关闭 · 客服中心 · 1 人')).toBeVisible();
  expect((await get(request, pos.id)).status).toBe('closed');
});

test('面试配置保留版本、协作留言与岗位列表筛选', async ({ page, request }) => {
  const title = `流程配置-${Date.now()}`;
  const { pos } = await ready(request, title);
  await login(page, 'hr');
  await page.goto(`/positions/${pos.id}`);
  await page.getByRole('button', { name: '编辑面试流程' }).click();
  await page.getByRole('button', { name: '添加轮次' }).click();
  await page.getByLabel('第 1 轮名称', { exact: true }).fill('业务复试');
  await page.getByLabel('搜索第 1 轮面试官').fill('manager');
  await expect(page.locator('#round-0 option[value="manager"]')).toHaveCount(1);
  await page.locator('#round-0').selectOption('manager');
  await page.getByLabel('第 1 轮评价项').fill('问题分析与沟通');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: '编辑面试流程' }).click();
  await page.getByLabel('第 1 轮时长').selectOption('60');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const plans = (await get(request, pos.id)).interviewPlans;
  expect(plans.map((p: { rounds: { duration: number }[] }) => p.rounds[0]!.duration)).toEqual([
    30, 60,
  ]);
  await page.getByRole('button', { name: '添加留言' }).click();
  await page.getByLabel('留言内容').fill('请用人经理核对面试评价项');
  await page.getByRole('dialog').getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('请用人经理核对面试评价项', { exact: false })).toBeVisible();
  await page.getByRole('link', { name: '返回岗位列表' }).click();
  await page.getByLabel('搜索岗位').fill(title);
  await page.getByLabel('搜索岗位').press('Enter');
  await expect(page.getByRole('row').filter({ hasText: title })).toHaveCount(1);
});
