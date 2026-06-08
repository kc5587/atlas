import { expect, test } from "@playwright/test";

test("working paper renders masthead, both figures, evidence, and the results table", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Honest Signal Detection/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Abstract")).toBeVisible();
  await expect(page.getByText("Evidence Chain")).toBeVisible();
  await expect(page.locator('svg[aria-label="The AI value chain"]')).toBeVisible();
  await expect(page.locator('svg[aria-label="Volcano plot of all slope hypotheses"]')).toBeVisible();
  await expect(page.getByText("Table 1 —", { exact: false })).toBeVisible();
  await expect(page.locator(".vd.s, .vd.c").first()).toBeVisible();
});
