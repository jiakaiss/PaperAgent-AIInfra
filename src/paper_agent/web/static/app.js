/**
 * Paper Agent app bootstrap.
 *
 * Runs on DOMContentLoaded:
 *  1. Apply URL mode override (?mode=...) to localStorage
 *  2. Sync preferences panel UI to current localStorage prefs
 *  3. Wire up event listeners (mode toggle, checkboxes, chips, preferences panel)
 *  4. Trigger the initial HTMX load of /_paper_list
 */
document.addEventListener("DOMContentLoaded", function () {
    "use strict";

    // 1. Apply any URL ?mode= override
    PaperAgentPrefs.applyPrefsToUrl();

    // 2. Sync panel to prefs
    const prefs = PaperAgentPrefs.getPrefs();
    _syncModeRadios(prefs.mode);
    _syncCheckboxes(prefs.subDomains);
    _syncChips(prefs.subDomains);

    // 3. Wire event listeners

    // Mode toggle radios
    document.querySelectorAll('input[name="mode"]').forEach(function (radio) {
        radio.addEventListener("change", function () {
            PaperAgentPrefs.setMode(this.value);
            _syncChips(PaperAgentPrefs.getPrefs().subDomains);
        });
    });

    // Sub-domain checkboxes
    document.querySelectorAll('input[name="sub_domain_pref"]').forEach(function (cb) {
        cb.addEventListener("change", function () {
            const checked = Array.from(
                document.querySelectorAll('input[name="sub_domain_pref"]:checked')
            ).map(function (el) {
                return el.value;
            });
            PaperAgentPrefs.setSubDomains(checked);
            _syncChips(checked);
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

function _syncModeRadios(mode) {
    const allRadio = document.getElementById("mode-all");
    const customRadio = document.getElementById("mode-custom");
    if (allRadio) allRadio.checked = mode === "all";
    if (customRadio) customRadio.checked = mode === "custom";
}

function _syncCheckboxes(subDomains) {
    const set = new Set(subDomains);
    document.querySelectorAll('input[name="sub_domain_pref"]').forEach(function (cb) {
        cb.checked = set.has(cb.value);
    });
}

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
