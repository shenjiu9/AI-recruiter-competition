import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
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

async function consentedCandidate(request: APIRequestContext, name: string) {
  const response = await request.post(`${API}/candidates`, {
    headers: await headers(request),
    data: { profile: { name, skills: '客户沟通、Excel 数据分析', city: '深圳' } },
  });
  expect(response.ok()).toBeTruthy();
  const c = (await response.json()).candidate;
  const granted = await request.post(`${API}/candidates/${c.id}/actions`, {
    headers: await headers(request),
    data: {
      action: 'consent',
      expected_version: c.version,
      granted: true,
      evidence: '本人签名',
      reason: '测试招聘评估',
    },
  });
  expect(granted.ok()).toBeTruthy();
  return c;
}

/** 在对话框里说一句话，返回这一轮助手的回复区域 */
async function say(page: Page, text: string, scope = page.locator('body')) {
  const asked = await scope.locator('.as-msg-user').count();
  const box = scope.getByLabel('和 AI 招聘助手对话');
  await box.fill(text);
  await box.press('Enter');
  const question = scope.locator('.as-msg-user').nth(asked);
  await expect(question).toHaveText(text);
  // The assistant answer is the first message right after this question.
  const reply = question.locator('xpath=following-sibling::div[contains(@class,"as-msg-ai")][1]');
  await expect(reply.locator('.as-typing')).toHaveCount(0);
  await expect(reply).toBeVisible();
  return reply;
}

