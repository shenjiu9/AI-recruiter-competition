import { expect, type Page, type APIRequestContext } from '@playwright/test';

const API = 'http://127.0.0.1:8010/api/v1';

export async function headers(request: APIRequestContext, actor = 'hr') {
  const r = await request.post(`${API}/auth/dev-login`, {
    data: { user_id: actor, password: 'e2e-only-password' },
  });
  expect(r.ok()).toBeTruthy();
  return {
    Authorization: `Bearer ${(await r.json()).token}`,
    'Idempotency-Key': crypto.randomUUID(),
  };
}
export async function login(page: Page, actor: string, start = '/') {
  await page.goto(start);
  if (await page.getByRole('button', { name: '退出登录' }).isVisible())
    await page.getByRole('button', { name: '退出登录' }).click();
  await page.getByLabel('开发账号').selectOption(actor);
  await page.getByLabel('开发登录口令').fill('e2e-only-password');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible();
}
export async function approve(request: APIRequestContext, title: string) {
  const r = await request.post(`${API}/hr/requisitions`, {
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
      expectedOnboard: new Date(Date.now() + 45 * 86400000).toISOString().slice(0, 10),
      salary: '8-12K/月×13',
      reason: '业务发展',
      duties: '提供客户服务',
      requirements: '良好的沟通能力',
    },
  });
  expect(r.status()).toBe(201);
  let req = await r.json();
  for (const actor of ['manager', 'director', 'hrbp']) {
    const response = await request.post(`${API}/hr/requisitions/${req.id}/approve`, {
      headers: await headers(request, actor),
      data: { expected_version: req.version, node_id: req.chain[req.currentNode].id },
    });
    expect(response.ok()).toBeTruthy();
    req = await response.json();
  }
  return req;
}
export async function projection(request: APIRequestContext, reqId: string) {
  return (
    await request.get(`${API}/hr/requisitions/${reqId}/position`, {
      headers: await headers(request),
    })
  ).json();
}
export async function ready(request: APIRequestContext, title: string) {
  const req = await approve(request, title);
  await expect.poll(async () => (await projection(request, req.id)).status).toBe('generated');
  return { req, pos: (await projection(request, req.id)).position };
}
export async function clickAction(page: Page, name: string) {
  await page.getByRole('button', { name, exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: '确认操作', exact: true }).click();
}
