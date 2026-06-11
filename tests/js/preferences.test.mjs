/**
 * Unit tests for preferences.js using Node's built-in test runner.
 *
 * Since preferences.js is written for browsers, this harness mocks
 * `document`, `localStorage`, `window`, and `URLSearchParams` just
 * enough to exercise the sync paths.
 *
 * Run with:  node --test tests/js/preferences.test.mjs
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PREFS_SRC = readFileSync(
    join(__dirname, "..", "..", "src", "paper_agent", "web", "static", "preferences.js"),
    "utf-8",
);

/** Build a fake DOM with N chip elements and 15 checkboxes, then eval preferences.js. */
function makeEnv(opts = {}) {
    const {
        initialPrefs = null,
        validTags = ["quantization", "moe", "compiler"],
        searchValue = "",
        activeSince = "",
    } = opts;

    const store = new Map();
    if (initialPrefs) {
        store.set("paper_agent_prefs", JSON.stringify(initialPrefs));
    }

    const localStorage = {
        getItem: (k) => (store.has(k) ? store.get(k) : null),
        setItem: (k, v) => {
            store.set(k, v);
        },
        removeItem: (k) => {
            store.delete(k);
        },
        _store: store,
    };

    // Mock elements: classList with add/remove tracking
    function makeElement(tag, attrs = {}) {
        const el = {
            tag,
            id: attrs.id || null,
            name: attrs.name || null,
            value: attrs.value ?? null,
            hidden: false,
            checked: attrs.checked || false,
            innerHTML: attrs.innerHTML || "",
            textContent: attrs.textContent || "",
            classList: {
                _classes: new Set(attrs.classes || []),
                add(c) {
                    this._classes.add(c);
                },
                remove(c) {
                    this._classes.delete(c);
                },
                has(c) {
                    return this._classes.has(c);
                },
            },
            getAttribute(k) {
                if (k === "data-tag") return attrs["data-tag"] || null;
                return attrs[k] || null;
            },
            setAttribute(k, v) {
                attrs[k] = v;
            },
            _listeners: {},
            addEventListener(type, fn) {
                this._listeners[type] = this._listeners[type] || [];
                this._listeners[type].push(fn);
            },
        };
        return el;
    }

    // Build elements
    const serverContextEl = makeElement("script", {
        id: "server-context",
        textContent: JSON.stringify({ allSubDomains: validTags }),
    });
    const modeAll = makeElement("input", { id: "mode-all", name: "mode", value: "all" });
    const modeCustom = makeElement("input", {
        id: "mode-custom",
        name: "mode",
        value: "custom",
    });
    const checkboxes = validTags.map((t) =>
        makeElement("input", { name: "sub_domain_pref", value: t })
    );
    // Two chips for quantization (regression test for "all chips for the same tag toggle together")
    const chips = [
        makeElement("button", { "data-tag": "quantization", classes: ["chip-filterable"] }),
        makeElement("button", { "data-tag": "moe", classes: ["chip-filterable"] }),
        makeElement("button", { "data-tag": "compiler", classes: ["chip-filterable"] }),
        makeElement("button", { "data-tag": "quantization", classes: ["chip-filterable"] }),
    ];

    const subDomainToggle = makeElement("button", { id: "sub-domain-toggle", textContent: "全选" });
    const searchInput = makeElement("input", {
        classes: ["search-input"],
        value: searchValue,
    });
    const timeChips = [
        makeElement("button", {
            "data-since": "",
            classes: ["chip-time", activeSince === "" ? "chip-active" : ""].filter(Boolean),
        }),
        makeElement("button", {
            "data-since": "1m",
            classes: ["chip-time", activeSince === "1m" ? "chip-active" : ""].filter(Boolean),
        }),
    ];

    const elementsById = {
        "server-context": serverContextEl,
        "mode-all": modeAll,
        "mode-custom": modeCustom,
        "sub-domain-toggle": subDomainToggle,
        "preferences-panel": makeElement("aside", { id: "preferences-panel" }),
        "preferences-toggle": makeElement("button", { id: "preferences-toggle" }),
        "preferences-close": makeElement("button", { id: "preferences-close" }),
        "paper-list-container": makeElement("div", { id: "paper-list-container" }),
    };

    const allElements = [
        serverContextEl,
        modeAll,
        modeCustom,
        searchInput,
        ...checkboxes,
        ...chips,
        ...timeChips,
        ...Object.values(elementsById),
    ];

    const document = {
        getElementById: (id) => elementsById[id] || null,
        querySelectorAll: (sel) => {
            if (sel === ".chip-filterable") return chips;
            if (sel === 'input[name="sub_domain_pref"]') return checkboxes;
            if (sel === 'input[name="sub_domain_pref"]:checked')
                return checkboxes.filter((c) => c.checked);
            if (sel === 'input[name="mode"]') return [modeAll, modeCustom];
            if (sel === ".search-input") return [searchInput];
            if (sel === ".chip-time") return timeChips;
            return [];
        },
        querySelector: (sel) => {
            if (sel === ".search-input") return searchInput;
            if (sel === ".chip-time.chip-active") {
                return timeChips.find((chip) => chip.classList.has("chip-active")) || null;
            }
            return null;
        },
        addEventListener: () => {},
    };

    const window = {
        location: { search: "", href: "/" },
        history: { replaceState: () => {} },
        PaperAgentPrefs: null,
    };

    // Mock htmx so refreshPaperList() records generated URLs instead of fetching.
    const htmxCalls = [];
    const htmx = {
        ajax: (method, url, options) => {
            htmxCalls.push({ method, url, options });
        },
    };

    // Expose globals and eval the module
    const fakeGlobal = {
        window,
        document,
        localStorage,
        URLSearchParams: globalThis.URLSearchParams,
        Set: globalThis.Set,
        Array: globalThis.Array,
        JSON: globalThis.JSON,
        Object: globalThis.Object,
        fetch: async () => ({ text: async () => "" }),
        htmx,
        console: globalThis.console,
    };
    fakeGlobal.globalThis = fakeGlobal;

    // Run preferences.js in this fake scope
    const wrappedSrc = `(function(window, document, localStorage, URLSearchParams, Set, Array, JSON, Object, fetch, htmx, console, globalThis) { ${PREFS_SRC} })(window, document, localStorage, URLSearchParams, Set, Array, JSON, Object, fetch, htmx, console, globalThis);`;
    // eslint-disable-next-line no-eval
    eval(wrappedSrc);

    return {
        PaperAgentPrefs: window.PaperAgentPrefs,
        elements: {
            modeAll,
            modeCustom,
            checkboxes,
            chips,
            serverContextEl,
            subDomainToggle,
            searchInput,
            timeChips,
            paperListContainer: elementsById["paper-list-container"],
        },
        localStorage,
        store,
        htmxCalls,
    };
}

