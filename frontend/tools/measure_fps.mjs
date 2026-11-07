/**
 * Render frame rate of the 3D view with the results drawer closed and open.
 *
 *   cd frontend && node tools/measure_fps.mjs [url] [seconds]
 *
 * Counts requestAnimationFrame callbacks over `seconds` (default 20) at 5x simulation speed
 * with the same camera view, alternating closed / MFD / space-time / queues, twice each.
 * Needs Chrome (set CHROME_PATH if it is not in the default place). Headless Chrome renders
 * with a software GL (SwiftShader), so the absolute numbers are far below a GPU's: compare
 * the closed and open numbers of the same run, not with other machines.
 */
import { chromium } from 'playwright-core';

const url = process.argv[2] ?? 'http://localhost:8000/';
const seconds = Number(process.argv[3] ?? 20);
const browser = await chromium.launch({
  executablePath: process.env.CHROME_PATH ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist'],
});
const page = await (await browser.newContext({ viewport: { width: 1600, height: 900 } })).newPage();
await page.goto(url);
await page.waitForSelector('.status--open');
await page.getByRole('button', { name: '5×', exact: true }).dispatchEvent('click');
await page.getByRole('button', { name: 'J1', exact: true }).click();
await page.waitForFunction(() => window.__trafficDebug?.screenPoints(1).length > 0, null, {
  timeout: 120000,
});
await page.waitForTimeout(15000); // let the network fill up

const fps = (s) =>
  page.evaluate(
    (ms) =>
      new Promise((resolve) => {
        let n = 0;
        const t0 = performance.now();
        const tick = (t) => {
          n++;
          if (t - t0 < ms) requestAnimationFrame(tick);
          else resolve({ fps: (n * 1000) / (t - t0), agents: document.querySelector('.agents .clock__value')?.textContent });
        };
        requestAnimationFrame(tick);
      }),
    s * 1000,
  );

const results = [];
const open = async (on) => {
  const isOpen = (await page.getByTestId('charts').count()) > 0;
  if (isOpen !== on) await page.getByTestId('results-toggle').click();
};
for (let round = 0; round < 2; round++) {
  await open(false);
  results.push({ mode: 'closed', ...(await fps(seconds)) });
  for (const tab of ['MFD', 'space-time', 'queues']) {
    await open(true);
    await page.getByRole('tab', { name: tab }).click();
    await page.waitForTimeout(2000);
    results.push({ mode: `open: ${tab}`, ...(await fps(seconds)) });
  }
}
for (const r of results) console.log(`${r.mode.padEnd(18)} ${r.fps.toFixed(1)} fps  (agents ${r.agents})`);
const mean = (f) => {
  const xs = results.filter(f).map((r) => r.fps);
  return xs.reduce((a, b) => a + b, 0) / xs.length;
};
console.log(`mean closed ${mean((r) => r.mode === 'closed').toFixed(1)} fps, open ${mean((r) => r.mode !== 'closed').toFixed(1)} fps`);
await browser.close();
