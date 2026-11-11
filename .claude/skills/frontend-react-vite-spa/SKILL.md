---
name: frontend-react-vite-spa
description: "Use when changing a React + Vite SPA: vite.config, router, import.meta.env, dev proxy, code splitting, SPA fallback, Vitest. Not Next.js -> frontend-react-nextjs. Server state -> frontend-data-fetching-caching."
license: Apache-2.0
metadata:
  version: "1.0.0"
---

# React + Vite SPA engineering

Scope: client-rendered React apps built by Vite and served as static files, by a web server or by their own API. This
skill decides what the bundle may contain, how dev routing mirrors production, how the bundle is split and how tests are
split. Not covered: Next.js, an SSR or edge build (estuda-facil-ai builds one beside its client), React Router framework
mode, Tailwind setup, service workers.

Written against `vite` 8.x, `react` 19.x, `react-router` 8.x or `@tanstack/react-router` 1.x and `vitest` 5.x, docs
checked 2026-11-11. The owner's apps run Vite 6 to 8, so the installed version decides (first dated trap).

## Procedure

Resolve API facts locally first: the installed version from the lockfile (package.json is only the constraint), the
installed package's types and source (`node_modules/vite`, `vitest`, the router package) and the repo's existing call
sites. Open a `## Sources` URL only when those leave a contract uncertain and network exists, and check the installed
major against this skill's written-against line.

### 1. Detect before choosing

- Read the lockfile for `vite`, `@vitejs/plugin-react`, the router and `vitest`; read `vite.config.*`, any separate
  `vitest.config.*`, and the `build` script chain.
- Keep the project's router. Observed 2026-11-11 across 11 apps: TanStack Router (3), React Router 6 with
  `BrowserRouter` (1), wouter (1), no router dependency (6). Adding a router or switching routers is its own change.
- An `--ssr` build or an edge worker beside the client build is out of scope here; say so and stop at that boundary.

### 2. Environment: what the bundle may know

- A `VITE_` variable is public: Vite inlines it into the JavaScript every visitor downloads. It never holds a key, token,
  password or private URL; those stay behind the API. Never set `envPrefix` to `''`, which exposes every variable.
- The config file does not see `.env` files: they load after the config is evaluated, so `process.env.X` inside
  `vite.config` reads only the shell. Use `loadEnv(mode, root, 'VITE_')` when the config needs a value.
- One name, one job: a `VITE_API_URL` used as the dev-proxy target (config, server side) and as the browser base URL
  (public) is two settings sharing a name; split them or read both through `loadEnv`.
- A build default that must hold on a fresh CI clone lives in a tracked file, never in a gitignored `.env` (vadefocus
  studio resolves it in `vite.config` with `loadEnv` and `define`, and skips it under test so `vi.stubEnv` stays in control).
- A required public setting is checked once at start or build. estuda-facil-ai throws "VITE_API_URL is not set" in a
  production build only when the base URL is first resolved at run time, which is where a bad deploy surfaces last.

### 3. API calls and the dev proxy

- The browser calls same-origin relative paths (`/api/...`). `server.proxy` is the dev copy of the production host's
  routing, so a route added to one is added to the other in the same change. An absolute API URL baked at build time is
  for an API on another origin, and then the API owns CORS.
- Anchor every proxy key to a whole path segment. Where the SPA has a screen that shares an API prefix (`/ingest`,
  `/admin`), narrow the key to the API sub-path, or add `bypass` returning `/index.html` for `Accept: text/html`
  navigations. `bypass` is in the installed vite types (`ProxyOptions`) but not on the docs page: read the types.
