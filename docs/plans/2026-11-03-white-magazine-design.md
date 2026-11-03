# White magazine redesign

Approved reference: white-tech-magazine.html in this chat, with a white background, charcoal typography, forest green accents, thin neutral rules, and modest corners. Keep the static GitHub Pages architecture, original article/report content, multilingual reading, search, category/month filters, pagination, and historical URLs.

# Implementation Plan

**Goal:** Apply the approved magazine style consistently to news, reports, and article reading.
**Architecture:** Keep presentation in assets/site.css and generated markup in site_ui.py. Extend the existing report scanner to include report.html files, generate reports.html from real report metadata, preserve smartphone.html as an alias, and add shared presentation to report pages without rewriting their bodies. Maintain the existing news reader DOM contracts and language state.
**Tech Stack:** Python standard library, static HTML/CSS, vanilla JavaScript.

1. Add regression coverage for shared navigation, report discovery, report-specific search/page metadata, and idempotent article/report upgrades. Run tests to confirm expected failures.
2. Implement shared magazine masthead and white design tokens; use a three-column editorial grid with the existing images and mobile list layout. Generate the report index from real report files; use route-specific copy while keeping filtering and language behavior.
3. Migrate existing article/report presentation and future templates. Preserve historical URLs and exact article/report content. Add shared navigation without removing reading controls.
4. Rebuild. Run Python/Node regression suites and generated link/content checks. Inspect desktop/mobile using a local preview if available. Review the final changes and document any validation limitations.

Do not publish, push, migrate hosting, or change crawler/translation behavior as part of this change.

## Category simplification

The user approved merging camera and phone into the virtual `mobile` (모바일·이미징) filter and removing the generic tech tab. Preserve stored source categories, all/search coverage, and old camera/phone URLs. Apply merged display labels in all four languages and article navigation. Added tests cover union filtering and historical URL compatibility.


## Optional dark appearance

The user requested a dark mode option while retaining the white default. Add a shared header toggle and a small synchronous theme script to restore the saved choice before body paint. Use charcoal green paper, lighter green accents, and semantic aliases covering legacy article and report styles. Persist `aisitei_theme` locally, synchronize other tabs, and preserve functionality if storage is blocked. Keep original images and article/report content unchanged. Verify toggle state, page navigation, storage failures, responsive header, text/table contrast, and future templates. Publish after validation under the existing deployment authorization.
