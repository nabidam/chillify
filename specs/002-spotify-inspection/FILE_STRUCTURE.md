# FILE_STRUCTURE — 002 Spotify inspection

Per-cycle prediction, archived after the cycle. Only files this delta **adds or
modifies**; the rest of the tree is cycle 001's and unchanged. The repo tree is the
living truth once code exists.

```
backend/
  alembic/versions/
    0002_settings_keys.py                    NEW  widen settings key CHECK; seed
                                                  inspection + provider.spotify_api;
                                                  rollback deletes rows first
    0003_inspections.py                      NEW  inspections table + expiry index
  src/chillify/
    config.py                                MOD  inspection settings shape
    application/
      inspection.py                          NEW  InspectionPolicy: mode ordering,
                                                  fallback, phase transitions
      settings.py                            MOD  inspection + spotify_api settings
      downloads.py                           MOD  edited_fields persistence (C4);
                                                  enricher call site (C5)
    api/
      schemas/settings.py                    MOD  inspection + masked spotify_api
      schemas/links.py                       MOD  202 inspection_id, event envelope
      schemas/downloads.py                   MOD  edited_fields
      routes/settings.py                     MOD  PATCH /settings/inspection,
                                                  PATCH /settings/providers/spotify_api
      routes/links.py                        MOD  202 POST, SSE GET events, DELETE
    infrastructure/
      providers/spotify_api.py               NEW  SpotifyApiInspector, token cache
      providers/registry.py                  MOD  bind Spotify adapter + enricher
      providers/spotdl.py                    MOD  cancel predicate from inspection row;
                                                  timeout constant reverted
      db/models.py                           MOD  inspections model
      db/repositories.py                     MOD  inspection repository + cleanup
  tests/
    contract/test_spotify_api_contract.py    NEW  wire contract + shared protocol suite
    integration/test_inspection_fallback.py  NEW  credential absence, failures, 404, 429
    integration/test_inspection_lifecycle.py NEW  202/SSE/cancel/expiry/heartbeat
    integration/test_edited_fields.py        NEW  touched vs cleared through request_json
    integration/test_enrichment.py           NEW  gap fill, skip, failure, no overwrite
    fixtures/spotify_api/
      track_success.json                     NEW
      track_missing_optional.json            NEW
      token_401.json                         NEW
      track_404.json                         NEW
      track_429.json                         NEW

frontend/
  src/
    api/generated.ts                         MOD  regenerated, never hand-edited
    features/acquisition/
      AddLinkDialog.tsx                      MOD  phases, elapsed, cancel, fallback,
                                                  expired state
      useInspection.ts                       NEW  SSE subscription + cancel
      YouTubeReviewDialog.tsx                MOD  dirty tracking, not-yet-known fields
    features/settings/
      SettingsPage.tsx                       MOD  mount inspection card
      InspectionSettingsCard.tsx             NEW  credentials, mode, three timeouts
  tests/
    component/inspection-feedback.test.tsx   NEW
    e2e/inspection.spec.ts                   NEW  NFR + journey coverage
    e2e/gate-6-release.spec.ts               NEW  crystallized release journey

scripts/
  verify/nfr.sh                              MOD  NFR-1..NFR-5 measurements
  production_canary.sh                       MOD  probe from inside the api container;
                                                  report the Spotify adapter
deploy/nginx.conf                            MOD  revert 200s stopgap

specs/002-spotify-inspection/
  SPEC.md  PRD.md  PLAN.md  FILE_STRUCTURE.md
  evidence/                                  per-task evidence files
```

**No new runtime dependency is predicted.** The Spotify API uses the existing
`httpx[socks]` client through `OutboundHttp`; SSE, Fernet, Alembic and the
cancellation primitive all exist. Anything else triggers the dependency rule.
