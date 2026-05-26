# Frontend Structure

The frontend is a no-build Vue 3 application served from `frontend/`. Runtime modules are loaded directly by `frontend/index.html`, so script order is part of the application contract.

## Entry Points

- `frontend/index.html` loads CSS, template fragments, Vue, and browser JavaScript modules.
- `frontend/templates-loader.js` loads partial HTML templates from `frontend/templates/` and dispatches `templates-loaded`.
- `frontend/js/app-main.js` mounts the Vue application after templates are ready and wires domain modules into Vue `data`, `computed`, and `methods`.

## Module Pattern

Current frontend modules expose browser globals and are merged into the Vue app. Keep new modules small and domain-based:

```javascript
window.RadioControlExample = {
    data: {},
    computed: {},
    methods: {},
};
```

When adding a required module:

1. Add its script tag in `frontend/index.html` before `js/app-main.js`.
2. Add it to the dependency check in `mountVueApp()`.
3. Merge its `data`, `computed`, or `methods` in `frontend/js/app-main.js`.
4. Run `node --check` and `scripts/maintenance/check_project.ps1`.

## Current Domains

- `core.js`, `websocket.js`, `radio-controls.js`, and `utils.js`: radio state, controls, WebSocket handling, and shared helpers.
- `dx-spots.js`: DX cluster spots, filtering, and spot actions.
- `solar-overlay.js`: reusable solar overlay rendering.
- `solar-data.js`: Vue solar data state, refresh timer, and HF condition formatting.
- `wavelog-stats.js`: Vue Wavelog statistics state, API loading, and consolidated mode counts.
- `wavelog-log-modal.js`, `wavelog-log-viewer.js`, and `local-log-modal.js`: logging views and modals.
- `wsjtx-handler.js`, `sdc-ticker.js`, and WinKeyer modules: external traffic and keyer integration.
- `ft8-modal.js` plus root/WASM FT8 assets: digital-mode UI and decoder assets.

## Cleanup Direction

Continue shrinking `app-main.js` by moving one cohesive domain at a time. Good next candidates are configuration dialog state/actions, QRZ/DXCC lookup state/actions, and previous-QSO pagination/state. Avoid broad rewrites until each extracted domain has a clear dependency boundary and smoke coverage.