- A proxy for a `/apis` screen must not catch it as `/api`: match `=== '/api' || startsWith('/api/')`
  (Projects_Manager's host does).
- Dev server host: the default is `localhost`. `0.0.0.0` only inside a container whose published port binds `127.0.0.1`,
  with `allowedHosts` set for the container's hostname. Projects_Manager binds `127.0.0.1` because, its config notes, on
  Windows `localhost` can resolve to `::1` and a client on `127.0.0.1` is refused.

### 4. Routing and the production host

- The host returns `index.html` for every path that is neither a file nor an API route. An API path never gets
  `index.html` (it answers the API's own 404), and a missing file under the assets directory answers 404. Dev has the
  fallback built in (`appType: 'spa'`); `vite preview` is for checking a build locally and is not a production server.
- Hosts observed: nginx `try_files $uri $uri/ /index.html`, a Fastify not-found handler, a FastAPI catch-all registered
  after every router. Whichever the host is, prove the three cases in the Done check.
- When the API serves the SPA from the same origin, choose `build.assetsDir` so it cannot collide with an API route
  (vadefocus studio uses `spa-assets` because `/assets/{id}` is an API route; the default is `assets`).
- A non-root `base` needs three matching changes: Vite's `base`, the router's base path and the proxy keys, which must be
  prefixed with that base.
- The catch-all route renders a not-found screen, never a real screen: Projects_Manager's `path="*"` renders Overview, so
  a mistyped URL looks valid.
- React Router has three modes: declarative (`BrowserRouter`, no loaders), data (`createBrowserRouter` plus
  `RouterProvider`, with loaders and actions) and framework (a Vite plugin; out of scope). Moving up a mode is its own change.
- TanStack Router file routes come from the bundler plugin; the generated route tree is plugin output (vibepm:
  `generatedRouteTree`), regenerated and never hand-edited. Loaders that feed the query client take it from router
  context: wiring and blocking-versus-prefetch go to `frontend-data-fetching-caching`.

### 5. Code splitting and chunks

- Split per route: each screen loads on demand. React `lazy` is declared at module top level (inside a component it
  resets state) under a `<Suspense>` boundary with an error boundary above it. React Router data mode has a route `lazy`
  property; TanStack Router has `autoCodeSplitting`, which splits components only: loaders and `beforeLoad` stay in the
  main bundle and the root route is never split. Set it explicitly; the docs page shows only `true`, so read the
  installed plugin's default.
- A router that imports every screen statically ships one entry chunk: Projects_Manager imports all its screens eagerly.
- `manualChunks` vendor groups need a reason: cache stability across deploys, or a heavy library used on one screen.
  Never force a lazily imported heavy library into a named chunk: vadefocus studio found that doing so for Monaco made
  Vite's shared preload helper land in it and the entry load the whole editor.
- `build.chunkSizeWarningLimit` only silences the warning. Three owner apps raised it (900, 3000, 3500): keep the number
  beside a comment naming the chunk that justifies it.
- A dynamic import that fails to load fires `vite:preloadError`; give the app one handler (reload once, then show an
  error) because a tab older than the last deploy hits it.

### 6. State and tests

- Server state lives in the query library (`frontend-data-fetching-caching`); a store or context holds client state only
  and never a copy of fetched data. Two owner apps pair zustand with TanStack Query: that line is the rule for both.
- Vitest runs unit and component tests. The default environment is `node`; pick `jsdom` or `happy-dom` in config or with a
  per-file `@vitest-environment` docblock. Browser journeys belong to Playwright (`testing-e2e-playwright`) and are never
  collected by Vitest.
- Vite only transpiles TypeScript. The type check is a separate `tsc --noEmit` before `vite build`, as the owner's build
  scripts chain it.
- Name each test purpose in its own `package.json` script (unit, e2e, coverage) so an agent runs the delta, not the suite.
- A vite-plugin-pwa service worker is `pwa-engineering`'s; `@tailwindcss/vite` and token wiring are
  `frontend-styling-architecture`'s.

## Dated traps

| Trap | Symptom, cause, fix |
|---|---|
| `[vite@8, 2026-11-11]` Rolldown names | `build.rollupOptions` is a deprecated alias of `build.rolldownOptions`; the object form of `output.manualChunks` is unsupported and the function form is deprecated. Use `rolldownOptions.output.codeSplitting`. Apps on Vite 6 or 7 keep the old names until upgraded; Projects_Manager uses the object form. |
| `[vite@8, 2026-11-11]` config reads `.env` | `process.env.VITE_API_URL` in `vite.config` is set only in `.env`, so the proxy silently targets its fallback (vibepm, relacionai read it this way). Use `loadEnv` or set it in the shell. |
| `[vite@8, 2026-11-11]` stale tab after deploy | A dynamic import fails and `vite:preloadError` fires. Handle it once, reload, then show an error. |
| `[vitest@5, 2026-11-11]` Playwright specs collected | Setting `test.exclude` replaces the defaults (`**/node_modules/**`, `**/.git/**`), and Playwright's own `test.use()` throws when Vitest collects a spec (vadefocus studio's note). Extend `configDefaults.exclude` and list the e2e folder. |
| `[vitest@4, 2026-11-11]` flaky large suite | Observed in vadefocus studio (about 3.4k tests): a worker crash surfaced as different "element not found" failures per run; `maxWorkers: 2` made it deterministic. Cause not reproduced here; `maxWorkers` is the documented knob. |
| `[SPA host, 2026-11-11]` `/apis` read as `/api` | A prefix check without the trailing slash answered a SPA deep link with the API's 404 (Projects_Manager). Match the whole segment. |

## Validation: Done check

- `tsc --noEmit` and `vite build` pass, and the build output shows no lazy screen or heavy library inside the entry chunk.
- Every `VITE_` name read in `src/` and `vite.config` is a public value: no `KEY`, `SECRET`, `TOKEN` or `PASSWORD` in the
  name, no private URL in its default.
- Against the production host, not `vite preview`: a nested SPA URL returns `index.html`; an unknown `/api/...` path
  returns the API's error; a missing `/assets/...` file returns 404.
- Each dev-proxy key matches a route the production host serves the same way; a proxy key on an SPA path has `bypass`.
- The Vitest delta passes and no Playwright spec is collected by it.
- The changed screen was verified in a real browser (`frontend-delivery-checklist`).

## Sources

| Topic | Official entry URL | Read when | Content checked |
|---|---|---|---|
| Env variables and modes | https://vite.dev/guide/env-and-mode | `VITE_` exposure, `.env` priority, `.local` files | 2026-11-11 |
| Env in the config file | https://vite.dev/config/ | `loadEnv`, what `vite.config` can read | 2026-11-11 |
| Shared options | https://vite.dev/config/shared-options | `base`, `appType`, `envPrefix`, `define` | 2026-11-11 |
| Server options | https://vite.dev/config/server-options | `server.proxy`, `host`, `allowedHosts` | 2026-11-11 |
| Build options | https://vite.dev/config/build-options | `outDir`, `assetsDir`, `chunkSizeWarningLimit` | 2026-11-11 |
| Building for production | https://vite.dev/guide/build | chunking, `vite:preloadError`, build target | 2026-11-11 |
| Migration to Vite 8 | https://vite.dev/guide/migration | `rolldownOptions`, `manualChunks`, minifier | 2026-11-11 |
| Features (TypeScript, preload) | https://vite.dev/guide/features | type checking, client types, CSS and async chunks | 2026-11-11 |
| Static deploy and preview | https://vite.dev/guide/static-deploy | `vite preview`, host rewrites | 2026-11-11 |
| React Router modes | https://reactrouter.com/start/modes | declarative, data or framework mode | 2026-11-11 |
| React Router route object | https://reactrouter.com/start/data/route-object | route `lazy`, `loader`, `Component` | 2026-11-11 |
| TanStack Router code splitting | https://tanstack.com/router/latest/docs/framework/react/guide/code-splitting | `autoCodeSplitting`, `.lazy.tsx` | 2026-11-11 |
| React `lazy` | https://react.dev/reference/react/lazy | lazy components and Suspense | 2026-11-11 |
| Vitest environment | https://vitest.dev/config/environment | `jsdom`, `happy-dom`, per-file docblock | 2026-11-11 |
| Vitest exclude | https://vitest.dev/config/exclude | collecting or skipping e2e specs | 2026-11-11 |
| Vitest maxWorkers | https://vitest.dev/config/maxworkers | worker count on a large suite | 2026-11-11 |

## Works with

| Skill | Owns | Load when |
|---|---|---|
| `frontend-design` | the visual standard: variant, composition, text budgets | defining or changing how a screen looks |
| `accessibility` | accessible interaction: semantics, keyboard, focus, contrast | a UI has a semantic, keyboard or focus barrier |
| `frontend-delivery-checklist` | the done gate: real browser, states, real backend | a UI change is about to be called done |
| `testing-e2e-playwright` | browser tests: fixtures, locators, waits | writing or fixing a Playwright test |
| `pwa-engineering` | install and offline: manifest, service worker, update | the surface is installable or works offline |
