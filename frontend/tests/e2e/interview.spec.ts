import { test, expect, type APIRequestContext } from '@playwright/test';
import { headers, login, ready } from './position-helpers';

const API = 'http://127.0.0.1:8010/api/v1';
async function createInterview(request: APIRequestContext) {
  const { pos } = await ready(request, `排期浏览器-${Date.now()}`);
  let p = await (
    await request.get(`${API}/hr/positions/${pos.id}`, { headers: await headers(request) })
  ).json();
  for (const [action, actor, extra] of [
    ['confirm_profile', 'manager', {}],
    ['publish', 'hr', {}],
    [
      'save_interview_plan',
      'hr',
      {
        rounds: [
          {
            name: '业务面试',
            format: 'phone',
            duration: 30,
            interviewers: ['manager'],
            rule: 'unanimous',
            criteria: '沟通能力\n专业能力',
          },
        ],
      },
    ],
  ] as const) {
    const r = await request.post(`${API}/hr/positions/${p.id}/actions`, {
      headers: await headers(request, actor),
      data: { action, expected_version: p.version, ...extra },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    p = await r.json();
  }
  const response = await request.post(`${API}/hr/candidates`, {
    headers: await headers(request),
    data: { profile: { name: `预约候选人-${Date.now()}` } },
  });
  expect(response.ok()).toBeTruthy();
  let c = (await response.json()).candidate;
  c = await (
    await request.post(`${API}/hr/candidates/${c.id}/actions`, {
      headers: await headers(request),
      data: {
        action: 'consent',
        expected_version: c.version,
        granted: true,
        reason: '本人授权',
        evidence: 'test-signed',
      },
    })
  ).json();
  let app = await (
    await request.post(`${API}/hr/applications`, {
      headers: await headers(request),
      data: { candidate_id: c.id, position_id: p.id },
    })
  ).json();
  for (let n = 0; n < 3; n++) {
    const r = await request.post(`${API}/hr/applications/${app.id}/actions`, {
      headers: await headers(request),
      data: { action: 'advance', expected_version: app.version },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    app = await r.json();
  }
  const list = await (
    await request.get(`${API}/hr/interviews?application_id=${app.id}`, {
      headers: await headers(request),
    })
  ).json();
  const link = await (
    await request.post(`${API}/hr/candidates/${c.id}/conversation`, {
      headers: await headers(request),
      data: { action: 'issue_link', expected_version: 0 },
    })
  ).json();
  return { iv: list.items[0], c, p, app, link: link.url as string };
}

test('HR offers times, candidate books exactly once and reschedules; position shares the schedule', async ({
  page,
  browser,
  request,
}, info) => {
  const data = await createInterview(request);
  await login(page, 'hr', `/interviews/${data.iv.id}`);
  await page.getByLabel('我已核实外部日历忙闲和面试安排').check();
  await page.getByRole('button', { name: '生成候选人可选时段' }).click();
  await expect(page.getByText(/可选：/)).toHaveCount(4);
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 } });
  try {
    await mobile.goto(data.link);
    await expect(mobile.getByRole('heading', { name: '我的面试安排' })).toBeVisible();
    let lost = false;
    const keys: string[] = [];
    await mobile.route(`**/api/v1/candidate/interviews/${data.iv.id}/actions`, async (route) => {
      if (route.request().postDataJSON().action !== 'book') {
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
    await mobile
      .getByRole('button', { name: /^选择 / })
      .first()
      .click();
    await expect(mobile.getByRole('button', { name: '重试本次操作' })).toBeVisible();
    await mobile.getByRole('button', { name: '重试本次操作' }).click();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
    await expect(mobile.getByText('已确定', { exact: true })).toBeVisible();
    await expect(page.getByRole('article', { name: '面试详情' })).toContainText('已确定');
    await page.goto(`/positions/${data.p.id}`);
    await expect(
      page
        .getByRole('region', { name: '本岗位面试记录' })
        .getByRole('link', { name: new RegExp(data.c.profile.name) }),
    ).toBeVisible();
    await mobile.getByLabel('改期说明').fill('希望调整为另一天');
    await mobile.getByRole('button', { name: '申请调整面试时间' }).click();
    await expect(mobile.getByText('等待 HR 提供时段', { exact: true })).toBeVisible();
    await page.goto(`/interviews/${data.iv.id}`);
    await expect(page.getByText(/改期请求：希望调整为另一天/)).toBeVisible();
    await page.getByLabel('面试操作原因').fill('双方协调后重新安排');
    await page.getByRole('button', { name: '取消本场面试' }).click();
    await expect(mobile.getByText('本场已取消', { exact: true })).toBeVisible();
    await mobile.evaluate(() => scrollTo(0, 0));
    await mobile.screenshot({ path: info.outputPath('candidate-interview.png'), fullPage: true });
  } finally {
    await mobile.close();
  }
});

test('business H5 submits verified feedback, retries safely and advances application; availability persists', async ({
  page,
  request,
}, info) => {
  const list = await (
    await request.get(`${API}/hr/interviews?state=awaiting_feedback`, {
      headers: await headers(request),
    })
  ).json();
  const iv = list.items[0];
  expect(iv).toBeTruthy();
  await login(page, 'manager', `http://127.0.0.1:5184/interviews/${iv.id}`);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: '提交本人面评' })).toBeDisabled();
  await page.getByLabel('专业能力评分').selectOption('4');
  await page.getByLabel('沟通能力评分').selectOption('4');
  await page.getByLabel('面评结论').selectOption('yes');
  await page.getByLabel('面评优势').fill('能清楚说明客户问题的处理步骤');
  await page.getByLabel('我已核对并对内容负责').check();
  let lost = false;
  const keys: string[] = [];
  await page.route(`**/api/v1/hr/interviews/${iv.id}/actions`, async (route) => {
    if (route.request().postDataJSON().action !== 'feedback') {
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
  await page.getByRole('button', { name: '提交本人面评' }).click();
  await expect(page.getByRole('button', { name: '重试本次操作' })).toBeVisible();
  await expect(page.getByLabel('面评优势')).toBeDisabled();
  await page.getByRole('button', { name: '重试本次操作' }).click();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  await expect(page.getByRole('article', { name: '面试详情' })).toContainText('已完成');
  const c = await (
    await request.get(`${API}/hr/candidates/${iv.candidate_id}`, {
      headers: await headers(request),
    })
  ).json();
  expect(c.applications.find((a: { id: string }) => a.id === iv.application_id).stage).toBe(
    'manager_eval',
  );
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: info.outputPath('business-feedback.png'), fullPage: true });
  await page.getByRole('link', { name: '返回我的面试' }).click();
  await page.getByLabel('每日场次上限').fill('6');
  await page.getByRole('button', { name: '保存可面设置' }).click();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${API}/biz/interview-availability`, {
              headers: await headers(request, 'manager'),
            })
          ).json()
        ).daily_limit,
    )
    .toBe(6);
});
