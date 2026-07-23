import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

/**
 * Demo Gate 3 — browse, organize, and listen, walked by a browser.
 *
 * This encodes the journey a human walked at Gate 3 against the same production
 * composition (nginx + api + worker + a disposable Redis) the gate overlay
 * brings up, seeded with the "listening" library: several artists and albums,
 * three known release years, and a first-class Unknown Year. It is one ordered
 * story on one page — browse the library by track, artist, album, and year
 * (Unknown Year included) and confirm each context builds the queue in its own
 * order; create a profile-specific playlist, fill it from the library, remove a
 * track, and play what remains in order; remove upcoming session items, walk
 * the primary routes, prove a refresh and a profile switch both drop the
 * session without leaking it; and — the unglamorous step — submit invalid
 * profile and playlist metadata and watch the input survive, the validation
 * show, and nothing durable change.
 *
 * It is a single test because the steps share one browser session: the active
 * profile and the play queue live in that session, so splitting the journey
 * would drop the household selection and the queue between steps.
 *
 * Locators are scoped deliberately: page-body queries go through the "Content"
 * main landmark so they never collide with the sidebar's own navigation and
 * playlist links, and the sidebar's primary nav is matched exactly so "Library"
 * does not also match a context page's "Your Library" back link.
 *
 * The seeded library is provisioned by global-setup with GATE_SCENARIO set to
 * "listening"; run this spec with:
 *   GATE_NAME=gate-3 GATE_SCENARIO=listening npx playwright test gate-3
 */

const HBFS = "Harder Better Faster Stronger"; // Daft Punk / Discovery / 2001
const KIARA = "Kiara"; // Bonobo / Black Sands / 2010, track 3
const KONG = "Kong"; // Bonobo / Black Sands / 2010, track 5
const SO_WHAT = "So What"; // Miles Davis / Kind of Blue / 1959
const RAINFALL = "Rainfall"; // Field Recordings / Untitled Sessions / Unknown Year

const PLAYLIST_NAME = "Road Trip";

