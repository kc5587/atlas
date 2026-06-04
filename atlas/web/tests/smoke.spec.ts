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

test("story-mode node clicks open the details panel", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("g.node").first()).toBeVisible({ timeout: 10_000 });

  await page.locator("g.node").first().click();

  await expect(page.locator("aside.panel")).toBeVisible();
});

test("node click targets are forgiving around the circle", async ({ page }) => {
  await page.goto("/");
  const circle = page.locator("g.node circle").first();
  await expect(circle).toBeVisible({ timeout: 10_000 });
  const box = await circle.boundingBox();
  expect(box).not.toBeNull();

  await page.mouse.click(box!.x + box!.width + 10, box!.y + box!.height / 2);

  await expect(page.locator("aside.panel")).toBeVisible();
});

test("a US filer node shows its CIK and SEC fundamentals", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("g.node").first()).toBeVisible({ timeout: 10_000 });
  // Explore mode hides the narrative overlay so off-top nodes are clickable.
  await page.mouse.wheel(0, 20_000);
  await page.waitForTimeout(800);

  await page.locator("g.node", { hasText: "Applied Materials" }).first().click();

  const panel = page.locator("aside.panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByText("SEC fundamentals")).toBeVisible();
  await expect(panel.getByText(/SEC CIK/)).toBeVisible();
  await expect(panel.getByText("Gross margin")).toBeVisible();
});

test("a foreign filer node states it has no CIK in this layer", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("g.node").first()).toBeVisible({ timeout: 10_000 });

  await page.locator("g.node", { hasText: "ASML" }).first().click();

  const panel = page.locator("aside.panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByText("No SEC CIK in this layer")).toBeVisible();
});

test("details panel opens in the current viewport after scrolling", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("g.node").first()).toBeVisible({ timeout: 10_000 });
  await page.mouse.wheel(0, 20_000);
  await page.waitForTimeout(800);

  await page.locator("g.node").first().click();

  const box = await page.locator("aside.panel").boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeLessThan(800);
});
