import { expect, test } from '@playwright/test';

test('a server that does not answer shows the waking-up message, not a broken page', async ({
  page,
}) => {
  // The WebSocket is accepted by the browser but the server never answers (a sleeping host).
  await page.routeWebSocket(/\/ws\/sim/, () => {});
  await page.goto('/');
  await expect(page.getByTestId('waking')).toHaveCount(0); // not at once
  await expect(page.getByTestId('waking')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('waking')).toContainText('about a minute');
  await expect(page.locator('.status--connecting, .status--closed')).toBeVisible();
});

test('a busy server shows the friendly message and the page keeps trying', async ({ page }) => {
  await page.routeWebSocket(/\/ws\/sim/, (ws) => {
    ws.send(
      JSON.stringify({
        type: 'busy',
        sessions_max: 2,
        message:
          'The free server allows 2 live simulations at a time and both are in use. Try again in a minute.',
      }),
    );
    ws.close({ code: 1013 });
  });
  await page.goto('/');
  await expect(page.getByTestId('busy')).toContainText('Try again in a minute');
  await expect(page.getByTestId('busy')).toContainText('Retrying automatically');
});

test('an idle-paused session shows a resume button that starts a new session', async ({ page }) => {
  let first = true;
  await page.routeWebSocket(/\/ws\/sim/, (ws) => {
    if (first) {
      first = false;
      ws.send(
        JSON.stringify({
          type: 'idle',
          message: 'Paused after 10 minutes without activity. Click to resume.',
        }),
      );
      ws.close({ code: 4000 });
    } else {
      ws.connectToServer(); // the resumed session is a real one
    }
  });
  await page.goto('/');
  await expect(page.getByTestId('idle')).toContainText('Click to resume');
  await page.getByRole('button', { name: 'Resume' }).click();
  await expect(page.locator('.status--open')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('idle')).toHaveCount(0);
});

test('a layout that must be measured shows the preparing message with progress', async ({
  page,
}) => {
  await page.routeWebSocket(/\/ws\/sim/, (ws) => {
    const msg = (done: number) => ({
      type: 'building',
      reason: 'resetting',
      name: 'custom',
      estimate_s: 150,
      done,
      total: 25,
    });
    ws.send(JSON.stringify(msg(0)));
    setTimeout(() => ws.send(JSON.stringify(msg(7))), 500);
  });
  await page.goto('/');
  await expect(page.getByTestId('building')).toContainText(
    'Preparing this layout for the first time',
  );
  await expect(page.getByTestId('building')).toContainText('about 150 s');
  await expect(page.getByTestId('building')).toContainText('step 7 of 25');
});
