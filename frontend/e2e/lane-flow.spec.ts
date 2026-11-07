import { expect, test, type Page } from '@playwright/test';

test('the lane-flow toggle colours lanes by measured flow and hides again', async ({ page }) => {
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console.error: ${m.text()}`);
  });
  await page.goto('/');
  await expect(page.locator('.status--open')).toBeVisible();
  const state = (p: Page) =>
    p.evaluate(() =>
      (
        window as unknown as {
          __trafficDebug: {
            laneFlow: () => { visible: boolean; segments: number; carrying: number };
          };
        }
      ).__trafficDebug.laneFlow(),
    );

  expect((await state(page)).visible).toBe(false); // off by default
  await expect(page.getByTestId('lane-flow-legend')).toHaveCount(0);
  await page.getByRole('button', { name: '10×', exact: true }).dispatchEvent('click');
  await page.getByTestId('lane-flow-toggle').click();
  await expect(page.getByTestId('lane-flow-legend')).toBeVisible();
  // a minute of simulated time at 10x: many lanes and connectors carry traffic
  await expect
    .poll(async () => (await state(page)).carrying, { timeout: 90_000 })
    .toBeGreaterThan(20);
  const on = await state(page);
  expect(on.visible).toBe(true);
  expect(on.segments).toBeGreaterThan(50); // every lane and connector, not a sample
  await page.getByTestId('lane-flow-toggle').click();
  expect((await state(page)).visible).toBe(false);
  await expect(page.getByTestId('lane-flow-legend')).toHaveCount(0);
  expect(problems, 'console / page errors').toEqual([]);
});
