import { test, expect } from '@playwright/test';
import { headers, login } from './position-helpers';
const API = 'http://127.0.0.1:8010/api/v1';
const confirm = '我已查看面评汇总并核实本次操作内容';

test('HR prepares, manager decides with retry, business approves, HR hands over and releases failed hire quota', async ({
  page,
  browser,
  request,
}, info) => {
  const rows = await (
    await request.get(`${API}/hr/hiring`, { headers: await headers(request) })
  ).json();
  const h = rows.items.find((v: { status: string }) => v.status === 'deciding');
  expect(h).toBeTruthy();
  await login(page, 'hr', `/hiring/${h.id}`);
  await page.getByLabel('候选人期望月薪').fill('10');
  await page
    .getByLabel('预计入职日期')
    .fill(new Date(Date.now() + 35 * 86400000).toISOString().slice(0, 10));
  await page.getByLabel('移交负责人', { exact: true }).selectOption('hr');
  await page.getByLabel('核实证据或移交凭证').fill('候选人书面确认');
  await page.getByLabel(confirm).check();
  await page.getByRole('button', { name: '保存核实信息' }).click();
  await expect(page.getByText('候选人期望：10 K/月 × 13 月')).toBeVisible();
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await login(mobile, 'manager', `http://127.0.0.1:5184/hiring/${h.id}`);
    await expect(mobile.getByRole('heading', { name: '面评汇总' })).toBeVisible();
    await expect(mobile.getByText('候选人期望：10 K/月 × 13 月')).toHaveCount(0);
    let lost = false;
    const keys: string[] = [];
    await mobile.route(`**/api/v1/hr/hiring/${h.id}/actions`, async (route) => {
      if (route.request().postDataJSON().action !== 'decide') {
        await route.continue();
        return;
      }
      keys.push(route.request().headers()['idempotency-key']);
      if (!lost) {
        lost = true;
        await route.fetch();
        await route.abort('failed');
      } else await route.continue();
    });
    await mobile.getByLabel(confirm).check();
    await mobile.getByRole('button', { name: '决定录用并发起审批' }).click();
    await expect(mobile.getByRole('button', { name: '重试本次操作' })).toBeVisible();
    await mobile.getByRole('button', { name: '重试本次操作' }).click();
    await expect(mobile.getByRole('article', { name: '录用详情' })).toContainText('审批中');
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await mobile.unrouteAll();
    for (const actor of ['director', 'hrbp']) {
      await login(mobile, actor, `http://127.0.0.1:5184/hiring/${h.id}`);
      await mobile.getByLabel(confirm).check();
      await mobile.getByRole('button', { name: '通过录用审批' }).click();
      await expect(mobile.getByRole('button', { name: '通过录用审批' })).toHaveCount(0);
    }
    await mobile.screenshot({ path: info.outputPath('business-hiring.png'), fullPage: true });
  } finally {
    await mobile.close();
  }
  await page.reload();
  await expect(page.getByRole('article', { name: '录用详情' })).toContainText('已录用 · 待移交');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载移交单（Excel）' }).click();
  expect((await download).suggestedFilename()).toBe('录用移交单.xlsx');
  await page.getByLabel('核实证据或移交凭证').fill('负责 HR 已接收移交单，回执 2026-1');
  await page.getByLabel(confirm).check();
  await page.getByRole('button', { name: '登记已实际移交' }).click();
  await expect(page.getByLabel('回填结果')).toBeVisible();
  await page.getByLabel('回填结果').selectOption('accepted');
  await page.getByLabel(confirm).check();
  await page.getByRole('button', { name: '保存录用结果' }).click();
  await expect(page.getByRole('article', { name: '录用详情' })).toContainText('回填：已接受');
  await page.getByLabel('回填结果').selectOption('no_show');
  await page.getByLabel('录用操作原因').fill('候选人确认不入职');
  await page.getByLabel(confirm).check();
  await page.getByRole('button', { name: '保存录用结果' }).click();
  await expect(page.getByRole('article', { name: '录用详情' })).toContainText('可招 1 人');
  await expect(page.getByRole('article', { name: '录用详情' })).toContainText('回填：未入职');
  await page.screenshot({ path: info.outputPath('hr-handoff-result.png'), fullPage: true });
  await page.goto(`/workbench`);
  await expect(page.getByRole('heading', { name: '招聘工作台' })).toBeVisible();
  const pos = await (
    await request.get(`${API}/hr/positions/${h.position_id}`, { headers: await headers(request) })
  ).json();
  expect(pos.hired).toBe(0);
});

test('automation UI preserves hard limits and restores configuration as a new version', async ({
  page,
}, info) => {
  await login(page, 'admin', '/settings/automation');
  await expect(page.getByLabel('淘汰等级').locator('option[value="3"]')).toHaveCount(0);
  await expect(page.getByLabel('录用建议等级').locator('option')).toHaveCount(1);
  await page.getByLabel('运行模式').selectOption('shadow');
  await page.getByRole('button', { name: '保存策略配置' }).click();
  await expect(page.getByRole('button', { name: '恢复版本 1 为新版本' })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('运行模式')).toHaveValue('shadow');
  await page.getByRole('button', { name: '恢复版本 1 为新版本' }).click();
  await expect(page.getByLabel('运行模式')).toHaveValue('manual');
  await page.screenshot({ path: info.outputPath('automation-rules.png'), fullPage: true });
});
