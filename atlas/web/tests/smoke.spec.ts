import { expect, test } from "@playwright/test";

test("map renders and explore unlocks", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("svg[aria-label='AI value chain map']")).toBeVisible();
  // at least one node circle renders
  await expect(page.locator("g.node").first()).toBeVisible({ timeout: 10_000 });
  // scroll to the final (explore) scene
  await page.mouse.wheel(0, 20_000);
  await page.waitForTimeout(800);
  // clicking a node opens the panel
  await page.locator("g.node").first().click();
  await expect(page.locator("aside.panel")).toBeVisible();
});