test("Gate 3 — browse, organize, and listen, end to end", async ({ page }) => {
  // The journey touches every primary route and rebuilds the queue several
  // times; it runs longer than a single default timeout comfortably allows.
  test.slow();

  const main = page.getByRole("main");
  const player = page.getByRole("region", { name: "Player" });
  const upNext = page.getByRole("region", { name: "Up next" });
  const openQueue = () => player.getByRole("button", { name: "Queue" }).click();
  // The sidebar's primary nav, matched exactly so "Library" excludes a context
  // page's "Your Library" back link.
  const navTo = (label: string) => page.getByRole("link", { name: label, exact: true }).click();

  await test.step("select a household and open the shared library", async () => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/profiles$/);
    await page.getByRole("button", { name: "Household" }).click();
    await expect(page).toHaveURL(/\/library$/);
    await expect(
      main.getByRole("row", { name: new RegExp(`${HBFS}.*Daft Punk`) }),
    ).toBeVisible();
  });

  await test.step("the year facet lists real years first and Unknown Year last", async () => {
    await main.getByRole("tab", { name: "Years" }).click();
    const yearCards = main.getByRole("tabpanel").getByRole("link");
    // Four groupings are seeded; Unknown Year is a first-class grouping that
    // sorts after every real year rather than being hidden.
    await expect(yearCards.filter({ hasText: "1959" })).toBeVisible();
    await expect(yearCards.filter({ hasText: "2001" })).toBeVisible();
    await expect(yearCards.filter({ hasText: "2010" })).toBeVisible();
    await expect(yearCards.filter({ hasText: "Unknown Year" })).toBeVisible();
    // Unknown Year is the last of the year cards.
    await expect(yearCards.last()).toHaveText(/Unknown Year/);
  });

  await test.step("playing a year builds the queue in that year's order", async () => {
    await main.getByRole("tabpanel").getByRole("link", { name: "2010" }).click();
    await expect(main.getByRole("heading", { name: "2010" })).toBeVisible();
    await main.getByRole("button", { name: "Play year" }).click();
    // The 2010 grouping is Bonobo's two tracks; playing the year starts the
    // first and queues the second.
    await expect(player.getByText(KIARA)).toBeVisible();
    await openQueue();
    await expect(upNext.getByText(KONG)).toBeVisible();
    await page.keyboard.press("Escape");
  });

  await test.step("Unknown Year plays its own, different queue", async () => {
    // Playing the year left us on that year's context page; return to the
    // library to reach the facet tabs again.
    await navTo("Library");
    await main.getByRole("tab", { name: "Years" }).click();
    await main.getByRole("tabpanel").getByRole("link", { name: "Unknown Year" }).click();
    await expect(main.getByRole("heading", { name: "Unknown Year" })).toBeVisible();
    await main.getByRole("button", { name: "Play year" }).click();
    await expect(player.getByText(RAINFALL)).toBeVisible();
    await openQueue();
    // The Unknown Year grouping is a single track: nothing follows it.
    await expect(upNext.getByText("Nothing is queued")).toBeVisible();
    await page.keyboard.press("Escape");
  });

  await test.step("artists and albums are their own browseable facets", async () => {
    await navTo("Library");
    await main.getByRole("tab", { name: "Artists" }).click();
    const artistCards = main.getByRole("tabpanel").getByRole("link");
    await expect(artistCards.filter({ hasText: "Bonobo" })).toBeVisible();
    await expect(artistCards.filter({ hasText: "Miles Davis" })).toBeVisible();
    await main.getByRole("tab", { name: "Albums" }).click();
    const albumCards = main.getByRole("tabpanel").getByRole("link");
    await expect(albumCards.filter({ hasText: "Black Sands" })).toBeVisible();
    await expect(albumCards.filter({ hasText: "Kind of Blue" })).toBeVisible();
  });

  await test.step("a profile-specific playlist starts empty", async () => {
    await navTo("Playlists");
    await expect(page).toHaveURL(/\/playlists$/);
    // The empty playlists screen shows a Create Playlist button in both the
    // header and the empty-state card; the header one is always present.
    await main.getByRole("button", { name: "Create Playlist" }).first().click();

    const dialog = page.getByRole("dialog", { name: "New playlist" });
    await dialog.getByLabel("Name").fill(PLAYLIST_NAME);
    await dialog.getByRole("button", { name: "Create" }).click();
    await expect(dialog).toBeHidden();

    await main.getByRole("link", { name: new RegExp(PLAYLIST_NAME) }).click();
    // The representative empty state: a new playlist with nothing in it.
    await expect(main.getByText("Nothing in this playlist yet")).toBeVisible();
  });

  await test.step("shared tracks are added to the playlist from the library", async () => {
    await addTrackToPlaylist(page, HBFS, PLAYLIST_NAME);
    await addTrackToPlaylist(page, SO_WHAT, PLAYLIST_NAME);

    await navTo("Playlists");
    await main.getByRole("link", { name: new RegExp(PLAYLIST_NAME) }).click();
    await expect(main.getByRole("button", { name: `Play ${HBFS}` })).toBeVisible();
    await expect(main.getByRole("button", { name: `Play ${SO_WHAT}` })).toBeVisible();
  });

  await test.step("a track is removed from the playlist without touching the library", async () => {
    await main.getByRole("button", { name: `Actions for ${SO_WHAT}` }).click();
    await page.getByRole("menuitem", { name: "Remove from this playlist" }).click();
    await expect(main.getByRole("button", { name: `Play ${SO_WHAT}` })).toHaveCount(0);
    await expect(main.getByRole("button", { name: `Play ${HBFS}` })).toBeVisible();

    // The track is gone from the playlist but still in the shared library.
    await navTo("Library");
    await main.getByRole("tab", { name: "Tracks" }).click();
    await expect(main.getByRole("row", { name: new RegExp(SO_WHAT) })).toBeVisible();
  });

  await test.step("the playlist plays in its saved order", async () => {
    await navTo("Playlists");
    await main.getByRole("link", { name: new RegExp(PLAYLIST_NAME) }).click();
    await main.getByRole("button", { name: "Play Playlist" }).click();
    await expect(player.getByText(HBFS)).toBeVisible();
  });

  await test.step("an album fills the session queue to prune", async () => {
    await navTo("Library");
    await main.getByRole("tab", { name: "Albums" }).click();
    await main.getByRole("tabpanel").getByRole("link", { name: "Black Sands" }).click();
    await main.getByRole("button", { name: "Play album" }).click();
    await expect(player.getByText(KIARA)).toBeVisible();

    await openQueue();
    await expect(upNext.getByText(KONG)).toBeVisible();
    // Remove the upcoming track; the queue empties after the current one.
    await page.getByRole("button", { name: `Remove ${KONG} from the queue` }).click();
    await expect(upNext.getByText(KONG)).toHaveCount(0);
    await page.keyboard.press("Escape");
  });

  await test.step("primary routes stay navigable while a track plays", async () => {
    for (const route of ["Playlists", "Downloads", "Settings", "Library"]) {
      await navTo(route);
      await expect(player.getByText(KIARA)).toBeVisible();
    }
  });

  await test.step("a refresh drops the session queue rather than leaking it", async () => {
    await page.reload();
    await openQueue();
    await expect(page.getByText("Nothing queued yet")).toBeVisible();
    await page.keyboard.press("Escape");
  });

  await test.step("switching profile clears the session without leaking it", async () => {
    // Rebuild a queue, then leave the profile.
    await main.getByRole("tab", { name: "Albums" }).click();
    await main.getByRole("tabpanel").getByRole("link", { name: "Black Sands" }).click();
    await main.getByRole("button", { name: "Play album" }).click();
    await expect(player.getByText(KIARA)).toBeVisible();

    await page.getByRole("button", { name: "Choose profile" }).click();
    await expect(page).toHaveURL(/\/profiles$/);
    await page.getByRole("button", { name: "Household" }).click();
    await expect(page).toHaveURL(/\/library$/);

    await openQueue();
    await expect(page.getByText("Nothing queued yet")).toBeVisible();
    await page.keyboard.press("Escape");
  });

  await test.step("invalid profile metadata is refused with the input preserved", async () => {
    await page.getByRole("button", { name: "Choose profile" }).click();
    await expect(page).toHaveURL(/\/profiles$/);
    // "Household" already exists; the server rejects the duplicate by field.
    const nameField = page.getByLabel("New profile name");
    await nameField.fill("Household");
    await page.getByRole("button", { name: "Create profile" }).click();
    await expect(page.getByText(/already exists/i)).toBeVisible();
    // The typed name survives the rejection so it can be corrected in place.
    await expect(nameField).toHaveValue("Household");
    // Re-select the existing household to continue.
    await page.getByRole("button", { name: "Household" }).click();
    await expect(page).toHaveURL(/\/library$/);
  });

  await test.step("invalid playlist metadata cannot be submitted", async () => {
    await navTo("Playlists");
    await main.getByRole("button", { name: "Create Playlist" }).first().click();
    const dialog = page.getByRole("dialog", { name: "New playlist" });
    // A whitespace-only name is invalid: the field is marked invalid and the
    // submit stays disabled, so no playlist can be created.
    await dialog.getByLabel("Name").fill("   ");
    await expect(dialog.getByRole("button", { name: "Create" })).toBeDisabled();
    await expect(dialog.getByLabel("Name")).toHaveAttribute("aria-invalid", "true");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
    // Only the one real playlist exists; the invalid attempt created nothing.
    await expect(main.getByRole("link", { name: new RegExp(PLAYLIST_NAME) })).toHaveCount(1);
  });
});

/**
 * Add a library track to a playlist through its row actions, from the Tracks
 * tab of the library.
 */
async function addTrackToPlaylist(page: Page, title: string, playlist: string): Promise<void> {
  const main = page.getByRole("main");
  await page.getByRole("link", { name: "Library", exact: true }).click();
  await main.getByRole("tab", { name: "Tracks" }).click();
  await main.getByRole("button", { name: `Actions for ${title}` }).click();
  await page.getByRole("menuitem", { name: playlist }).click();
}
