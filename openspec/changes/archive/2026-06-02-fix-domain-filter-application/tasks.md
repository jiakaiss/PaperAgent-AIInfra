## 1. Reproduce and locate filter bug

- [x] 1.1 Inspect current `preferences.js` and `app.js` URL-building logic for `sub_domain` handling
- [x] 1.2 Reproduce server-side filtering via `/_paper_list?sub_domain=<tag>` using tests or curl
- [x] 1.3 Reproduce client-side behavior for chip click / checkbox change in JS tests or browser flow

## 2. Fix client-side preference and URL behavior

- [x] 2.1 Ensure selecting a chip or checkbox switches mode to `custom`
- [x] 2.2 Ensure paper-list HTMX URL includes repeated `sub_domain` params when mode is `custom`
- [x] 2.3 Ensure search (`q`), time range (`since`), and pagination are preserved when domain filters change
- [x] 2.4 Ensure custom mode with zero selected domains shows empty-state message instead of all papers
- [x] 2.5 Ensure chip, checkbox, and mode radio visuals stay synchronized after each mutation

## 3. Verify server-side filtering behavior

- [x] 3.1 Add or update tests for `/_paper_list?sub_domain=quantization` excluding unrelated papers
- [x] 3.2 Add or update tests for repeated `sub_domain` params using OR semantics
- [x] 3.3 Add or update tests for combined `sub_domain` + `q` + `since` filtering
- [x] 3.4 Ensure unknown sub-domain params are ignored per spec

## 4. Add frontend regression coverage

- [x] 4.1 Add JS test for selecting a chip from `all` mode switching to `custom`
- [x] 4.2 Add JS test for generated URL including selected sub-domain params
- [x] 4.3 Add JS test for custom mode with empty sub-domain selection rendering empty state
- [x] 4.4 Add JS test for preserving search/time filters during domain changes

## 5. Final verification

- [x] 5.1 Run JS tests for preferences behavior
- [x] 5.2 Run Python web browsing/storage tests
- [x] 5.3 Run full test suite
- [x] 5.4 Manually verify in browser: select one domain and confirm paper list only shows matching tags
