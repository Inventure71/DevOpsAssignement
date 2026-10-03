# Combined device playtest

The `test/optimized-game` branch combines catalog optimization and UI polish.
Use the shared HTTPS origin configured in the ignored `.env` on both devices.
The existing tunnel must remain running and forward to the configured app port.
The exact Spotify callback must remain saved in the Spotify developer dashboard.

When the server is already running this checkout, open the shared URL, refresh
the page, and create a Spotify room. Join from the second device using Invite
friends. Different nicknames can use the same approved Spotify account in this
explicit playtest mode. Enable host audio and start a five-round game.

If the app server has stopped, run from the repository root:

```bash
bash tools/run_playtest.sh
```

The launcher loads `.env`, checks the shared origin/provider configuration,
enables two-player playtest mode, prints the device URL, and runs the server in
the foreground. Stop it with Ctrl-C. It does not stop another process already
using the app port. `bash tools/run_playtest.sh --check` validates configuration
without starting a server or modifying storage. If the quick tunnel itself has
stopped, restore it separately; a new tunnel URL also requires updating `.env`
and saving the matching Spotify callback.

During the test, typing should leave search idle until Search/Enter. Selecting a
new bulk result may briefly say Checking song; repeating that verified choice
in another game uses the stored mapping. Preparation should use short player
instructions rather than provider counters. Confirm host audio is audible and
that both devices progress through reveal, leaderboard, and a new game.

The small starter catalog is enough to exercise local hits; other searches still
use the provider and save public results. The full metadata import is optional
and is not a prerequisite for this quick test:

```bash
.venv/bin/python tools/setup_catalog.py --info
.venv/bin/python tools/setup_catalog.py --all
```

It downloads approximately 2.38 GB of metadata and builds the Git-ignored search
database. Public verified mappings persist indefinitely; preview URLs renew
separately. Private listening ownership remains separate from public search.