test('HR completes a hiring loop by chatting with the assistant, confirming every change', async ({
  page,
  request,
}, info) => {
  const admin = await headers(request, 'admin');
  const before = await (await request.get(`${API}/automation-live`, { headers: admin })).json();
  const configured = await request.post(`${API}/automation-live`, {
    headers: { ...admin, 'Idempotency-Key': crypto.randomUUID() },
    data: {
      expected_version: before.version,
      mode: 'manual',
      components: Object.fromEntries([1, 2, 3, 4, 5, 6, 7].map((i) => [`A${i}`, true])),
    },
  });
  expect(configured.ok()).toBeTruthy();
  try {
    const suffix = String(Date.now()).slice(-6);
    const pos = await openPosition(request, `助手闭环岗位${suffix}`);
    const name = `周闭环${suffix}`;
    const candidate = await consentedCandidate(request, name);
    await page.setViewportSize({ width: 1440, height: 900 });

    // The assistant is the HR home page.
    await login(page, 'hr', '/');
    await expect(page).toHaveURL(/\/assistant$/);
    await expect(page.getByRole('heading', { name: /今天想先处理什么/ })).toBeVisible();
    await page.screenshot({ path: info.outputPath('assistant-home.png') });

    // 1. Attach: proposed as a card, executed only after confirmation.
    let reply = await say(page, `把${name}加到${pos.name}岗位`);
    await expect(reply.getByRole('group', { name: /关联岗位/ })).toBeVisible();
    await reply.getByRole('button', { name: '确认执行' }).click();
    await expect(page.getByText(`已把${name}关联到“${pos.name}”`).first()).toBeVisible();

    // 2. "他" refers to the candidate of the previous turn.
    for (const stage of ['沟通中', 'AI 评估']) {
      reply = await say(page, '推进他');
      await expect(reply.getByRole('group', { name: new RegExp(`推进 ${name}`) })).toContainText(
        stage,
      );
      await reply.getByRole('button', { name: '确认执行' }).click();
      await expect(page.getByText(new RegExp(`已推进${name}.*${stage}`)).first()).toBeVisible();
    }

    // 3. AI evaluation runs as a reviewed job inside the chat.
    reply = await say(page, '评估一下他');
    const job = reply.getByLabel('AI 任务 候选人证据评估');
    await expect(job.getByText('待你复核')).toBeVisible({ timeout: 30_000 });
    await expect(job.getByText('建议推进')).toBeVisible();
    await page.screenshot({ path: info.outputPath('assistant-evaluation.png') });
    await job.getByRole('checkbox', { name: '我已核对原文、证据和当前状态' }).check();
    await job.getByRole('button', { name: '确认并执行' }).click();
    await expect(job.getByText('已处理')).toBeVisible();

    // 4. Status answers come straight from the records.
    reply = await say(page, `${name}到哪一步了`);
    await expect(reply.locator('.as-text')).toContainText('面试');
    reply = await say(page, `${pos.name}还差几个人`);
    await expect(reply.getByLabel('候选人阶段分布')).toBeVisible();
    await expect(reply.locator('.as-text')).toContainText('还差 1 人');

    // 5. Messages are sent through the existing conversation commands after confirmation.
    reply = await say(page, `给${name}发消息：明天上午10点电话沟通`);
    await expect(reply.locator('.as-quote')).toHaveText('明天上午10点电话沟通');
    await reply.getByRole('button', { name: '确认发送' }).click();
    await expect(page.getByText(/消息已(发送|排队)/).first()).toBeVisible();
    const conversation = await (
      await request.get(`${API}/candidates/${candidate.id}/conversation`, {
        headers: await headers(request),
      })
    ).json();
    expect(conversation.messages.at(-1).content).toBe('明天上午10点电话沟通');

    // 6. Overview with decision cards and pending work.
    reply = await say(page, '今天有什么要处理');
    await expect(reply.getByText('在招岗位', { exact: true })).toBeVisible();
    const approvalQuery = page.waitForRequest(
      (request) => request.url().endsWith('/hr/assistant') && request.method() === 'POST',
    );
    await page.getByRole('button', { name: /待我审批/ }).click();
    expect((await approvalQuery).postDataJSON().text).toBe('今天有什么要处理');
    await expect(page.locator('.as-typing')).toHaveCount(0);
    await page.screenshot({ path: info.outputPath('assistant-loop.png'), fullPage: false });

    // Merged A2 keeps resume matching and evidence visible inside the new chat.
    reply = await say(page, `为${pos.name}做简历匹配`);
    const matching = reply.getByLabel('AI 任务 简历匹配与人才搜索');
    await expect(matching.getByText('待你复核')).toBeVisible({ timeout: 30_000 });
    const results = matching.getByRole('region', { name: '简历匹配结果' });
    await expect(results.getByRole('link', { name, exact: true })).toBeVisible();
    await expect(results).toContainText('证据覆盖率');
    await page.screenshot({ path: info.outputPath('assistant-matching.png') });

    // 7. On any other page the assistant opens beside the page and keeps the conversation.
    await page.goto(`/positions/${pos.id}`);
    await page.getByRole('button', { name: 'AI 助手' }).click();
    const dock = page.locator('.as-dock');
    await expect(dock.getByText('明天上午10点电话沟通').first()).toBeVisible();
    reply = await say(page, '分析这个岗位的招聘瓶颈', dock);
    await expect(reply.getByLabel('AI 任务 岗位数据洞察')).toBeVisible();
    await expect(reply.getByText('进度正常，主要停留在沟通阶段。')).toBeVisible({
      timeout: 30_000,
    });
    await page.screenshot({ path: info.outputPath('assistant-dock.png') });

    // Mobile layout keeps the chat usable.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/assistant');
    await expect(page.getByLabel('和 AI 招聘助手对话')).toBeVisible();
    await page.screenshot({ path: info.outputPath('assistant-mobile.png') });
    await page.reload();
    await expect(page.locator('.as-msg-user').first()).toContainText(name);
    // Another account must never see the previous HR's cached conversation.
    await login(page, 'manager', '/assistant');
    await expect(page.locator('.as-msg-user')).toHaveCount(0);
  } finally {
    const latest = await (await request.get(`${API}/automation-live`, { headers: admin })).json();
    await request.post(`${API}/automation-live`, {
      headers: { ...admin, 'Idempotency-Key': crypto.randomUUID() },
      data: { expected_version: latest.version, mode: before.mode, components: before.components },
    });
  }
});
