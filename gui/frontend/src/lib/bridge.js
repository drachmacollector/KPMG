/**
 * lib/bridge.js
 *
 * Thin abstraction over window.pywebview.api so React components never
 * call the pywebview object directly.  This makes components testable
 * outside the pywebview container (e.g. in a plain browser) and keeps all
 * pywebview-specific logic in one place.
 *
 * Two helpers:
 *   call(method, ...args)  — invoke a Python Api method, returns a Promise.
 *   on(eventName, handler) — subscribe to push events from Python.
 *
 * UTF-8 note:
 *   Python's _dispatch() sends payloads as base64-encoded UTF-8 JSON.
 *   The injected JS decodes them with Uint8Array + TextDecoder (not bare
 *   atob()) so multi-byte characters in college names (Marathi/Devanagari)
 *   survive the round-trip correctly.  The on() handler receives the already-
 *   decoded plain object from e.detail — no further decoding needed here.
 */

/**
 * Returns a Promise that resolves when window.pywebview is available.
 * pywebview injects this object asynchronously after the page loads —
 * calling api.* before the `pywebviewready` event fires is the single most
 * common integration bug with this stack.
 *
 * @returns {Promise<void>}
 */
function whenReady() {
  return new Promise((resolve) => {
    if (window.pywebview) return resolve();
    window.addEventListener('pywebviewready', () => resolve(), { once: true });
  });
}

/**
 * Call a method on the Python Api class.
 *
 * @param {string} method - Exact name of the Api method (e.g. 'get_initial_state').
 * @param {...any} args   - Arguments to pass to the method.
 * @returns {Promise<any>} Resolves with whatever the Python method returns.
 */
export async function call(method, ...args) {
  await whenReady();
  return window.pywebview.api[method](...args);
}

/**
 * Subscribe to a push event dispatched by Python via window.evaluate_js().
 *
 * The handler receives the parsed payload object from e.detail.
 * Payloads are decoded on the Python side; by the time the CustomEvent
 * fires, e.detail is already a plain JS object.
 *
 * @param {string}   eventName - One of:
 *   'pipeline-log'            → { line: string }
 *   'pipeline-progress'       → { count: number, total: number | null }
 *   'pipeline-done'           → { claims_seen: number, output_file: string }
 *   'pipeline-error'          → { message: string }
 *   'pipeline-awaiting-login' → {}
 * @param {function} handler   - Called with the payload object.
 * @returns {function} Cleanup function — call it in useEffect cleanup to
 *   unsubscribe and prevent memory leaks.
 */
export function on(eventName, handler) {
  const listener = (e) => handler(e.detail);
  window.addEventListener(eventName, listener);
  return () => window.removeEventListener(eventName, listener);
}
