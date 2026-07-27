# Chillify UX

This living document defines the interactive desktop experience for milestone 001. It adapts Spotify Web Player patterns of navigation, disclosure, and information density to Chillify’s downloader-first local library; it does not copy Spotify layouts or assets.

## Persistent application shell

Screens S2–S12 share four stable regions:

1. **Sidebar:** active profile switcher; Library, Search, Playlists, Downloads, and Settings; personal playlist shortcuts; Add Music action.
2. **Top bar:** back/forward navigation, current view title or contextual search, provider/degraded-state summary.
3. **Content viewport:** the active screen; only this region changes during navigation.
4. **Bottom player:** cover, title/artist, play/pause, previous/next, elapsed/remaining time, seek, volume, and Queue action. It stays mounted so navigation never interrupts audio.

A compact global job indicator stays visible whenever work is queued or running. Activating it opens S11. Persistent degraded-state notices explain unavailable acquisition without blocking local playback.

## Screen inventory

| ID | Screen/view/modal | Purpose | Entry points |
|---|---|---|---|
| S1 | Profile chooser | Create or select a name-only household profile | First visit; profile switcher |
| S2 | Your Library | Landing view for locally playable tracks and browse contexts | Profile selection; Library sidebar item |
| S3 | Search | Search local tracks, deliberately query Deezer, and start result downloads | Search sidebar item; top-bar search |
| S4 | Add Track by Link | Detect and accept one Spotify track or YouTube video URL | Add Music in shell or empty states |
| S5 | YouTube Metadata Review | Correct extracted metadata before queueing a YouTube download | Valid YouTube URL from S4 |
| S6 | Artist view | Inspect and play all local tracks for one artist | Artist link in S2, S3, S7, S10, or player |
| S7 | Album view | Inspect and play one local album in disc/track order | Album link in S2, S3, S6, S10, or player |
| S8 | Year view | Inspect and play tracks for a release year | Year grouping in S2 or metadata link |
| S9 | Playlists | List and create the active profile’s playlists | Playlists sidebar item |
| S10 | Playlist detail | Play, reorder, add to, and remove from a personal playlist | S9; playlist shortcut |
| S11 | Downloads | Inspect the durable serial queue and cancel/retry jobs | Downloads item; global job indicator |
| S12 | Settings | Configure proxy/providers and inspect storage/tool health | Settings sidebar item |
| S13 | Track details/editor | Inspect source data; edit synchronized metadata and artwork; delete a track | Track overflow action; player context |
| S14 | Queue drawer | Inspect and edit the browser-session playback queue | Bottom-player Queue action |
| S15 | Delete-track confirmation | Confirm permanent shared-media deletion and disclose impact | Delete action in S13 |
| S16 | Playlist editor dialog | Create or rename a personal playlist | S9 create action; S10 overflow action |

## Navigation map

```text
S1 Profile chooser
 └─ select/create profile
    └─ S2 Your Library
       ├─ Tracks ────────────────┬─ S6 Artist
       │                         ├─ S7 Album
       │                         ├─ S8 Year
       │                         └─ S13 Track editor ── S15 Delete confirmation
       ├─ S3 Search ─────────────┬─ local track → play / S13
       │                         └─ Deezer result → S11 Downloads
       ├─ S4 Add by Link ────────┬─ Spotify → S11 Downloads
       │                         └─ YouTube → S5 Review → S11 Downloads
       ├─ S9 Playlists ──────────┬─ S16 Create
       │                         └─ S10 Playlist detail ── S16 Rename
       ├─ S11 Downloads
       └─ S12 Settings

Persistent from S2–S12:
 bottom player ↔ S14 Queue drawer
 profile switcher → S1
 Add Music → S4
 job indicator → S11
```

Browser back/forward restores the previous content view without remounting the player. Switching profile stops playback, clears the session queue, and returns through S1 before loading the selected profile’s personal playlists.

## Screen wireframes

### S1 — Profile chooser

**Regions:** product name and one-line household explanation; existing profile buttons; inline “new profile name” field and Create action.  
**Primary action:** choose an existing profile.  
**Eye first:** profile choices; on first use, the creation field.

- **Empty:** explain that profiles separate playlists but share all tracks and settings; focus the name field.
- **Loading:** reserve profile positions and prevent duplicate selection.
- **Error:** keep the entered name, identify whether it is invalid, duplicated, or could not be saved, and offer retry.
- **Density/hierarchy:** profile selection and creation are immediate. The no-auth/equal-access implication is stated once; no avatar, PIN, rename, or delete controls appear.

