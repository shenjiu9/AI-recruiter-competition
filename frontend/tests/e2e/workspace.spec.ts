import { test, expect } from '@playwright/test';
import { headers, login, ready } from './position-helpers';

test.use({ actionTimeout: 15_000 });

test('workspace shows real totals, searches candidates and opens the notification panel', async ({
  page,
  request,
}, info) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page, 'hr', '/workbench');
  await expect(page.getByRole('heading', { name: '招聘工作台', exact: true })).toBeVisible();
  const response = await request.get('http://127.0.0.1:8010/api/v1/hr/workbench-live', {
    headers: await headers(request),
  });
  expect(response.ok()).toBeTruthy();
  const data = await response.json();
  await expect(
    page
      .locator('.rc-metric')
      .filter({ hasText: '招聘中岗位' })
      .locator('.ant-statistic-content-value'),
  ).toHaveText(String(data.counts.open_positions));
  await page.getByRole('button', { name: '消息中心', exact: true }).click();
  await expect(page.locator('#requisition-notices')).toHaveAttribute('open', '');
  await page.getByRole('button', { name: 'AI 助手', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'AI 任务与复核', exact: true })).toBeVisible();
  await page.getByLabel('全局搜索', { exact: true }).fill('视觉回归查询');
  const searchResult = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname.endsWith('/candidates') && url.searchParams.get('query') === '视觉回归查询';
  });
  await page.getByLabel('全局搜索', { exact: true }).press('Enter');
  await expect(page).toHaveURL(/\/candidates\?query=/);
  expect((await searchResult).ok()).toBeTruthy();
  await expect(page.getByRole('searchbox', { name: '搜索候选人', exact: true })).toHaveValue(
    '视觉回归查询',
  );
  await expect(page.getByRole('heading', { name: '候选人', exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath('desktop-workspace.png'), fullPage: true });
});

test('business bottom navigation remains usable on a small screen without horizontal overflow', async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await login(page, 'manager', 'http://127.0.0.1:5184/');
  const nav = page.getByRole('navigation', { name: '业务导航' });
  await expect(nav).toBeVisible();
  for (const [label, path] of [
    ['岗位', '/positions'],
    ['面试', '/interviews'],
    ['工作台', '/workbench'],
    ['待办', '/'],
  ]) {
    await nav.getByText(label, { exact: true }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(path);
    await expect(nav).toBeVisible();
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      )
      .toBeTruthy();
  }
  await page.screenshot({ path: info.outputPath('mobile-navigation.png'), fullPage: true });
});

test('automation waits for a named position selection instead of showing an invalid-ID error', async ({
  page,
  request,
}) => {
  const title = `策略选择-${Date.now()}`;
  await ready(request, title);
  await login(page, 'hr', '/settings/automation');
  await expect(page.getByText('选择一个岗位，查看并调整它的自动化策略。')).toBeVisible();
  await expect(page.getByText('岗位不存在或不在可见范围内')).toHaveCount(0);
  await page.getByRole('combobox', { name: '策略岗位' }).fill(title);
  await page
    .locator('.ant-select-item-option-content')
    .getByText(`${title} · 客服中心`, { exact: true })
    .click();
  await expect(page.getByLabel('淘汰等级')).toBeVisible();
  await expect(page.getByLabel('淘汰等级').locator('option[value="3"]')).toHaveCount(0);
});
