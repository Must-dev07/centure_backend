# Refonte — Phase 4: pytest coverage (backend)

## Target phase

This is **Phase 4** of the enrollment refonte, as defined in `REFONTE_system.md` §8, step 4:
"Tests pytest de la section 7."

Prerequisite: Phases 1, 2, and 3 are complete and validated by the owner.

`REFONTE_system.md` (in the `webapp` repository, `webapp/REFONTE_system.md`) is the **sole source of
truth** for requirements, completed by the owner decisions recorded in the Phase 1–3 files. Tests
must verify that specified behavior, as implemented in Phases 1–3. Do not invent expectations.

Owner decisions reflected in the tests:

- Invitation validity is **7 days**.
- Doctor self-registration is unchanged; no doctor verification/approval workflow exists.
- Legacy babies: `enrollment_reason="other"`,
  `enrollment_notes="Legacy enrollment — original enrollment reason was not recorded."`.
- Admin enrollment: `Baby.enrolled_by` = admin, enrollment history entry `recorded_by=None`.
- Invitation delivery by link (`invitation_link`), no email; tokens never listed.
- `parent=None` is a valid baby state.
- Accept: unknown token → 404; expired or not pending → 410; existing parent account → linked, no
  duplicate.
- Parents cannot delete babies.

## IN scope

### A. Required tests — `REFONTE_system.md` §7

1. Baby creation by a parent → **403**.
2. Baby creation by a doctor with the email of an existing parent → baby linked directly, **no**
   invitation created.
3. Baby creation by a doctor with an unknown email → baby created with `parent=None`, `pending`
   invitation created.
4. Accepting a valid invitation → account created, baby(ies) attached, JWT tokens returned.
5. Accepting an expired invitation → **410**.
6. Two babies created with the same unregistered email → the existing `pending` invitation is reused.
7. `PATCH /babies/{id}/` by the owning parent → **403** (previously 200).
8. Pairing by the assigned doctor → **200** (new case).
9. `POST /auth/register` with `role=parent` → **403**.

### B. Enrollment and models (Phase 1–2)

- `parent_status` is `"linked"` / `"invitation_pending"` in the `POST /babies/` response.
- `invitation_link` equals `app://invite/{token}` of the created invitation when pending, is the
  **same** link when the invitation is reused, and is `null` when linked.
- A reused `pending` invitation that has already passed `expires_at` is marked `expired` and a new
  invitation (new link) is created.
- New invitations have `expires_at` = creation time + 7 days and `created_by` = the enrolling user.
- `enrollment_reason == "other"` without `enrollment_notes` → 400.
- Enrollment history entry: doctor enrollment → `recorded_by` is that doctor; admin enrollment →
  `recorded_by` is `None` and `Baby.enrolled_by` is the admin.
- Admin can also create a baby (201).
- Legacy data migration: existing babies receive `enrollment_reason="other"`, the exact legacy note,
  and a valid `enrolled_by` (migration test if practical with the project's tools; otherwise report
  why it was verified differently).

### C. Permissions (Phase 2)

- `PATCH /babies/{id}/`: assigned doctor → allowed (non-core fields; the existing core-field
  restriction for doctors still applies); admin → allowed; other doctor → refused.
- `DELETE /babies/{id}/`: owning parent → **403**; admin → allowed; doctor → refused (unchanged).
- `GET /babies/` and `GET /babies/{id}/`: unchanged for parent (own), assigned doctor, admin; a
  parent cannot see a baby without a parent.
- Unpair by the assigned doctor → allowed; pair/unpair by an admin → allowed; pair by a
  non-assigned doctor → refused; pair by the owning parent → still allowed.
- `POST /auth/register` with `role=doctor` succeeds exactly as before; `role=admin` is still rejected.

### D. `parent=None` safety (Phase 2)

For a baby with `parent=None`:

- pairing and unpairing by the assigned doctor/admin succeed without error (no parent notification;
  doctor notification behavior unchanged);
- alert notification dispatch (`dispatch_alert_notifications`) does not crash and notifies only
  existing targets;
- an admin-created doctor request, and a doctor accepting or declining it, succeed without error;
- `GET /babies/{id}/` serializes `parent_name` as empty.

### E. Invitations (Phase 3)

- `GET /parents/`: doctor and admin allowed; parent refused; `?search=` matches email/name; existing
  admin behavior and response shape unchanged.
- `GET /invitations/?status=pending`: doctor and admin allowed; parent and anonymous refused; doctor
  scope (own or assigned-baby invitations only); response contains **no** `token` and **no**
  `invitation_link`.
- Accept:
  - unknown token → **404**;
  - expired (status `expired`, or `pending` past `expires_at`) → **410**;
  - already accepted → **410**;
  - existing parent account + correct password → babies linked to the existing parent, no
    duplicate `User`/`Parent`, tokens returned, invitation `accepted`;
  - existing parent account + wrong password → **401**, nothing attached, invitation still
    `pending`;
  - email belonging to a doctor/admin → **409**, nothing created;
  - invalid password for a new account → **400**, nothing created.
- Resend:
  - doctor (in scope) and admin allowed; parent refused; doctor out of scope refused;
  - `pending` invitation → new token, `expires_at` = now + 7 days, response contains the new
    `invitation_link`; the old token now returns 404 on accept;
  - `expired` invitation → back to `pending` with a new token and a 7-day validity;
  - `accepted` invitation → **409**, unchanged.
- Watchdog: `pending` invitations past `expires_at` become `expired`; others are unchanged.

Only test behavior specified by the source or the owner decisions. If something was reported as
unspecified in an earlier phase summary, note it instead of asserting an invented expectation.

## OUT of scope

- Any application code change. If a test reveals a bug, **do not fix it**. Report it with the failing
  test and wait for the owner's decision.
- Model, migration, permission, view, serializer, URL, or settings changes.
- Dashboard (§5) and mobile (§6) work.

## Rules that apply to this phase

- Use the existing setup: pytest + pytest-django (`pytest.ini`), fixtures in `conftest.py` (`api`,
  `parent`, `doctor`, `admin_user`, `baby`, `belt`, `parent_client`, `doctor_client`,
  `admin_client`), and `tests/factories.py` (factory_boy). No new test framework or dependencies.
- Put tests in the existing `<app>/tests/test_*.py` structure (and in the invitations location chosen
  in Phase 1).
- Do not modify existing tests to hide a regression. Extending shared factories or fixtures is
  allowed when needed.
- Do not touch `analysis`, `Measurement`, pagination, JWT token rotation, or unrelated endpoints.
- No destructive data operations: tests use the pytest-django test database only.
- Preserve existing unrelated Git changes. No push, pull, fetch, or remote changes.
- Respect `CLAUDE.md` and `.claude/settings.json`.
- Useful resources: `django-expert` skill (testing strategies), `backend-tester` agent.

## Checks

- Test command: `.venv/Scripts/python.exe -m pytest` from the repository root: new tests first, then
  the full suite.
- The existing suite must keep passing (the source cites 105 existing tests).

## Completion — STOP

When Phase 4 is complete:

1. List every test file changed or added.
2. Map each §7 item and each group B–E above to the test(s) that cover it.
3. Report the full-suite results (passed/failed/skipped counts).
4. Report any failing test that indicates a bug in Phases 1–3 (not fixed), and unresolved issues.
5. **STOP.** Do not begin the dashboard (§5) or mobile (§6) phases. Wait for explicit validation.
