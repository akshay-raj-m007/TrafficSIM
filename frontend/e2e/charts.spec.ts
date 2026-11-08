import { expect, test, type Page } from '@playwright/test';

type Mfd = { t: number; density: number; flow: number; flyoverOpen: boolean };
type Queue = { t: number; j1: number; j2: number };
interface Debug {
  open: boolean;
  mfd: Mfd[];
  queue: Queue[];
  cols: number;
  col0: number;
}
const debug = (page: Page) =>
  page.evaluate(() => (window as unknown as { __chartsDebug: () => unknown }).__chartsDebug());

/** Number of canvas pixels that are not the (near-black) background: a drawn chart has many. */
const inkPixels = (page: Page, testId: string) =>
  page.evaluate((id) => {
    const c = document.querySelector(`[data-testid="${id}"]`) as HTMLCanvasElement;
    const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i]! + d[i + 1]! + d[i + 2]! > 120) n++;
    return n;
  }, testId);

test('the results drawer draws the three charts from the server measurements, without errors', async ({
  page,
}) => {
  test.setTimeout(300_000); // 5 MFD points need 50 simulated seconds
  const problems: string[] = [];
  const received = { mfd: [] as unknown[][], queue: [] as unknown[][] };
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console.error: ${m.text()}`);
  });
  page.on('websocket', (ws) =>
    ws.on('framereceived', (f) => {
      if (typeof f.payload !== 'string' || !f.payload.startsWith('{"type":"charts"')) return;
      const m = JSON.parse(f.payload);
      received.mfd.push(...m.mfd);
      received.queue.push(...m.queue);
    }),
  );
  await page.goto('/');
  await expect(page.locator('.status--open')).toBeVisible();
  await page.getByRole('button', { name: '10×', exact: true }).dispatchEvent('click');
  await expect(page.getByTestId('charts')).toHaveCount(0); // closed by default: nothing streams
  await page.getByTestId('results-toggle').click();
  await expect(page.getByTestId('charts')).toBeVisible();

  // MFD: points arrive every 10 simulated seconds
  await expect
    .poll(async () => ((await debug(page)) as Debug).mfd.length, { timeout: 90_000 })
    .toBeGreaterThan(4);
  await expect.poll(() => inkPixels(page, 'chart-mfd')).toBeGreaterThan(200);

  await page.getByRole('tab', { name: 'space-time' }).click();
  await expect
    .poll(() => inkPixels(page, 'chart-spacetime'), { timeout: 30_000 })
    .toBeGreaterThan(2000);
  const drawer = page.getByTestId('charts');
  await drawer.getByRole('button', { name: 'flyover', exact: true }).click();
  await drawer.getByRole('button', { name: 'westbound', exact: true }).click();
  await expect.poll(() => inkPixels(page, 'chart-spacetime')).toBeGreaterThan(2000);

  await page.getByRole('tab', { name: 'queues' }).click();
  await expect.poll(() => inkPixels(page, 'chart-queue')).toBeGreaterThan(200);

  // the chart data is the server's data: every point the browser holds was sent by the server
  await page.waitForTimeout(2500);
  const d = (await debug(page)) as Debug;
  const sentMfd = received.mfd;
  const held = d.mfd.map((p) => [p.t, p.density, p.flow, p.flyoverOpen]);
  expect(held.length).toBeGreaterThan(4);
  expect(held).toEqual(sentMfd.slice(sentMfd.length - held.length));
  const heldQ = d.queue.map((p) => [p.t, p.j1, p.j2]);
  expect(heldQ).toEqual(received.queue.slice(received.queue.length - heldQ.length));
  expect(d.cols).toBeGreaterThan(30);

  await page.getByTestId('results-toggle').click();
  await expect(page.getByTestId('charts')).toHaveCount(0);
  expect(problems, 'console / page errors').toEqual([]);
});