### S2 — Your Library

**Regions:** heading with track count and Add Music; browse switcher for Tracks, Artists, Albums, and Years; sort control relevant to the active browse mode; dense track rows or context cards; bottom player.  
**Primary action:** play a local track or context.  
**Eye first:** recently added/local track content, then browse modes.

- **Empty:** explain that Chillify only shows managed downloads; offer Add Music and Search.
- **Loading:** preserve heading and controls; use fixed row placeholders without blocking the player.
- **Error:** show library-read failure with Retry; player remains available for any already-loaded track.
- **Unavailable file:** retain the row, disable Play, label the file missing, and offer S13.
- **Density/hierarchy:** playback, artist, album, year, and Add to Playlist are one click away. Metadata editing and deletion stay in the row overflow/S13.

### S3 — Search

**Regions:** track query field; local-results heading and rows; explicit Search Deezer action; remote status line; separate Deezer-results region with source, metadata, availability, and Download action.  
**Primary action:** play a local match; if none is suitable, explicitly search Deezer.  
**Eye first:** query and local results.

- **Empty query:** explain local-first behavior and place online search behind the button.
- **No local matches:** preserve the query and make Search Deezer the next clear action.
- **Online loading:** keep local results usable; show that Deezer is being contacted and prevent duplicate submits.
- **Online result:** never shows Play; Download is the only primary action. An existing duplicate links to the local track instead.
- **Online error:** identify provider disabled, proxy failure, timeout, or unavailable queue; local results remain usable. Redis degradation may allow discovery but disables Download.
- **Density/hierarchy:** local and internet content never intermix. Detailed provider diagnostics remain in S12; job details move to S11 after queueing.

### S4 — Add Track by Link

**Regions:** URL field; supported-input note (“one Spotify track or one YouTube video”); detected-source preview; Cancel and Continue/Download actions.  
**Primary action:** paste a supported link and continue.  
**Eye first:** URL field.