test("syncAllUI adds chip-active to selected chips and removes from others", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: ["quantization"] } });
    env.PaperAgentPrefs.syncAllUI({ mode: "custom", subDomains: ["quantization"] });

    // quantization chips (both of them) should be active
    const qChips = env.elements.chips.filter((c) => c.getAttribute("data-tag") === "quantization");
    assert.equal(qChips.length, 2);
    for (const c of qChips) {
        assert.equal(c.classList.has("chip-active"), true, "quantization chip should be active");
    }
    // moe and compiler chips should NOT be active
    const moeChip = env.elements.chips.find((c) => c.getAttribute("data-tag") === "moe");
    assert.equal(moeChip.classList.has("chip-active"), false, "moe chip should NOT be active");
});

test("syncAllUI syncs checkboxes with subDomains", () => {
    const env = makeEnv();
    env.PaperAgentPrefs.syncAllUI({ mode: "custom", subDomains: ["quantization", "moe"] });

    const qCb = env.elements.checkboxes.find((c) => c.value === "quantization");
    const mCb = env.elements.checkboxes.find((c) => c.value === "moe");
    const cCb = env.elements.checkboxes.find((c) => c.value === "compiler");
    assert.equal(qCb.checked, true);
    assert.equal(mCb.checked, true);
    assert.equal(cCb.checked, false);
});

