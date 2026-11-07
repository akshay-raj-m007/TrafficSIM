import { expect, test } from '@playwright/test';

test('the validation tab shows every stored result with value, reference, source and command', async ({
  page,
}) => {
  const problems: string[] = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') problems.push(`console.error: ${m.text()}`);
  });
  await page.goto('/');
  await expect(page.locator('.status--open')).toBeVisible();
  await page.getByRole('tab', { name: 'validation' }).click();

  const items = page.getByTestId('validation-item');
  await expect(items).toHaveCount(8);
  for (const id of ['ring_waves', 'lane_capacity', 'stop_line', 'j2_left', 'j2_right', 'webster']) {
    const item = page.locator(`#val-${id}`);
    await expect(item.locator('.val-headline')).toContainText('measured');
    await expect(item.locator('.val-headline')).toContainText('reference');
    await expect(item.locator('.val-ref')).toContainText('Source:');
    await expect(item.locator('.val-cmd code').first()).toContainText('python');
  }
  await expect(page.locator('#val-known_j2_right')).toContainText('64%');
  await expect(page.locator('#val-known_saturation')).toContainText('1,900');
  await expect(page.getByText('stale')).toHaveCount(0);
  expect(problems, 'console / page errors').toEqual([]);
});
