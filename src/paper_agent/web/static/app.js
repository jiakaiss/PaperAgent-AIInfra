/**
 * Paper Agent app bootstrap.
 *
 * Runs on DOMContentLoaded:
 *  1. Apply URL mode override (?mode=...) to localStorage
 *  2. Sync all UI surfaces (radios, checkboxes, chips) to current prefs
 *  3. Wire up event listeners (mode toggle, checkboxes, chips, preferences panel)
 *  4. Trigger the initial HTMX load of /_paper_list
 */
document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    // 1. Apply any URL ?mode= override
    PaperAgentPrefs.applyPrefsToUrl();

    // 2. Sync all UI surfaces to prefs (single entry point)
    PaperAgentPrefs.syncAllUI();

    // 3. Wire event listeners

    // Mode toggle radios — setMode() internally calls syncAllUI + refreshPaperList
    document.querySelectorAll('input[name="mode"]').forEach(function (radio) {
        radio.addEventListener("change", function () {
            PaperAgentPrefs.setMode(this.value);
        });
    });

    // Sub-domain checkboxes — setSubDomains() internally calls syncAllUI + refreshPaperList
    document.querySelectorAll('input[name="sub_domain_pref"]').forEach(function (cb) {
        cb.addEventListener("change", function () {
            const checked = Array.from(
                document.querySelectorAll('input[name="sub_domain_pref"]:checked')
            ).map(function (el) {
                return el.value;
            });
            PaperAgentPrefs.setSubDomains(checked);
        });
    });

    // Preferences panel toggle
    const panel = document.getElementById("preferences-panel");
    const toggleBtn = document.getElementById("preferences-toggle");
    const closeBtn = document.getElementById("preferences-close");
    if (panel && toggleBtn) {
        toggleBtn.addEventListener("click", function () {
            panel.hidden = !panel.hidden;
        });
    }
    if (panel && closeBtn) {
        closeBtn.addEventListener("click", function () {
            panel.hidden = true;
        });
    }

    // Search form: intercept submit to use HTMX with prefs
    const searchForm = document.querySelector(".search-form");
    if (searchForm) {
        searchForm.addEventListener("submit", function (e) {
            e.preventDefault();
            PaperAgentPrefs.refreshPaperList();
        });
    }

    // 4. Trigger initial HTMX load
    const container = document.getElementById("paper-list-container");
    if (container && typeof htmx !== "undefined") {
        const url = "/_paper_list" + PaperAgentPrefs.buildQueryString();
        htmx.ajax("GET", url, { target: "#paper-list-container", swap: "innerHTML" });
    }
});
