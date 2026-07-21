/** Display formatting shared across screens. */

/**
 * Render a duration as `m:ss`, or `h:mm:ss` past an hour.
 *
 * A negative, absent, or non-finite value renders as `--:--` rather than as
 * `0:00`: the player must never claim a position it does not have.
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "--:--";
  }
  const whole = Math.floor(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  const paddedSeconds = String(remainder).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${paddedSeconds}`
    : `${minutes}:${paddedSeconds}`;
}

/** Milliseconds as a track length, for durations the server reports. */
export function formatMilliseconds(milliseconds: number | null | undefined): string {
  return milliseconds === null || milliseconds === undefined
    ? "--:--"
    : formatDuration(milliseconds / 1000);
}

/**
 * Render a stored timestamp as a coarse "how long ago".
 *
 * Deliberately coarse: a household listing playlists wants "3 days ago", and a
 * precise timestamp would only invite the reader to compare clocks.
 */
export function formatRelativeTime(timestamp: string): string {
  const moment = Date.parse(timestamp);
  if (Number.isNaN(moment)) {
    return "recently";
  }
  const minutes = Math.floor((Date.now() - moment) / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
