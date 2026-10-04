# Privacy and code organization cleanup

## Privacy

Each player receives their own answer and score, public rankings and revealed song/listener facts. Other answers remain server-side, including void-attempt diagnostics. The host follows the same rule.

The cleanup removed the shared answer table and enforced visibility in Game's API projection. Scoring, room identity and audio continuity were retained.

## Organization

- Rooms repositories own SQL; services own admission, retention and snapshot policy.
- Browser application modules own commands, polling and screen lifecycle; transport and audio have separate collaborators.
- Components own reusable rendering; screens compose them. Lab fixtures and character setup are separate from navigation.
- Lifecycle generations invalidate callbacks from stopped sessions. Keyed rendering retains player components across updates.

The [code map](09_CODEBASE_MAP.md) shows current module locations. The [API contract](07_API_AND_RUNTIME.md) defines private responses; [testing strategy](18_TESTING_STRATEGY.md) identifies their verification owners.
