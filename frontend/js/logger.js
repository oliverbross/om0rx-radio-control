/**
 * Centralized Logger Module
 * Provides leveled, filtered, and batched logging for the application
 * 
 * Features:
 * - Log levels: error, warn, info, debug
 * - URL parameters: ?debug, ?log=level, ?topics=topic1,topic2, ?sample=0.5
 * - Environment-aware (production suppression)
 * - Batching support for high-frequency events
 * - Change detection for status updates
 * - Performance optimized
 */

(function() {
  'use strict';

  const LEVELS = {
  error: 0,
  warn: 1,
  info: 2,
  debug: 3
};

// Parse URL parameters once at load
const urlParams = typeof location !== 'undefined' ? new URLSearchParams(location.search) : new URLSearchParams();

// Configuration
const config = {
  // Debug enabled: explicit URL param or non-production
  debugEnabled: urlParams.has('debug') || (typeof process !== 'undefined' && process.env?.NODE_ENV !== 'production'),
  
  // Current log level
  currentLevel: LEVELS[urlParams.get('log') || 'info'] ?? LEVELS.info,
  
  // Topic filter (if set, only log these topics)
  topics: new Set((urlParams.get('topics') || '').split(',').map(s => s.trim()).filter(Boolean)),
  
  // Sample rate (0-1, where 1 = log everything)
  sampleRate: Math.max(0, Math.min(1, Number(urlParams.get('sample') ?? 1))),
  
  // Whether to use colors in console
  useColors: typeof process === 'undefined' || process.env?.NODE_ENV !== 'production'
};

// Topic-specific batchers for high-frequency logs
const batchers = new Map();

/**
 * Color codes for console output
 */
const colors = {
  error: 'color: #f44336; font-weight: bold',
  warn: 'color: #ff9800; font-weight: bold',
  info: 'color: #2196f3',
  debug: 'color: #9c27b0'
};

/**
 * Check if a topic should be logged based on filters
 */
function shouldLogTopic(topic) {
  if (!config.topics.size) return true; // No filters = log all
  return config.topics.has(topic);
}

/**
 * Check if a level should be logged based on current level
 */
function shouldLogLevel(level) {
  return (LEVELS[level] ?? 99) <= config.currentLevel;
}

/**
 * Check if should sample this log (for sampling high-frequency logs)
 */
function shouldSampleLog() {
  if (config.sampleRate >= 1) return true;
  return Math.random() <= config.sampleRate;
}

/**
 * Main logging function
 * @param {string} level - Log level: 'error', 'warn', 'info', 'debug'
 * @param {string} topic - Topic/category for filtering
 * @param {...any} args - Arguments to log
 */
  function log(level, topic, ...args) {
    // Skip if debugging disabled
    if (!config.debugEnabled) return;
    
    // Skip if level not enabled
    if (!shouldLogLevel(level)) return;
    
    // Skip if topic not in filters
    if (!shouldLogTopic(topic)) return;
    
    // Skip if not sampling
    if (!shouldSampleLog()) return;
    
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 });
    
    // Format message
    const prefix = config.useColors 
      ? `%c[${timestamp}] [${topic}]`
      : `[${timestamp}] [${topic}]`;
    
    const style = config.useColors ? colors[level] : '';
    
    // Output
    const consoleMethod = console[level] || console.log;
    if (config.useColors) {
      consoleMethod(prefix, style, ...args);
    } else {
      consoleMethod(prefix, ...args);
    }
  }

  /**
   * Batch similar logs into a single aggregated message
   * Useful for high-frequency events
   * @param {string} topic - Topic/category
   * @param {string} level - Log level
   * @param {string} key - Unique key for this batch (e.g., 'spot-count')
   * @param {function} formatter - Function that formats the batch message
   * @param {number} intervalMs - Time window for batching
   * @param {any} data - Data to include in batch
   */
  function batch(topic, level, key, formatter, intervalMs = 1000, data) {
    const batchKey = `${topic}:${key}`;
    
    if (!batchers.has(batchKey)) {
      batchers.set(batchKey, {
        items: [],
        timer: null
      });
    }
    
    const batcher = batchers.get(batchKey);
    batcher.items.push(data);
    
    if (batcher.timer) {
      clearTimeout(batcher.timer);
    }
    
    batcher.timer = setTimeout(() => {
      if (batcher.items.length > 0) {
        const message = formatter(batcher.items);
        log(level, topic, message);
        batcher.items = [];
      }
    }, intervalMs);
  }

  /**
   * Change detector for status updates
   * Returns an object with previous state and change detection logic
   */
  class ChangeDetector {
    constructor(initialState = {}) {
      this.previous = { ...initialState };
      this.current = { ...initialState };
    }
    
    /**
     * Check if a value changed and update tracking
     * @returns {boolean} true if changed
     */
    hasChanged(key, newValue) {
      const changed = this.previous[key] !== newValue;
      if (changed) {
        this.previous[key] = newValue;
        this.current[key] = newValue;
      }
      return changed;
    }
    
    /**
     * Get all changes from previous state
     * @returns {object} object with only changed keys
     */
    getChanges(newState) {
      const changes = {};
      Object.keys(newState).forEach(key => {
        if (this.previous[key] !== newState[key]) {
          changes[key] = newState[key];
          this.previous[key] = newState[key];
        }
      });
      return changes;
    }
    
    /**
     * Update all tracked values
     */
    updateAll(newState) {
      this.previous = { ...newState };
      this.current = { ...newState };
    }
  }

  /**
   * Get current configuration
   */
  function getConfig() {
    return {
      debugEnabled: config.debugEnabled,
      currentLevel: Object.entries(LEVELS).find(([, v]) => v === config.currentLevel)[0],
      topics: Array.from(config.topics),
      sampleRate: config.sampleRate
    };
  }

  /**
   * Update configuration at runtime
   */
  function setConfig(newConfig) {
    if ('debugEnabled' in newConfig) config.debugEnabled = newConfig.debugEnabled;
    if ('currentLevel' in newConfig) config.currentLevel = LEVELS[newConfig.currentLevel] ?? config.currentLevel;
    if ('topics' in newConfig) config.topics = new Set(newConfig.topics || []);
    if ('sampleRate' in newConfig) config.sampleRate = Math.max(0, Math.min(1, newConfig.sampleRate));
  }

  // Export to window for global access
  window.Logger = {
    log,
    batch,
    ChangeDetector,
    debugEnabled: config.debugEnabled,
    getConfig,
    setConfig
  };

})();