- **Empty:** show two concise supported examples without suggesting albums or playlists.
- **Loading:** show link inspection and disable repeated submission. Inspection
  reports its **named phase** and **elapsed seconds**, and offers **Cancel**
  throughout. Phase names state real work ("Reading Spotify details", "Matching
  with SpotDL"); no percentage is shown, because inspection has no honest one.
- **Fallback:** when the fast Spotify lookup fails and SpotDL takes over, the
  phase changes visibly and names the switch. The fallback is never silent, and
  the elapsed timer keeps running across the handover rather than resetting.
- **Cancel:** stops inspection at any phase and leaves no provider subprocess
  running. The dialog returns to the editable URL field with the input preserved.
- **Spotify success:** identify the track source and allow queueing; job progress continues in S11.
- **YouTube success:** continue to S5 rather than queueing immediately.
- **Error:** preserve input; distinguish malformed URL, unsupported host/entity, bulk link, duplicate local track, provider disabled, proxy failure, extractor failure, inspection timeout, and cancellation. A timeout names which inspection path timed out and links to S12.
- **Density/hierarchy:** only URL acquisition is here. Provider configuration is linked but not embedded. The inspection mode lives in S12, not here — the dialog reports which path ran, but does not offer to change it.

### S5 — YouTube Metadata Review

**Regions:** extracted cover preview and replacement actions; editable title, artist, album, year, disc number, track number; original URL/source summary; Cancel and Queue Download.  
**Primary action:** validate and queue the corrected track.  
**Eye first:** title and artist, followed by cover.

- **Loading:** keep the modal open while metadata/artwork inspection completes.
- **Partial metadata:** the fast Spotify path returns no album, disc, or track
  number. Those fields arrive empty and are marked as not-yet-known rather than
  silently blank, so the person can tell "nothing found" from "nothing there".
  An untouched not-yet-known field stays eligible for Last.fm gap enrichment;
  a field the person edits — including deliberately clearing it — is their
  answer and is never overwritten.
- **Validation:** mark exact invalid fields; preserve all edits. Title and artist cannot be blank.
- **Artwork error:** metadata can still be submitted without artwork after a clear warning.
- **Duplicate:** block queueing and link to the existing S13 record.
- **Density/hierarchy:** common music tags are visible. Source diagnostics and advanced tags are omitted.

### S6 — Artist view

**Regions:** artist identity and local track count; Play Artist action; albums ordered by release year, each with disc/track-ordered rows.  
**Primary action:** replace the session queue with the artist context and play its first track.  
**Eye first:** artist identity and Play Artist.

- **Empty:** if reached from stale metadata, explain that the artist has no playable tracks and return to S2.
- **Loading:** preserve artist header and player.
- **Error:** Retry reloads this view only.
- **Density/hierarchy:** album and track playback are immediate; editing belongs to S13.

### S7 — Album view

**Regions:** cover and album metadata; Play Album; disc/track-ordered rows with duration and per-track actions.  
**Primary action:** replace the session queue with the album and play from disc one/track one.  
**Eye first:** album identity and Play Album.

- **Empty:** explain that no playable local tracks remain.
- **Loading:** preserve album header proportions and player.
- **Error:** Retry reloads this album; unavailable rows remain identifiable.
- **Density/hierarchy:** track playback and artist navigation are immediate; metadata correction is disclosed per track.

### S8 — Year view

**Regions:** year heading and count; Play Year; rows grouped by artist then album, ordered by disc/track.  
**Primary action:** replace the session queue with the year context.  
**Eye first:** year and Play Year.

- **Unknown Year:** behaves as a first-class grouping and explains that metadata can be corrected per track.
- **Empty/loading/error:** follow S7 behavior without losing the player.
- **Density/hierarchy:** grouping explains queue order. Track editing stays in S13.

### S9 — Playlists

**Regions:** heading and Create Playlist; list of current profile’s playlists with track count and last-modified time.  
**Primary action:** open a playlist; when empty, create one.  
**Eye first:** playlist list or empty-state action.

- **Empty:** state that playlists belong to the active profile; offer Create Playlist.
- **Loading:** preserve heading and create action.
- **Error:** Retry without affecting playback or shared library access.
- **Density/hierarchy:** creation and opening are immediate. Rename is available inside S10; profiles and shared tracks are not managed here.

### S10 — Playlist detail

**Regions:** playlist name, count, Play Playlist, and Rename; manually ordered track rows with drag/reorder handle, remove action, and per-track navigation.  
**Primary action:** play the playlist in its saved order.  
**Eye first:** playlist identity and Play Playlist.

- **Empty:** offer a route to S2/S3 and explain how to add tracks from row actions.
- **Loading:** preserve header; disable reorder until all entries load.
- **Error:** restore the last confirmed order and offer Retry.
- **Missing/deleted track:** remove globally deleted tracks automatically; transiently missing files remain disabled and labeled.
- **Density/hierarchy:** play, reorder, and remove are direct. Rename uses S16; metadata changes stay in S13.

### S11 — Downloads

**Regions:** service state and current-job summary; serial queue ordered by execution; completed/failed history; each row shows source, track, phase, available progress, timestamps, and actions.  
**Primary action:** understand or act on the current job.  
**Eye first:** active job phase and meaningful progress, then next queued item.

- **Empty:** state that downloads continue without this page and link to S3/S4.
- **Loading/reconnecting:** retain last known states, label them stale, and reconnect without resetting progress.
- **Redis unavailable:** explain degraded mode; local playback remains available; new jobs are disabled.
- **Failure:** show a plain-language summary, expandable technical detail, and Retry. Cancel is available for queued/running work; Retry returns a job to the serial queue.
- **Restart recovery:** an interrupted job visibly returns to queued before restarting from the beginning.
- **Deleted result:** completed history remains in place as “Deleted track” with provider, phase, state, and timestamps, but no deleted track/source metadata.
- **Density/hierarchy:** current phase, progress, Cancel/Retry are immediate. Full error detail and completed history are disclosed.

### S12 — Settings

**Regions:** global proxy at the top with Save and Test; provider list with enabled state, credential fields, Test, and health; **link inspection** with mode and per-provider timeouts; storage/tool diagnostics showing mounted path, free space, and required binaries.  
**Primary action:** save and test the proxy, then resolve provider health.  
**Eye first:** proxy state and last test result.

- **Link inspection:** a mode choice between **Fast** (default) and **Thorough**,
  each stating its trade in one line — Fast returns in about a second but without
  album, disc, or track number; Thorough asks SpotDL and returns everything, but
  can take minutes on a slow connection. Below it, one timeout per inspection
  path, each showing its unit and default. Fast mode always falls back to
  Thorough on failure, and the mode copy says so, so the choice reads as "what to
  try first", not "what is allowed".
- **Loading:** settings fields remain stable while health checks resolve independently.
- **Validation:** reject malformed proxy URLs before save; credentials are never echoed after persistence. Timeouts are bounded, and a value outside its range is rejected at the field with the permitted range stated.
- **Proxy failure:** identify connection, authentication, timeout, or unsupported-scheme failure; never suggest direct fallback.
- **Provider error:** isolate it to that provider and show the next action. Missing Last.fm key marks enrichment optional, not globally unhealthy.
- **Diagnostics error:** distinguish unreadable mount, low disk space, unavailable Redis, missing FFmpeg, SpotDL, or yt-dlp.
- **Density/hierarchy:** proxy and provider recovery are direct. Redis URL, bind mounts, and LAN port are read-only deployment concerns.

### S13 — Track details/editor

**Regions:** playback identity and availability; editable title, artist, album, year, disc/track number; artwork preview with Upload, URL, and Last.fm actions; source identities; Save; destructive Delete action at the end.  
**Primary action:** save corrected metadata consistently.  
**Eye first:** title/artist and artwork.

- **Loading:** disable edits until the complete record is loaded.
- **Validation:** preserve edits and identify blank/invalid fields or a duplicate collision before mutation.
- **Save in progress:** prevent a second edit/delete while file, tags, artwork, path, and database synchronize.
- **Save error:** state that the previous version remains authoritative; offer Retry.
- **Missing file:** disable tag/path mutation, retain metadata, and offer permanent cleanup through S15.
- **Density/hierarchy:** common correction actions are visible; source IDs are disclosed; Delete is separated from Save.

### S14 — Queue drawer

**Regions:** current track; upcoming manually ordered rows; reorder/remove/clear controls; close action.  
**Primary action:** inspect or adjust what plays next.  
**Eye first:** current and next track.

- **Empty:** explain that playing a track, artist, album, year, or playlist creates a queue.
- **Unavailable/deleted track:** remove deleted tracks; label transiently missing tracks and skip them.
- **Error:** queue editing is browser-local, so errors are limited to unavailable media and failed playback.
- **Density/hierarchy:** reorder and remove are direct; metadata editing links to S13. Shuffle, repeat, and persistence after refresh are absent.

### S15 — Delete-track confirmation

**Regions:** track identity; permanent shared-impact warning; affected playlist count and current-queue impact; Cancel and Delete Permanently.  
**Primary action:** cancel unless permanent deletion is intentional.  
**Eye first:** irreversible scope.

- **Loading:** calculate server-owned playlist references and combine them with current-player/queue occurrences from this browser session before enabling deletion.
- **Error:** keep the dialog open and state that deletion did not complete; if recovery is running, prevent a second attempt.
- **Success:** close, remove the track everywhere, and advance/stop the player if it was current.
- **Density/hierarchy:** no secondary settings or metadata actions appear.

### S16 — Playlist editor dialog

**Regions:** playlist name field; Cancel and Create/Save.  
**Primary action:** create or rename the active profile’s playlist.  
**Eye first:** playlist name.

- **Validation:** reject blank or duplicate names within the profile and preserve input.
- **Loading/error:** prevent duplicate submission and retain the field for retry.
- **Density/hierarchy:** only the name is editable; there is no artwork, sharing, collaboration, or profile management.

## Key flows

### F1 — Kernel: discover, download, correct, playlist, play, persist

1. **S1:** User sees named profiles, selects one; system opens S2 with that profile’s playlists and the shared library.
2. **S3:** User sees local-first search, enters a query; system returns matching playable local tracks or an explicit no-match state.
3. **S3:** User clicks Search Deezer; system preserves local results, shows online loading, then renders a separate internet-only result list.
4. **S3:** User clicks Download on a Deezer result; system rejects a duplicate or creates a queued job and exposes its global status.
5. **S11:** User sees queued → downloading → converting → tagging → completed; system runs the job independently of navigation or browser closure.
6. **S2:** User returns to Library; system lists the new playable track with provider metadata and optional Last.fm gap fills.
7. **S13:** User opens Edit, corrects metadata/artwork, and saves; system keeps the prior record visible until file, ID3, artwork, path, and database all agree.
8. **S16/S2/S10:** User creates a personal playlist, uses Add to Playlist on the track, then opens it; system saves the track at the end of that profile’s manual order.
9. **S10:** User clicks Play Playlist; system creates the browser-session queue and starts playback.
10. **S2–S12:** User navigates elsewhere; system changes only the content viewport and playback continues.
11. **S1/S2/S9:** After restarting Chillify, user selects the same profile; system restores the track, corrected metadata, and playlist, but not the prior playback session.

### F2 — Add one YouTube track with reviewed metadata

1. **S4:** User pastes a YouTube video URL; system validates that it is one supported video and inspects its metadata through the configured proxy.
2. **S5:** User sees extracted values, corrects title/artist/album/year/track data, and optionally replaces artwork.
3. **S5:** User clicks Queue Download; system validates required fields and duplicate signals.
4. **S11:** User sees the serial job progress; system cleans temporary files on failure/cancel or produces the organized MP3 on success.
5. **S2:** User sees and can play the reviewed track using the saved metadata.

### F3 — Browse and play a context

1. **S2:** User chooses Artists, Albums, or Years; system shows only local managed content.
2. **S6/S7/S8:** User opens a context and sees the exact ordering that playback will use.
3. **S6/S7/S8:** User clicks Play; system replaces the session queue and starts its first playable track.
4. **S14:** User opens Queue, reorders or removes an upcoming item; system applies the change only to this browser session.
5. **S3/S9/S12:** User navigates; system preserves the adjusted queue and uninterrupted playback until refresh or profile switch.

### F4 — Recover from provider or queue failure

1. **S3/S4:** User starts an online action; system reports a proxy/provider error without disturbing local results or playback.
2. **S12:** User opens Settings, corrects the global proxy, and clicks Test; system reports the specific test outcome without bypassing the proxy.
3. **S11:** If Redis is unavailable, user sees acquisition disabled while existing tracks remain playable.
4. **S11:** When Redis returns, system requeues unfinished database jobs; interrupted work visibly restarts from the beginning.
5. **S11:** User retries a failed job or cancels it; system updates global status and advances the serial queue.

### F5 — Cycle 002 kernel: inspect a Spotify link quickly, legibly, and cancellably

1. **S4:** User pastes a Spotify track link and submits; system shows the phase "Reading Spotify details" with elapsed seconds and an active Cancel.
2. **S4:** System returns a candidate in about a second and continues to review.
3. **S5:** User sees title, artist, year, duration, and cover filled, with album, disc, and track number marked not-yet-known rather than blank; user queues the download.
4. **S4:** On a later link whose fast lookup fails, user sees the phase change to "Matching with SpotDL" naming the fallback; the elapsed timer continues rather than resetting, and the inspection still succeeds.
5. **S4:** User starts another inspection and presses Cancel mid-phase; system stops, leaves no provider subprocess running, and restores the editable URL with the input preserved.
6. **S12:** User switches link inspection to Thorough; system saves it and states the trade.
7. **S4:** User inspects a Spotify link again; system uses SpotDL first and returns album, disc, and track number.
8. **S12:** User restarts the app and reopens Settings; system shows the saved mode and timeouts unchanged.

## Cross-screen interaction rules

- A local track always exposes Play; an internet result never does.
- Every local track row exposes Add to Playlist through the same row-action pattern.
- Starting a context replaces the current session queue. Playing one row starts at that row and queues the remaining tracks in the current view order.
- Navigating never changes playback. Refresh or profile switch may stop it and clear the queue.
- Job state is global and server-owned; playback queue state is browser-owned.
- Toasts acknowledge short successes. Persistent banners carry degraded states. Inline messages own recoverable form/provider errors.
- Progress is determinate only when a provider reports a real percentage; otherwise show the current phase without invented progress.
- Destructive shared-track deletion always uses S15. Removing a track from a personal playlist does not delete shared media.
- Keyboard order follows the visual reading order; focus returns to the invoking control after a modal/drawer closes.

## Operator surfaces

### Docker Compose lifecycle

Invocation: `docker compose up -d`, `docker compose stop`, and `docker compose down` from the repository. Output is standard Compose service status; any service startup/health failure returns a non-zero exit and remains inspectable through Compose logs.

### Deployment configuration

Invocation: edit the repository `.env` before starting Compose. It supplies LAN port, host bind-mount paths, `REDIS_URL`, the settings-encryption key, and host UID/GID; invalid/missing values or unwritable mount ownership fail startup with a named configuration error rather than appearing as editable application screens. The encryption key must be backed up with the mounted data.