test("syncAllUI syncs mode radio buttons", () => {
    const env = makeEnv();

    env.PaperAgentPrefs.syncAllUI({ mode: "custom", subDomains: [] });
    assert.equal(env.elements.modeAll.checked, false);
    assert.equal(env.elements.modeCustom.checked, true);

    env.PaperAgentPrefs.syncAllUI({ mode: "all", subDomains: [] });
    assert.equal(env.elements.modeAll.checked, true);
    assert.equal(env.elements.modeCustom.checked, false);
});

test("toggleSubDomain flips chip-active on AND off", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: [] } });
    const qChip = env.elements.chips[0];

    // Initial: no active class
    assert.equal(qChip.classList.has("chip-active"), false);

    // Click to activate
    env.PaperAgentPrefs.toggleSubDomain("quantization");
    assert.equal(qChip.classList.has("chip-active"), true, "chip should be active after toggle-on");

    // Click again to deactivate
    env.PaperAgentPrefs.toggleSubDomain("quantization");
    assert.equal(
        qChip.classList.has("chip-active"),
        false,
        "chip should be inactive after toggle-off"
    );
});

test("toggleSubDomain also flips the matching checkbox", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: [] } });
    const qCb = env.elements.checkboxes.find((c) => c.value === "quantization");

    assert.equal(qCb.checked, false);
    env.PaperAgentPrefs.toggleSubDomain("quantization");
    assert.equal(qCb.checked, true, "checkbox should be checked after toggle-on");
    env.PaperAgentPrefs.toggleSubDomain("quantization");
    assert.equal(qCb.checked, false, "checkbox should be unchecked after toggle-off");
});

test("toggleSubDomain persists to localStorage", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: [] } });

    env.PaperAgentPrefs.toggleSubDomain("quantization");
    const stored = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.deepEqual(stored.subDomains, ["quantization"]);

    env.PaperAgentPrefs.toggleSubDomain("moe");
    const stored2 = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.deepEqual(stored2.subDomains, ["quantization", "moe"]);
});

test("regression: chip click end-to-end (class + checkbox + localStorage)", () => {
    // This is the exact scenario from the bug report:
    // "clicking a chip updates the paper count but doesn't change its color"
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: [] } });

    const qChip = env.elements.chips[0]; // quantization chip
    const qCb = env.elements.checkboxes.find((c) => c.value === "quantization");

    // Pre-state: chip inactive, checkbox unchecked, subDomains empty
    assert.equal(qChip.classList.has("chip-active"), false);
    assert.equal(qCb.checked, false);

    // Act: click the chip (calls toggleChip → toggleSubDomain → syncAllUI)
    env.PaperAgentPrefs.toggleChip("quantization");

    // Post-state: chip active, checkbox checked, localStorage has the tag
    assert.equal(qChip.classList.has("chip-active"), true, "chip should turn blue");
    assert.equal(qCb.checked, true, "preferences-panel checkbox should check");
    const stored = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.deepEqual(stored.subDomains, ["quantization"]);
});

test("all chips for the same tag toggle together", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: [] } });

    // Click the FIRST quantization chip
    env.PaperAgentPrefs.toggleChip("quantization");

    // BOTH quantization chips should now be active
    const qChips = env.elements.chips.filter((c) => c.getAttribute("data-tag") === "quantization");
    assert.equal(qChips.length, 2);
    for (const c of qChips) {
        assert.equal(c.classList.has("chip-active"), true);
    }
});

test("setSince function is exposed in global API", () => {
    const env = makeEnv();
    assert.equal(typeof env.PaperAgentPrefs.setSince, "function");
});

