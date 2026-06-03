## Context

Paper browsing currently relies on a split responsibility:

- Server routes (`/`, `/_paper_list`) are stateless and filter only from query parameters.
- Browser `localStorage` stores user preferences (`mode`, `subDomains`).
- Client JS converts preferences into HTMX request URLs.

The reported bug indicates this chain is broken: users choose interested domains but the list still shows all papers. The likely failure modes are:

1. Client remains in `mode=all`, so selected `subDomains` are ignored.
2. Chip/checkbox click updates visuals but not the actual HTMX URL.
3. `/_paper_list` request omits `sub_domain` parameters.
4. Server receives parameters but empty/custom mode semantics fall back to all.

## Goals / Non-Goals

**Goals:**
- Ensure selecting sub-domain chips or preference checkboxes updates `localStorage` and re-fetches filtered results.
- Ensure selected domains are represented as repeated `sub_domain=<tag>` query parameters on HTMX requests.
- Ensure custom mode with no selected sub-domains shows an empty state instead of all papers.
- Add regression tests for JS URL construction and server-side fragment filtering.

**Non-Goals:**
- Do not add server-side user sessions or authenticated preferences.
- Do not change the paper storage schema.
- Do not change the scoring/tag taxonomy.
- Do not redesign the filter UI beyond behavior fixes.

## Decisions

### 1. Client-side mode must control whether subDomains apply

When `paper_agent_prefs.mode === "all"`, requests intentionally omit `sub_domain` and show all papers. When the user explicitly selects a domain via chip or checkbox, the app should switch to `custom` mode so the selected domains take effect immediately.

Rationale: selecting a chip is a direct filtering action; keeping `mode=all` while showing active chips is inconsistent.

### 2. URL construction is the source of truth for HTMX filtering

All paper list refreshes should go through one helper that builds `/_paper_list` URLs from:

- `localStorage.mode`
- `localStorage.subDomains`
- current search query
- current time range
- requested page

The helper must append one `sub_domain` param per selected tag only when mode is `custom`.

### 3. Custom mode with empty selected domains should not fetch all papers

If mode is `custom` and `subDomains` is empty, the UI should display a client-side or server-rendered empty state saying that at least one domain must be selected. It must not omit `sub_domain` params and accidentally display all papers.

Implementation options:
- Client-side: render an empty state without sending HTMX request.
- Server-side: send a sentinel such as `empty_custom=1`.

Preferred: client-side empty state to avoid unnecessary backend changes.

### 4. Server route tests remain authoritative for query filtering

Even if the root cause is frontend, `/_paper_list?sub_domain=quantization` must be covered by tests and must never return unrelated papers. This guards future regressions.

## Risks / Trade-offs

- **[Risk] Search/time filters get dropped when re-fetching after domain changes** → Centralize URL building and test combined filters.
- **[Risk] Browser localStorage has stale `mode=all` from previous visits** → Selecting any domain switches mode to `custom`.
- **[Risk] Empty custom mode behavior surprises users** → Show explicit empty message: "Select at least one sub-domain in preferences".
- **[Trade-off] Stateless server remains unaware of browser mode** → Keeps current architecture simple; frontend owns preference interpretation.
