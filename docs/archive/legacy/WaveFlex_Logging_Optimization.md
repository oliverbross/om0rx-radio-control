# 🧩 Project Document: WebSocket Logging Optimization & Performance Hardening

**Project:** Wave-Flex-Spots  
**Prepared by:** Oliver Bross  
**Target audience:** Front-end developer(s) maintaining `websocket.js`, `wsjtx-handler.js`, and `sdc-ticker.js`  
**Date:** 2 November 2025  
**Version:** 1.0  

---

## 1. Background & Problem Description

During runtime, the browser console is receiving a very high frequency of messages from `websocket.js`.  
While this is useful for debugging, it introduces performance overhead. Every `console.*()` call executes on the UI thread, causing jank with DevTools open.  
Even with DevTools closed, frequent formatting and JSON operations still consume CPU cycles.

---

## 2. Objectives

1. Preserve useful debug information without flooding the console.  
2. Eliminate performance cost in production builds.  
3. Provide granular developer control via URL parameters or environment variables.  
4. Implement structured, leveled logging with change detection and batching logic.

---

## 3. Deliverables

- **`utils/logger.js`**: Centralized logger with levels (`error`, `warn`, `info`, `debug`), topic filters, and sampling.  
- **Modified `websocket.js`**: Replace raw `console.log` calls; log only changed status and batched spot updates.  
- **Modified `wsjtx-handler.js` & `sdc-ticker.js`**: Adjust logging levels and add sampling.  
- **Production build setup**: Ensure logs are stripped or disabled in production builds.

---

## 4. Implementation Guidelines

### 4.1 Create `utils/logger.js`

```js
// utils/logger.js
const LEVELS = { error: 0, warn: 1, info: 2, debug: 3 };

const params = typeof location !== 'undefined' ? new URLSearchParams(location.search) : new URLSearchParams();
const DEBUG_ENABLED = params.has('debug') || process.env.NODE_ENV !== 'production';
const CURRENT = params.get('log') || process.env.LOG_LEVEL || 'info';
const CURRENT_LEVEL = LEVELS[CURRENT] ?? LEVELS.info;
const TOPICS = new Set((params.get('topics') || process.env.LOG_TOPICS || '').split(',').map(s => s.trim()).filter(Boolean));
const SAMPLE = Number(params.get('sample') || process.env.LOG_SAMPLE_RATE || '1');

export function log(level, topic, ...args) {
  if (!DEBUG_ENABLED) return;
  if ((LEVELS[level] ?? 99) > CURRENT_LEVEL) return;
  if (TOPICS.size && !TOPICS.has(topic)) return;
  if (SAMPLE < 1 && Math.random() > SAMPLE) return;
  (console[level] || console.log)(`[${topic}]`, ...args);
}

export const debugOn = DEBUG_ENABLED;
```

---

### 4.2 Modify `websocket.js`

```js
// websocket.js
import { log } from './utils/logger.js';

let lastStatus = {};
let spotBuffer = [];
let flushTimer = null;

export function onStatusUpdate(s) {
  if (s.monitor !== lastStatus.monitor) {
    log('info', 'status', 'monitor →', s.monitor);
    lastStatus = { ...s };
  } else {
    log('debug', 'status', 'unchanged monitor =', s.monitor);
  }
}

export function onNewSpot(spot) {
  spotBuffer.push(spot);
  if (!flushTimer) {
    flushTimer = setTimeout(() => {
      const n = spotBuffer.length;
      const preview = spotBuffer.slice(0, 3).map(s => `${s.call} ${s.freq}`).join(', ');
      log('info', 'spots', `+${n} new`, n <= 3 ? preview : `${preview}, ...`);
      spotBuffer = [];
      flushTimer = null;
    }, 1000);
  }
}
```

---

### 4.3 Adjust Other Modules

- `wsjtx-handler.js`: Wrap decode messages in `log('info', 'wsjtx', ...)`; apply sampling.  
- `sdc-ticker.js`: Downgrade forwarding messages to debug level.  
- `index.js`: Import logger early so URL params are parsed once.

---

### 4.4 Production Build Configuration

**Option 1 — Terser (for Vite/Webpack):**

```js
esbuild: {
  drop: process.env.NODE_ENV === 'production' ? ['console'] : []
}
```

**Option 2 — Manual:**

```js
if (process.env.NODE_ENV !== 'production') log(...);
```

---

## 5. Acceptance Criteria

- No repetitive logs (e.g., `monitor = 92` spam).  
- Spot logs appear once per second as aggregated summary.  
- DevTools closed → zero measurable CPU overhead.  
- Debug toggling works via URL query.  
- Production build silent by default.

---

## 6. Risks & Mitigation

| Risk | Mitigation |
|------|-------------|
| Developer forgets to import `log()` | Add ESLint rule to disallow `console.*`. |
| Missed messages during batching | Aggregation only, no data loss. |
| Inconsistent debug flag parsing | Centralize config in `utils/logger.js`. |

---

## 7. Timeline

| Task | Duration |
|------|-----------|
| Implement `logger.js` | 0.5 day |
| Refactor `websocket.js` | 1 day |
| Adjust WSJT-X + SDC modules | 0.5 day |
| Review + QA | 0.5 day |
| Merge & Deploy | pending |

---

## 8. Notes

The new system ensures the console remains usable for debugging without degrading browser performance.  
Future integration may forward diagnostic events to server logs for deeper monitoring.

**Approved by:** Oliver Bross  
**ICT Systems Architect / MorseTrainerPro & Wave-Flex Ecosystem**  
📅 *Darwin, 2 Nov 2025*
