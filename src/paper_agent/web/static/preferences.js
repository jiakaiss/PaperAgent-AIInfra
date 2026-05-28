/**
 * Paper Agent client-side preferences module.
 *
 * Stores preferences in localStorage under the key "paper_agent_prefs".
 * Shape: { mode: "all" | "custom", subDomains: string[] }
 *
 * Exposes a global `PaperAgentPrefs` object used by app.js and templates.
 */
(function () {
    "use strict";

    const STORAGE_KEY = "paper_agent_prefs";
    const DEFAULT_PREFS = { mode: "all", subDomains: [] };

    /** Read the list of valid sub-domain keys from the server-injected context. */
    function getValidSubDomains() {
        const el = document.getElementById("server-context");
        if (!el) return [];
        try {
            const ctx = JSON.parse(el.textContent);
            return Array.isArray(ctx.allSubDomains) ? ctx.allSubDomains : [];
        } catch {
            return [];
        }
    }

    /** Return current prefs, falling back to defaults on missing/corrupt data. */
    function getPrefs() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return { ...DEFAULT_PREFS, subDomains: [] };
            const parsed = JSON.parse(raw);
            if (typeof parsed !== "object" || parsed === null) {
                return _resetToDefaults();
            }
            const mode = parsed.mode === "custom" ? "custom" : "all";
            const valid = new Set(getValidSubDomains());
            const subDomains = Array.isArray(parsed.subDomains)
                ? parsed.subDomains.filter((t) => valid.has(t))
                : [];
            return { mode, subDomains };
        } catch {
            return _resetToDefaults();
        }
    }

    function _resetToDefaults() {
        const prefs = { ...DEFAULT_PREFS, subDomains: [] };
        _persist(prefs);
        return prefs;
    }

    function _persist(prefs) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch {
            // localStorage full or blocked — silently ignore
        }
    }

    /** Update the mode radio buttons to reflect the given mode. */
    function _syncModeRadios(mode) {
        const allRadio = document.getElementById("mode-all");
        const customRadio = document.getElementById("mode-custom");
        if (allRadio) allRadio.checked = mode === "all";
        if (customRadio) customRadio.checked = mode === "custom";
    }

    /** Update the preferences-panel checkboxes to reflect the given sub-domains. */
    function _syncCheckboxes(subDomains) {
        const set = new Set(subDomains);
        document.querySelectorAll('input[name="sub_domain_pref"]').forEach(function (cb) {
            cb.checked = set.has(cb.value);
        });
    }

    /** Update every chip's `chip-active` class to reflect the given sub-domains. */
    function _syncChips(subDomains) {
        const set = new Set(subDomains);
        document.querySelectorAll(".chip-filterable").forEach(function (chip) {
            const tag = chip.getAttribute("data-tag");
            if (set.has(tag)) {
                chip.classList.add("chip-active");
            } else {
                chip.classList.remove("chip-active");
            }
        });
    }

    /**
     * Synchronize every UI surface (mode radios, sub-domain checkboxes, chip
     * filter) with the given prefs. Call this after every mutation so the DOM
     * always reflects localStorage.
     */
    function syncAllUI(prefs) {
        const p = prefs || getPrefs();
        _syncModeRadios(p.mode);
        _syncCheckboxes(p.subDomains);
        _syncChips(p.subDomains);
    }

    /** Set mode ("all" or "custom"), persist, and refresh the paper list. */
    function setMode(mode) {
        const prefs = getPrefs();
        if (mode !== "all" && mode !== "custom") return;
        prefs.mode = mode;
        _persist(prefs);
        syncAllUI(prefs);
        refreshPaperList();
    }

    /** Replace the sub-domain selection, persist, and refresh. */
    function setSubDomains(tags) {
        const prefs = getPrefs();
        const valid = new Set(getValidSubDomains());
        prefs.subDomains = (Array.isArray(tags) ? tags : []).filter((t) => valid.has(t));
        _persist(prefs);
        syncAllUI(prefs);
        refreshPaperList();
    }

    /** Toggle a single sub-domain tag in/out of the selection. */
    function toggleSubDomain(tag) {
        const prefs = getPrefs();
        const idx = prefs.subDomains.indexOf(tag);
        if (idx >= 0) {
            prefs.subDomains.splice(idx, 1);
        } else {
            prefs.subDomains.push(tag);
        }
        _persist(prefs);
        syncAllUI(prefs);
        refreshPaperList();
    }

    /** Toggle a chip on the main page — same as toggleSubDomain. */
    function toggleChip(tag) {
        toggleSubDomain(tag);
    }

    /**
     * Build a query string from the current prefs and the given search/page.
     * When mode is "custom", sub-domain tags are included as repeated `sub_domain` params.
     */
    function buildQueryString(opts) {
        opts = opts || {};
        const prefs = getPrefs();
        const params = new URLSearchParams();

        // Only pass mode if it was explicitly overridden (URL override flow)
        if (opts.mode) params.set("mode", opts.mode);

        if (prefs.mode === "custom" && prefs.subDomains.length > 0) {
            prefs.subDomains.forEach((t) => params.append("sub_domain", t));
        }
        if (opts.search) params.set("q", opts.search);
        if (opts.page && opts.page > 1) params.set("page", String(opts.page));
        const qs = params.toString();
        return qs ? "?" + qs : "";
    }

    /** Re-issue the HTMX request against /_paper_list with current prefs. */
    function refreshPaperList() {
        const container = document.getElementById("paper-list-container");
        if (!container) return;
        const url = "/_paper_list" + buildQueryString({ search: _currentSearch() });
        // Use htmx.ajax if available, else fall back to fetch
        if (typeof htmx !== "undefined" && htmx.ajax) {
            htmx.ajax("GET", url, { target: "#paper-list-container", swap: "innerHTML" });
        } else {
            fetch(url)
                .then((r) => r.text())
                .then((html) => {
                    container.innerHTML = html;
                });
        }
        _syncUrlBar();
    }

    /** Read the current search term from the search input. */
    function _currentSearch() {
        const input = document.querySelector(".search-input");
        return input ? input.value.trim() : "";
    }

    /** Update the URL bar to reflect current prefs (replaceState, no reload). */
    function _syncUrlBar() {
        const qs = buildQueryString({ search: _currentSearch() });
        const newUrl = "/" + qs;
        if (window.history && window.history.replaceState) {
            window.history.replaceState(null, "", newUrl);
        }
    }

    /**
     * Apply a URL ?mode= override: write it to localStorage, strip from URL.
     * Called on page load when the URL contains ?mode=all or ?mode=custom.
     */
    function applyPrefsToUrl() {
        const params = new URLSearchParams(window.location.search);
        const urlMode = params.get("mode");
        if (urlMode === "all" || urlMode === "custom") {
            const prefs = getPrefs();
            prefs.mode = urlMode;
            _persist(prefs);
            // Strip ?mode= from URL
            params.delete("mode");
            const qs = params.toString();
            const cleanUrl = "/" + (qs ? "?" + qs : "");
            window.history.replaceState(null, "", cleanUrl);
        }
    }

    /** Clear all preferences and reload the page. */
    function clearAndReload() {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch {
            // ignore
        }
        window.location.href = "/";
    }

    // Expose global API
    window.PaperAgentPrefs = {
        getPrefs,
        setMode,
        setSubDomains,
        toggleSubDomain,
        toggleChip,
        buildQueryString,
        refreshPaperList,
        applyPrefsToUrl,
        clearAndReload,
        getValidSubDomains,
        syncAllUI,
    };
})();
