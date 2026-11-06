import { test, expect } from '@playwright/test';
import { headers, login } from './position-helpers';

const API = 'http://127.0.0.1:8010/api/v1';

test('signed candidate portal, retry deduplication, consent, HR takeover and rights requests', async ({
  page,
  browser,
  request,
}, info) => {
  const name = `沟通联调-${Date.now()}`;
  const response = await request.post(`${API}/hr/candidates`, {
    headers: await headers(request),
    data: { profile: { name, skills: 'Java' } },
  });
  expect(response.ok()).toBeTruthy();
  const candidate = (await response.json()).candidate;
  await login(page, 'hr', `/candidates/${candidate.id}`);
  const conversation = page.getByRole('region', { name: '候选人沟通' });
  await conversation.getByRole('button', { name: '生成专属链接' }).click();
  const url = await conversation.getByLabel('候选人专属链接').inputValue();
  expect(url).toContain('/#t=');
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await mobile.goto(url);
    await expect(mobile.getByRole('heading', { name: `${name}，您好` })).toBeVisible();
    const keys: string[] = [];
    let interrupted = false;
    await mobile.route('**/api/v1/candidate/actions', async (route) => {
      const body = route.request().postDataJSON();
      if (body.action !== 'send') {
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
    await mobile.getByLabel('候选人消息').fill('请问岗位工作地点？');
    await mobile.getByRole('button', { name: '发送消息', exact: true }).click();
    await expect(mobile.getByRole('button', { name: '重试本次操作' })).toBeVisible();
    await expect(mobile.getByLabel('候选人消息')).toBeDisabled();
    await mobile.getByRole('button', { name: '重试本次操作' }).click();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await expect(
      mobile.getByRole('log').getByText('请问岗位工作地点？', { exact: true }),
    ).toHaveCount(1);
    await expect(conversation.getByRole('log')).toContainText('请问岗位工作地点？');
    await mobile.getByRole('button', { name: '同意并授权' }).click();
    await mobile.getByRole('button', { name: '确定', exact: true }).click();
    await expect(mobile.getByText('授权状态：已授权。未授权也可以发送消息。')).toBeVisible();
    await expect(conversation.getByText('会话授权：已授权', { exact: true })).toBeVisible();
    await conversation.getByRole('button', { name: '接管会话' }).click();
    await expect(conversation).toContainText('人工接管中');
    await expect(mobile.getByText('招聘 HR 已接管会话，消息由人工回复。')).toBeVisible();
    await conversation.getByLabel('HR 消息').fill('您好，HR 已收到您的咨询。');
    await conversation.getByRole('button', { name: '发送消息', exact: true }).click();
    await expect(conversation.getByRole('log')).toContainText('您好，HR 已收到您的咨询。');
    const state = await (
      await request.get(`${API}/hr/candidates/${candidate.id}/conversation`, {
        headers: await headers(request),
      })
    ).json();
    if (state.messages.at(-1).status === 'sent')
      await expect(mobile.getByRole('log')).toContainText('您好，HR 已收到您的咨询。');
    else await expect(conversation.getByRole('log')).toContainText('等待发送');
    await mobile.getByLabel('资料请求说明').fill('技能请补充 SQL');
    await mobile.getByRole('button', { name: '提交更正请求' }).click();
    await expect(conversation).toContainText('技能请补充 SQL');
    await conversation.getByLabel('资料处理结果').fill('已收到补充证明，正在核实');
    await conversation.getByRole('button', { name: '登记处理结果' }).click();
    await expect(mobile.getByText(/更正请求已处理：已收到补充证明/)).toBeVisible();
    await mobile.getByRole('button', { name: '撤回授权', exact: true }).click();
    await mobile.getByRole('button', { name: '确定', exact: true }).click();
    await expect(conversation).toContainText('候选人已停止联系或撤回授权');
    await expect(
      conversation.getByRole('button', { name: '发送消息', exact: true }),
    ).toBeDisabled();
    await mobile.evaluate(() => window.scrollTo(0, 0));
    await mobile.screenshot({ path: info.outputPath('candidate-portal.png'), fullPage: true });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: info.outputPath('hr-conversation.png'), fullPage: true });
    await conversation.getByRole('button', { name: '撤销已有链接' }).click();
    await expect(mobile.getByRole('heading', { name: '专属链接不可用' })).toBeVisible();
  } finally {
    await mobile.close();
  }
});

test('candidate portal rejects missing and HR tokens without showing demo identity', async ({
  page,
  request,
}) => {
  await page.goto('http://127.0.0.1:5185');
  await expect(page.getByRole('heading', { name: '专属链接不可用' })).toBeVisible();
  const auth = await headers(request);
  await page.goto(`http://127.0.0.1:5185/#t=${auth.Authorization.slice(7)}`);
  await page.reload();
  await expect(page.getByRole('heading', { name: '专属链接不可用' })).toBeVisible();
  await expect(page.getByText('陈佳怡', { exact: false })).toHaveCount(0);
});
