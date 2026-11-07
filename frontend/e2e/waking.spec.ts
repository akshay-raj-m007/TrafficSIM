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
