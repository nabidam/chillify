/**
 * The content viewport of a route whose screen has not been built yet.
 *
 * The walking skeleton needs every shell route to be genuinely navigable so
 * navigation, history, and player continuity can be exercised for real. This
 * states plainly that the screen is not built; it never imitates one.
 */
export function PendingScreen({ title }: { title: string }) {
  return (
    <section aria-labelledby="pending-screen-title" className="flex flex-col gap-3">
      <h1 id="pending-screen-title" className="type-title text-foreground">
        {title}
      </h1>
      <p className="type-body text-foreground-muted">
        This screen is not built yet. The shell around it — navigation, history, and the player
        slot — is live.
      </p>
    </section>
  );
}
