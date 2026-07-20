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
