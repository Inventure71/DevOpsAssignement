> Historical checkpoint/research document. Current architecture, complete offline Demo and storage/setup are described in [README](../README.md), [architecture](05_ARCHITECTURE.md) and [implementation status](08_IMPLEMENTATION_STATUS.md). Four-song references below describe the earlier development seed.

# Privacy and code organization cleanup

## Goal and constraints

Players see their own round answer, public rankings and the revealed song/listener facts. Other players' answers remain server-side, including diagnostic void attempts. The host follows the same privacy rule. Existing scoring, audio continuity, room identity and character animation behavior must stay intact.

This is an in-place refactor on the existing dirty `feature/frontend` checkout. No staging, commits, branch changes or remote operations are part of this task. The starting verification baseline is 129 Python tests and 55 frontend tests.

## Target responsibilities

```text
frontend/
  app.mjs                     Browser composition and lifecycle wiring
  application/               Local state, commands, polling and screen mounting
  transport/                 HTTP and estimated server clock
  audio/                     Host source/preload and measured audio analysis
  game/                      Pure timing and result display projections
  components/                Reusable controls and character rendering
  screens/                   Page composition
  lab/                       Isolated fixtures and scene lifecycle
  styles/                    Tokens and presentation
```

The server's Game projection enforces answer visibility. The frontend consumes that narrow contract rather than filtering a list of private answers. Audio controllers own sources; renderers own drawing. Screen mounting and header/menu behavior move out of the bootstrap. The lab's fixtures and character studio remain separate from its scene controller. Modules receive the dependencies they need; there is no service locator, new framework or speculative interface hierarchy.

## Checkable plan

- [x] Enforce private reveal replies for host and guests; retain internal answers.
- [x] Remove the disclosure/table, its rendering code and unused styles.
- [x] Record the privacy decision and reconcile game/API/data/presentation docs.
- [x] Audit existing boundaries and confirmed dead/duplicate paths.
- [x] Group application, transport, audio, game and lab responsibilities; update imports and the code map without compatibility wrappers.
- [x] Extract screen/header behavior from bootstrap and narrow component contracts.
- [x] Split fixture construction and standalone character setup from lab lifecycle.
- [x] Verify private replies through real HTTP/SQLite, existing behavior tests, imports, formatting and served assets. Native preview was attempted; open timed out.

## Review criteria

Single responsibility means each module has a concrete reason to change. Dependency inversion means the orchestration code receives transport/audio/storage collaborators rather than hiding them in UI rendering. Small component contracts avoid exposing unused state. Composition and existing drawing callbacks provide extension where it is needed. No inheritance is introduced merely to claim substitution coverage. Testing must exercise the actual privacy and lifecycle boundaries. Live visual and audible playback acceptance remains separate from unit-test or syntax results.

## Verified outcome

- Rooms SQL is owned by `rooms/repository.py`; the service keeps admission, identity, retention and snapshot rules and uses caller-owned transactions.
- Native `.mjs` imports make module ownership explicit without a per-folder manifest. Application screen lifecycle and static header controls are separate from the bootstrap. Lab data and character setup are independent of navigation.
- One readiness result supplies the lobby's start state and explanation. Shared keyed reconciliation retains player components across column moves. Obsolete answer-table and unused entry selectors are removed.
- Runtime lifecycle generations prevent stopped async callbacks from updating state, renewing leases or scheduling duplicate loops after a restart.
- Automated evidence: 132 Python tests, 94% Rooms/Game coverage, and 66 frontend tests. All 38 native modules pass syntax/import and HTTP/MIME checks.

The class SOLID/code-smell material guided responsibility separation, dependency injection, retained identities and removal of dead contracts. Concrete composition and callbacks supply extension points. There is no inheritance hierarchy to which substitution rules need to be applied; inventing one would add unnecessary coupling. Live visual and audible verification of this cleanup remains pending because the native preview could not attach. No Git/GitHub state was changed.
