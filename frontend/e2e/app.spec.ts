import { expect, test, type Page } from '@playwright/test';

/** Every test fails on any console error or uncaught page error (the J2 preset crash was one). */
test.beforeEach(async ({ page }) => {
  const problems: string[] = [];
  (page as Page & { problems: string[] }).problems = problems;
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console.error: ${m.text()}`);
  });
  page.on('dialog', (d) => void d.accept()); // the flyover confirmation
  await page.goto('/');
  await expect(page.locator('.status--open')).toBeVisible();
});

test.afterEach(async ({ page }) => {
  expect((page as Page & { problems: string[] }).problems, 'console / page errors').toEqual([]);
});

const agents = (page: Page) => page.locator('.agents .clock__value');
const speed = (page: Page, label: string) =>
  page.getByRole('button', { name: label, exact: true }).dispatchEvent('click');
const jSelect = (page: Page) => page.getByLabel('J2 minor approach');
const group = (page: Page, name: string, what: 'lanes' | 'lane width') =>
  page.getByLabel(`${name} ${what}`);
const TITLES: Record<string, string> = {
  default: 'Scenario · Default',
  rush_hour: 'Scenario · Rush hour',
  flyover_closed: 'Scenario · Flyover closed',
  j2_before: 'Scenario · J2 before: one shared lane',
};
const SURFACE = 'Surface road (through J1)';
const FLYOVER = 'Flyover / through road';

/** A structure reset was applied: the new network's hello arrived, so nothing is pending. A new
 *  structure first measures its saturation flows (seconds), shown as the building banner. */
async function applied(page: Page) {
  await expect(page.getByText('pending until reset')).toHaveCount(0, { timeout: 120_000 });
  await waitReady(page);
}

async function waitReady(page: Page) {
  await expect(page.getByTestId('building')).toBeHidden({ timeout: 120_000 });
  await expect(page.locator('.status--open')).toBeVisible();
}

test('loads, streams vehicles and shows measured KPIs', async ({ page }) => {
  await speed(page, '10×');
  await expect
    .poll(async () => Number(await agents(page).innerText()), { timeout: 60_000 })
    .toBeGreaterThan(5);
  await expect(page.getByText('Measured KPIs')).toBeVisible();
  await expect(page.locator('canvas')).toBeVisible();
});

test('every preset loads, including the one-lane J2 layout, and the panel follows the network', async ({
  page,
}) => {
  const presets = page.getByLabel('Preset');
  const names = await presets
    .locator('option')
    .evaluateAll((o) => o.map((x) => (x as HTMLOptionElement).value));
  expect(names).toEqual(
    expect.arrayContaining(['default', 'rush_hour', 'flyover_closed', 'j2_before']),
  );
  for (const name of names) {
    await presets.selectOption(name);
    await page.getByRole('button', { name: /Load preset/ }).click();
    // the hello of this preset was applied once the panel title shows its scenario name
    await expect(page.getByRole('heading', { level: 2, name: TITLES[name] ?? name })).toBeVisible({
      timeout: 120_000,
    });
    await waitReady(page);
    const expectedJ2 = name === 'j2_before' ? '1' : '2';
    await expect(jSelect(page)).toHaveValue(expectedJ2); // the hello was applied
    await expect(page.getByText('pending until reset')).toHaveCount(0);
    await speed(page, '5×');
    await expect
      .poll(async () => Number(await agents(page).innerText()), { timeout: 60_000 })
      .toBeGreaterThan(0);
  }
});

test('the flyover can be closed and reopened live and the change log records both', async ({
  page,
}) => {
  await speed(page, '5×');
  await page.getByRole('button', { name: /close it/ }).click();
  await expect(page.locator('.ed-log')).toContainText('flyover closed');
  await page.getByRole('button', { name: /reopen it/ }).click();
  await expect(page.locator('.ed-log')).toContainText('flyover opened');
});

test('live demand, mix and policy changes validate, apply and export', async ({ page }) => {
  const mix = page.locator('section', { hasText: 'Vehicle mix' });
  await mix.locator('input').first().fill('52');
  await expect(mix.getByRole('status')).toContainText('shares sum to 97, must be exactly 100');
  await expect(page.getByRole('button', { name: 'Apply mix' })).toBeDisabled();
  await mix.locator('input').first().fill('45');
  await mix.locator('input').nth(1).fill('20');
  await page.getByRole('button', { name: 'Apply mix' }).click();
  await page.getByLabel('Max-pressure', { exact: true }).click();
  await page.getByRole('button', { name: 'Scale' }).click(); // draft only, apply stays a choice
  await expect(page.locator('.ed-log')).toContainText('mix: 45/20/30/5');
  await expect(page.locator('.ed-log')).toContainText('signal policy: max_pressure');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export JSON' }).click();
  expect((await download).suggestedFilename()).toMatch(/^scenario-.*\.json$/);
});

test('lane counts and widths: extremes apply on reset, invalid values are errors', async ({
  page,
}) => {
  // an invalid width is an error next to its field and blocks the reset (nothing is clamped)
  await group(page, SURFACE, 'lane width').fill('2.4');
  await expect(page.getByText('surface_width_m 2.4 m is outside 2.5..4.0 m')).toBeVisible();
  await expect(page.getByRole('button', { name: /Reset with these settings/ })).toBeDisabled();
  await expect(page.getByRole('button', { name: /↺ reset/ })).toBeDisabled();

  // 1 lane per group at the narrowest width
  await group(page, SURFACE, 'lanes').selectOption('1');
  await group(page, FLYOVER, 'lanes').selectOption('1');
  await group(page, SURFACE, 'lane width').fill('2.5');
  await group(page, FLYOVER, 'lane width').fill('2.5');
  await expect(page.getByText('pending until reset')).toBeVisible();
  await page.getByRole('button', { name: /Reset with these settings/ }).click();
  await applied(page);
  await speed(page, '5×');
  await expect
    .poll(async () => Number(await agents(page).innerText()), { timeout: 60_000 })
    .toBeGreaterThan(0);

  // 4 lanes per group at the widest width, reset from the header button (the same reset)
  await group(page, SURFACE, 'lanes').selectOption('4');
  await group(page, FLYOVER, 'lanes').selectOption('4');
  await group(page, SURFACE, 'lane width').fill('4.0');
  await group(page, FLYOVER, 'lane width').fill('4.0');
  await page.getByRole('button', { name: /↺ reset/ }).click();
  await applied(page);
  await expect(page.getByText(/Roads \/ lanes/)).toBeVisible();
  await speed(page, '5×');
  await expect
    .poll(async () => Number(await agents(page).innerText()), { timeout: 60_000 })
    .toBeGreaterThan(0);
});

test('the compare view shows a stored experiment and runs a small live comparison', async ({
  page,
}) => {
  await page.getByRole('tab', { name: 'compare' }).click();
  await page.getByRole('button', { name: /Flyover open vs closed/ }).click();
  await expect(page.locator('.cmp-table')).toBeVisible();
  await expect(page.locator('.cmp-row')).toHaveCount(12);
  await expect(page.getByTestId('distribution-chart').first()).toBeVisible();

  await page.getByText('Duration, s').locator('..').locator('input').fill('150');
  await page.getByText('Warm-up excluded, s').locator('..').locator('input').fill('30');
  await page.getByText('Runs (paired seeds)').locator('..').locator('select').selectOption('3');
  await page.getByLabel('A scenario').selectOption('preset:default');
  await page.getByLabel('B scenario').selectOption('preset:flyover_closed');
  await page.getByRole('button', { name: 'Run comparison' }).click();
  await expect(page.locator('progress')).toBeVisible();
  await expect(page.locator('.cmp-meta')).toContainText('3 paired runs', { timeout: 150_000 });
  await expect(page.locator('.cmp-row').first()).toBeVisible();
  // the pooled travel-time distributions are drawn (coloured pixels on the canvas)
  const ink = await page.getByTestId('distribution-chart').first().evaluate((el) => {
    const c = el as HTMLCanvasElement;
    const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
    let n = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i]! + d[i + 1]! + d[i + 2]! > 200) n++;
    return n;
  });
  expect(ink).toBeGreaterThan(500);
});
