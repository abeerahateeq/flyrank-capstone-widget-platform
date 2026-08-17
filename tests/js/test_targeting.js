/**
 * Tests the targeting-rules logic (delay, path matching, once-per-visitor)
 * embedded in the served widget.js bundle (app/api/delivery.py::WIDGET_JS).
 *
 * This does NOT re-implement the logic separately — it extracts the actual
 * function bodies out of the live-served bundle via regex and evals them,
 * so a change to the real widget.js is what gets tested, not a copy that
 * could silently drift from it.
 *
 * Usage:
 *   node tests/js/test_targeting.js <path-to-widget.js-or-fetched-copy>
 *   # or, with the server running:
 *   curl -s http://localhost:8000/widget.js -o /tmp/widget.js && \
 *     node tests/js/test_targeting.js /tmp/widget.js
 */
const fs = require("fs");
const assert = require("assert");

const bundlePath = process.argv[2];
if (!bundlePath) {
  console.error("usage: node test_targeting.js <path-to-widget.js>");
  process.exit(2);
}
const source = fs.readFileSync(bundlePath, "utf8");

function extractFunction(name) {
  const re = new RegExp("function " + name + "\\s*\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n  \\}");
  const match = source.match(re);
  if (!match) throw new Error("could not find function " + name + " in bundle");
  return match[0];
}

// Build a tiny sandbox with the extracted functions plus a fake
// window.localStorage, then eval them into it.
const fakeStorageData = {};
const window = {
  localStorage: {
    getItem: (k) => (Object.prototype.hasOwnProperty.call(fakeStorageData, k) ? fakeStorageData[k] : null),
    setItem: (k, v) => { fakeStorageData[k] = v; },
  },
};

const fnSource = [
  extractFunction("pathMatches"),
  extractFunction("shouldShowOnThisPath"),
  extractFunction("seenKey"),
  extractFunction("hasAlreadyBeenSeen"),
  extractFunction("markAsSeen"),
].join("\n\n");

// eslint-disable-next-line no-eval
eval(fnSource); // defines pathMatches, shouldShowOnThisPath, etc. in this scope

// -- tests --------------------------------------------------------------

assert.strictEqual(pathMatches("/pricing", "/pricing"), true);
assert.strictEqual(pathMatches("/pricing", "/pricing/enterprise"), false);
assert.strictEqual(pathMatches("/blog/*", "/blog/my-post"), true);
assert.strictEqual(pathMatches("/blog/*", "/blogging"), false);
assert.strictEqual(pathMatches("/a.b", "/aXb"), false, "dot must be literal");
console.log("pathMatches: OK");

assert.strictEqual(shouldShowOnThisPath([], "/anything"), true);
assert.strictEqual(shouldShowOnThisPath(undefined, "/anything"), true);
assert.strictEqual(shouldShowOnThisPath(["/pricing"], "/about"), false);
assert.strictEqual(shouldShowOnThisPath(["/pricing", "/blog/*"], "/blog/x"), true);
console.log("shouldShowOnThisPath: OK");

assert.strictEqual(hasAlreadyBeenSeen("widget-1"), false);
markAsSeen("widget-1");
assert.strictEqual(hasAlreadyBeenSeen("widget-1"), true);
assert.strictEqual(hasAlreadyBeenSeen("widget-2"), false, "different widget unaffected");
console.log("seen/unseen tracking: OK");

console.log("\nALL TARGETING LOGIC TESTS PASSED (against live-served widget.js)");