test("toggleAllSubDomains selects all when none selected", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: [] } });
    const allTags = ["quantization", "moe", "compiler"];

    env.PaperAgentPrefs.toggleAllSubDomains();

    // All checkboxes should be checked
    for (const cb of env.elements.checkboxes) {
        assert.equal(cb.checked, true, `checkbox ${cb.value} should be checked`);
    }

    // localStorage should contain all tags
    const stored = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.deepEqual(stored.subDomains.sort(), allTags.sort());

    // Toggle button text should change to "取消全选"
    assert.equal(env.elements.subDomainToggle.textContent, "取消全选");
});

test("toggleAllSubDomains deselects all when all selected", () => {
    const env = makeEnv({
        initialPrefs: { mode: "custom", subDomains: ["quantization", "moe", "compiler"] },
    });

    env.PaperAgentPrefs.toggleAllSubDomains();

    // All checkboxes should be unchecked
    for (const cb of env.elements.checkboxes) {
        assert.equal(cb.checked, false, `checkbox ${cb.value} should be unchecked`);
    }

    // localStorage should have empty subDomains
    const stored = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.deepEqual(stored.subDomains, []);

    // Toggle button text should change to "全选"
    assert.equal(env.elements.subDomainToggle.textContent, "全选");
});

test("toggleAllSubDomains selects all when partially selected", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: ["quantization"] } });
    const allTags = ["quantization", "moe", "compiler"];

    env.PaperAgentPrefs.toggleAllSubDomains();

    // All checkboxes should be checked
    for (const cb of env.elements.checkboxes) {
        assert.equal(cb.checked, true, `checkbox ${cb.value} should be checked`);
    }

    const stored = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.deepEqual(stored.subDomains.sort(), allTags.sort());

    // Toggle button text should change to "取消全选"
    assert.equal(env.elements.subDomainToggle.textContent, "取消全选");
});

test("setSince validates input and accepts valid values", () => {
    const env = makeEnv();

    // Valid values should not throw
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince(""));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("1w"));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("1m"));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("3m"));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("6m"));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("1y"));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("3y"));

    // Invalid value should be ignored (no throw)
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("invalid"));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince("2m"));
    assert.doesNotThrow(() => env.PaperAgentPrefs.setSince(null));
});

test("selecting a chip from all mode switches to custom and filters URL", () => {
    const env = makeEnv({ initialPrefs: { mode: "all", subDomains: [] } });

    env.PaperAgentPrefs.toggleChip("quantization");

    const stored = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.equal(stored.mode, "custom");
    assert.deepEqual(stored.subDomains, ["quantization"]);
    assert.equal(env.elements.modeCustom.checked, true);
    assert.equal(env.htmxCalls.at(-1).url, "/_paper_list?sub_domain=quantization");
});

test("setSubDomains switches to custom and generated URL includes repeated sub_domain params", () => {
    const env = makeEnv({ initialPrefs: { mode: "all", subDomains: [] } });

    env.PaperAgentPrefs.setSubDomains(["quantization", "moe"]);

    const stored = JSON.parse(env.store.get("paper_agent_prefs"));
    assert.equal(stored.mode, "custom");
    const url = env.htmxCalls.at(-1).url;
    assert.equal(url, "/_paper_list?sub_domain=quantization&sub_domain=moe");
});

test("custom mode with empty subDomains renders empty state instead of fetching all", () => {
    const env = makeEnv({ initialPrefs: { mode: "custom", subDomains: ["quantization"] } });

    env.PaperAgentPrefs.setSubDomains([]);

    assert.equal(env.htmxCalls.length, 0);
    assert.match(env.elements.paperListContainer.innerHTML, /Select at least one sub-domain/);
});

test("domain changes preserve search and time filters", () => {
    const env = makeEnv({
        initialPrefs: { mode: "all", subDomains: [] },
        searchValue: "llm",
        activeSince: "1m",
    });

    env.PaperAgentPrefs.toggleChip("quantization");

    const url = env.htmxCalls.at(-1).url;
    assert.equal(url, "/_paper_list?sub_domain=quantization&q=llm&since=1m");
});
