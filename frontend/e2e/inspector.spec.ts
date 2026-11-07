import { expect, test, type Page } from '@playwright/test';

interface Dbg {
  screenPoints: (n: number) => { id: number; x: number; y: number }[];
  selectedOnScreen: () => { x: number; y: number; visible: boolean } | null;
}
const dbg = <T>(page: Page, fn: (d: Dbg) => T) =>
  page.evaluate(`(${fn.toString()})(window.__trafficDebug)`) as Promise<T>;

/** Click vehicles on screen until one is picked (they move a little between measure and click). */
async function pickAVehicle(page: Page) {
  const canvas = page.locator('.viewport__canvas canvas');
  for (let attempt = 0; attempt < 12; attempt++) {
    const pts = await dbg(page, (d) => d.screenPoints(8));
    const box = (await canvas.boundingBox())!;
    for (const p of pts) {
      await page.mouse.click(box.x + p.x, box.y + p.y);
      if (await page.getByTestId('inspector').isVisible()) return;
    }
    await page.waitForTimeout(500);
  }
  throw new Error('no vehicle could be picked');
}

test('the inspector opens on a click, shows the server numbers, follows, and closes cleanly', async ({
  page,
}) => {
  const problems: string[] = [];
  const messages: { gone: boolean; speed_mps?: number; lane?: string; vid?: number }[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console.error: ${m.text()}`);
  });
  page.on('websocket', (ws) =>
    ws.on('framereceived', (f) => {
      if (typeof f.payload === 'string' && f.payload.startsWith('{"type":"vehicle"')) {
        messages.push(JSON.parse(f.payload));
      }
    }),
  );
  await page.goto('/');
  await expect(page.locator('.status--open')).toBeVisible();
  await page.getByRole('button', { name: '5×', exact: true }).dispatchEvent('click');
  await page.getByRole('button', { name: 'J1', exact: true }).click();
  await expect
    .poll(async () => (await dbg(page, (d) => d.screenPoints(3))).length, { timeout: 60_000 })
    .toBeGreaterThan(0);

  // a drag of the camera is not a pick
  const box = (await page.locator('.viewport__canvas canvas').boundingBox())!;
  await page.mouse.move(box.x + 300, box.y + 300);
  await page.mouse.down();
  await page.mouse.move(box.x + 340, box.y + 310, { steps: 4 });
  await page.mouse.up();
  await expect(page.getByTestId('inspector')).toHaveCount(0);

  await pickAVehicle(page);
  await expect(page.getByTestId('inspector-now')).toContainText('trip');
  await expect(page.getByTestId('inspector-now')).toContainText('lane changes');
  expect(await dbg(page, (d) => d.selectedOnScreen())).not.toBeNull(); // highlighted

  // the displayed numbers are the server's: the speed in the panel equals a recent message
  await page.waitForTimeout(1500);
  const shown = await page.getByTestId('inspector-now').innerText();
  const m = /speed\s+(\d+\.\d) m\/s/.exec(shown);
  expect(m).not.toBeNull();
  const recent = messages
    .filter((x) => !x.gone)
    .slice(-12)
    .map((x) => x.speed_mps!.toFixed(1));
  expect(recent).toContain(m![1]);

  // follow keeps the vehicle near the middle of the screen while it moves
  await page.getByTestId('inspector-follow').click();
  await page.waitForTimeout(3000);
  const at = await dbg(page, (d) => d.selectedOnScreen());
  if (at) {
    expect(at.visible).toBe(true);
    expect(Math.abs(at.x)).toBeLessThan(0.35);
    expect(Math.abs(at.y)).toBeLessThan(0.35);
  } else {
    await expect(page.getByTestId('inspector-gone')).toBeVisible(); // it left meanwhile
  }

  await page.keyboard.press('Escape');
  await expect(page.getByTestId('inspector')).toHaveCount(0);
  expect(await dbg(page, (d) => d.selectedOnScreen())).toBeNull();

  // pick again, close with the button, then let a vehicle run until it leaves the network
  await pickAVehicle(page);
  await page.getByTestId('inspector-close').click();
  await expect(page.getByTestId('inspector')).toHaveCount(0);

  await page.getByRole('button', { name: '10×', exact: true }).dispatchEvent('click');
  await pickAVehicle(page);
  await expect(page.getByTestId('inspector-gone')).toBeVisible({ timeout: 150_000 });
  await expect(page.getByTestId('inspector')).toHaveCount(0, { timeout: 10_000 }); // closes itself
  expect(messages.some((x) => x.gone)).toBe(true);
  expect(problems, 'console / page errors').toEqual([]);
});
