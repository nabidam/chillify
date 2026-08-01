import { expect, test } from "@playwright/test";
import { chooseHousehold } from "./fixtures";

const responsiveViewports = [
  { width: 375, height: 812 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1440, height: 900 },
] as const;

/**
 * U1 kernel journey: the dedicated source stays separate, yet its native MP3
 * travels through the shipped queue and becomes ordinary local playback.
 */
test("Radio Javan walking skeleton — discover, download, and play locally", async ({
  page,
}) => {
  const main = page.getByRole("main");

  await test.step("open the dedicated Radio Javan destination and search its fixture", async () => {
    await chooseHousehold(page);
    await page.getByRole("link", { name: "Radio Javan", exact: true }).click();
    await expect(page).toHaveURL(/\/radio-javan$/);
    await main.getByLabel("Search Radio Javan").fill("walking");
    await main.getByRole("button", { name: "Search", exact: true }).click();
    await expect(page).toHaveURL(/\/radio-javan\/search\?q=walking$/);
    const downloadButton = main.getByRole("button", {
      name: "Download Radio Javan Walking Skeleton",
    });
    await expect(downloadButton).toBeVisible();
    const resultCard = downloadButton.locator("xpath=ancestor::*[@data-slot='card']").first();
    await expect(resultCard).toContainText("Radio Javan Walking Skeleton");
    await expect(resultCard.getByRole("status")).toHaveText("MP3 · not playable remotely");
  });

  await test.step("queue the direct MP3 and wait for durable publication", async () => {
    await main.getByRole("button", { name: "Download Radio Javan Walking Skeleton" }).click();
    await page.getByRole("link", { name: "Downloads", exact: true }).click();
    await expect(main.getByText(/completed/i).first()).toBeVisible({ timeout: 90_000 });
  });

  await test.step("play the completed local track through the persistent player", async () => {
    await page.getByRole("link", { name: "Library", exact: true }).click();
    const trackRow = main.getByRole("row", {
      name: /Radio Javan Walking Skeleton.*Radio Javan Ensemble/,
    });
    await expect(trackRow).toBeVisible();
    await trackRow.getByRole("button", { name: "Play Radio Javan Walking Skeleton" }).click();
    await expect(page.getByRole("region", { name: "Player" })).toContainText(
      "Radio Javan Walking Skeleton",
    );
  });
});

test("Radio Javan Explore stays readable without horizontal overflow", async ({ page }) => {
  await chooseHousehold(page);

  for (const viewport of responsiveViewports) {
    await page.setViewportSize(viewport);
    await page.goto("/radio-javan");
    await expect(page.getByRole("heading", { name: "Radio Javan" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Download Featured Fixture" })).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      ),
    ).toBe(true);
  }
});
