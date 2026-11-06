import { test, expect, type APIRequestContext } from '@playwright/test';
import { resolve } from 'node:path';
import { headers, login, ready } from './position-helpers';

const API = 'http://127.0.0.1:8010/api/v1/hr';
async function openPosition(request: APIRequestContext, name: string) {
  const { pos } = await ready(request, name);
  let p = await (
    await request.get(`${API}/positions/${pos.id}`, { headers: await headers(request) })
  ).json();
  for (const [action, actor] of [
    ['confirm_profile', 'manager'],
    ['publish', 'hr'],
  ]) {
    const r = await request.post(`${API}/positions/${pos.id}/actions`, {
      headers: await headers(request, actor),
      data: { action, expected_version: p.version },
    });
    expect(r.ok()).toBeTruthy();
    p = await r.json();
  }
  return p;
}

test('candidate creation retries safely, attaches both directions, checks consent and masks business H5', async ({
  page,
  request,
  browser,
}, info) => {
  const title = `候选人联调岗位-${Date.now()}`;
  const pos = await openPosition(request, title);
  await login(page, 'hr', '/candidates');
  let interrupted = false;
  const keys: string[] = [];
  await page.route('**/api/v1/hr/candidates', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    keys.push(route.request().headers()['idempotency-key']);
    if (!interrupted) {
      interrupted = true;
      await route.fetch();
      await route.abort('failed');
    } else await route.continue();
  });
  await page.getByRole('button', { name: '新建候选人', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const name = `联调候选人-${Date.now()}`;
  await dialog.getByLabel('姓名', { exact: true }).fill(name);
  await dialog.getByLabel('手机号', { exact: true }).fill('13800009992');
  await dialog.getByLabel('邮箱', { exact: true }).fill('candidate-e2e@example.com');
  await dialog.getByLabel('技能', { exact: true }).fill('客户沟通、Python');
  await dialog.getByRole('button', { name: '保存候选人', exact: true }).click();
  await expect(dialog.getByRole('button', { name: '重试本次操作' })).toBeVisible();
  await expect(dialog.getByLabel('姓名', { exact: true })).toBeDisabled();
  await dialog.getByRole('button', { name: '重试本次操作' }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  expect(keys.length).toBe(2);
  expect(keys[0]).toBe(keys[1]);
  const candidateUrl = page.url();
  await expect(page.getByText('138****9992', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '登记候选人授权' }).click();
  await dialog.getByLabel('授权证据').fill('signed:fixture-001');
  await dialog.getByLabel('操作依据').fill('候选人已签署招聘和 AI 评估授权');
  await dialog.getByRole('button', { name: '保存操作' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText('已授权', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '挂到其他岗位' }).click();
  await dialog.getByLabel('搜索挂入对象').fill(title);
  await dialog.getByLabel('搜索挂入对象').press('Enter');
  await expect(dialog.getByLabel('目标岗位').locator('option', { hasText: title })).toHaveCount(1);
  await dialog.getByLabel('目标岗位').selectOption(pos.id);
  await dialog.getByRole('button', { name: '确认挂入' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('link', { name: title, exact: true })).toBeVisible();
  await page.goto(`/positions/${pos.id}`);
  await expect(
    page.getByRole('region', { name: '岗位候选人' }).getByRole('link', { name, exact: true }),
  ).toBeVisible();
  await page.goto(candidateUrl);
  for (const label of ['沟通中', 'AI 评估']) {
    await page.getByRole('button', { name: '推进下一阶段', exact: true }).click();
    await dialog.getByRole('button', { name: '确认操作', exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByRole('cell', { name: label, exact: true })).toBeVisible();
  }
  const biz = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await login(biz, 'manager', `http://127.0.0.1:5184/positions/${pos.id}`);
  await biz.goto(`http://127.0.0.1:5184/positions/${pos.id}`);
  await biz.getByRole('button', { name: '查看候选人资料' }).click();
  await expect(
    biz.getByRole('region', { name: '候选人资料' }).getByText('手机：138****9992'),
  ).toBeVisible();
  await expect(biz.getByText('13800009992', { exact: false })).toHaveCount(0);
  await biz.screenshot({ path: info.outputPath('candidate-biz-h5.png'), fullPage: true });
  await biz.close();
  await page.getByRole('button', { name: '淘汰候选人', exact: true }).click();
  await dialog.getByLabel('淘汰原因分类').selectOption('experience');
  await dialog.getByLabel('操作原因').fill('所需行业经验不足');
  await dialog.getByRole('button', { name: '确认操作' }).click();
  await expect(page.getByRole('cell', { name: '已淘汰', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '挂到其他岗位' }).click();
  await dialog.getByLabel('搜索挂入对象').fill(title);
  await dialog.getByLabel('搜索挂入对象').press('Enter');
  await expect(dialog.getByLabel('目标岗位').locator('option', { hasText: title })).toHaveCount(1);
  await dialog.getByLabel('目标岗位').selectOption(pos.id);
  await dialog.getByRole('button', { name: '确认挂入' }).click();
  await expect(dialog.getByRole('alert')).toContainText('冷却期');
  await dialog.getByLabel('强制挂入原因').fill('候选人补充了相关项目证明');
  await dialog.getByRole('button', { name: '确认挂入' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('cell', { name: 'AI 触达', exact: true })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: info.outputPath('candidate-detail.png'), fullPage: true });
});

test('resume upload parses, deduplicates, downloads and preserves pending completion', async ({
  page,
}, info) => {
  await login(page, 'hr', '/candidates');
  for (let i = 0; i < 2; i++) {
    await page.getByRole('button', { name: '上传简历', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog
      .getByLabel('选择简历文件')
      .setInputFiles(resolve('frontend/tests/fixtures/candidate-resume.docx'));
    await dialog.getByRole('button', { name: '开始上传' }).click();
    await expect(dialog.getByText('完成 1 / 1，失败 0')).toBeVisible();
    await expect(dialog.getByText(i ? /归入已有档案/ : /新建档案/)).toBeVisible();
    await dialog.getByRole('link', { name: '查看档案' }).click();
    await expect(page.getByRole('heading', { name: '简历自动化测试', exact: true })).toBeVisible();
    if (i === 0) await page.goto('/candidates');
  }
  await expect(page.getByRole('button', { name: '下载原件（记审计）' })).toHaveCount(2);
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载原件（记审计）' }).first().click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe('candidate-resume.docx');
  await page.getByText('查看解析字段与段落', { exact: true }).first().click();
  await expect(page.getByText('年龄：28', { exact: false })).toHaveCount(0);
  await page.getByRole('button', { name: '上传简历版本' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('选择简历文件').setInputFiles({
    name: 'scan.png',
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5d0AAAAASUVORK5CYII=',
      'base64',
    ),
  });
  await dialog.getByRole('button', { name: '开始上传' }).click();
  await expect(dialog.getByText(/待人工补全/)).toBeVisible();
  await dialog.getByRole('link', { name: '查看档案' }).click();
  await expect(page.getByText('待人工补全', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '核对并修正资料' }).last().click();
  await dialog.getByRole('button', { name: '读取联系方式并开始编辑（记审计）' }).click();
  await dialog.getByLabel('城市', { exact: true }).fill('深圳');
  await dialog.getByRole('button', { name: '保存操作' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByText('已由 HR 核对修正；原件保持不变')).toBeVisible();
  await page.screenshot({ path: info.outputPath('candidate-resumes.png'), fullPage: true });
});

test('similar records can merge and undo; contact opt out and erasure work in the UI', async ({
  page,
  request,
}) => {
  const name = `合并测试-${Date.now()}`;
  const create = async () => {
    const r = await request.post(`${API}/candidates`, {
      headers: await headers(request),
      data: { profile: { name, school: '测试大学', graduation_year: 2020 } },
    });
    expect(r.ok()).toBeTruthy();
    return (await r.json()).candidate;
  };
  const first = await create();
  const second = await create();
  await login(page, 'hr', `/candidates/${first.id}`);
  await page.getByRole('button', { name: '核对并合并' }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('操作依据').fill('候选人确认两个档案属于本人');
  await dialog.getByRole('button', { name: '保存操作' }).click();
  await expect(page.getByRole('heading', { name: '已合并档案' })).toBeVisible();
  await page.getByRole('button', { name: '撤销合并', exact: true }).click();
  await dialog.getByRole('button', { name: '保存操作' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('button', { name: '核对并合并' })).toBeVisible();
  await page.getByRole('button', { name: '标记不再联系' }).click();
  await dialog.getByLabel('操作依据').fill('候选人本人要求不再联系');
  await dialog.getByRole('button', { name: '保存操作' }).click();
  await expect(page.getByRole('button', { name: '挂到其他岗位' })).toBeDisabled();
  await page.getByRole('button', { name: '处理删除请求' }).click();
  await dialog.getByLabel('操作依据').fill('候选人已提交删除本人档案申请');
  await dialog.getByRole('button', { name: '确认执行删除' }).click();
  await expect(page).toHaveURL(/\/candidates$/);
  expect(
    (
      await request.get(`${API}/candidates/${first.id}`, { headers: await headers(request) })
    ).status(),
  ).toBe(404);
  expect(
    (await request.get(`${API}/candidates/${second.id}`, { headers: await headers(request) })).ok(),
  ).toBeTruthy();
});
