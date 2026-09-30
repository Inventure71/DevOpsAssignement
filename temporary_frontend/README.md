# Browser client

The server serves `index.html` at `/` and mounts `static/` at `/static`.
The browser loads native ES modules directly. There is no bundler, package
installation or separate frontend server.

## Responsibilities

| Module | Owns |
| --- | --- |
| `static/js/app.js` | Browser startup and wiring dependencies together |
| `static/js/transport.js` | JSON requests, API paths, request IDs and server clock estimate |
| `static/js/state.js` | Presentation state, saved room identity and accepted answer receipts |
| `static/js/views.js` | Screen markup for entry, lobby and game phases |
| `static/js/view-helpers.js` | HTML escaping and character symbols |
| `static/js/renderer.js` | DOM replacement, focus preservation, timers and notices |
| `static/js/actions.js` | User gestures, forms and server commands |
| `static/js/runtime.js` | Nonoverlapping state polling and heartbeat scheduling |
| `static/js/audio.js` | Host audio lease, bounded preloading, readiness and scheduled playback |
| `static/css/styles.css` | Current visual styles, responsive rules and reduced motion |

`app.js` creates the model and transport, then injects those into rendering,
audio, actions and polling. Other modules do not import the startup module.
The audio controller keeps decoded clips and Web Audio objects private; views
receive only its lease/unlock/conflict status. The server owns identity,
phases, deadlines and scoring.

An accepted answer receipt belongs to its game and round. The model applies
that receipt to later polling responses so an older response cannot unlock an
already submitted answer. A late answer response never writes into the next
round. Native form submit clicks run before any DOM replacement.

## Verification

From the repository root, with Node installed:

```sh
node tests/frontend/client.test.mjs
```

The checks execute production modules through controlled browser and network
ports. They cover submission/polling races, form dispatch, clock rendering,
artwork fallback, preload concurrency, readiness, playback and audio lease
conflicts. Real browser and physical phone checks remain necessary for audio
permissions, audibility, network behavior and layout.

The `static/js/package.json` declares ES module semantics for these Node checks;
it has no dependencies or build commands. Audio and cover fixtures live under
`static/demo/`. Their public URLs stay `/static/demo/...`.
