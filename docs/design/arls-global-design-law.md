# ARLS Global Design Law

## Purpose

This document is the canonical reusable reference for ARLS visual work.

Binding execution authority still lives in:

- [prd-arls-global-design-box-in-box-reset-overlay.md](/Users/mark/Desktop/rg-arls-dev/.omx/plans/prd-arls-global-design-box-in-box-reset-overlay.md)
- [test-spec-arls-global-design-box-in-box-reset-overlay.md](/Users/mark/Desktop/rg-arls-dev/.omx/plans/test-spec-arls-global-design-box-in-box-reset-overlay.md)

If this document and the overlay artifacts diverge, the overlay artifacts win.

## Default plane grammar

For ARLS operational surfaces:

1. one outer background plane
2. one white primary sheet
3. same-plane subdivision inside the sheet
4. divider rhythm instead of inset panels by default

Only these surface classes may intentionally break the default:

- document-editing surfaces
- form wizards
- detail inspectors

## Do not do

Unless a Shople reference explicitly shows otherwise, do not:

1. create `box-in-box`
2. mix multiple plane grammars inside one workspace
3. use U-shaped tabs or U-bookmark shells
4. use orange or tinted empty-state cards
5. use decorative title-left icons
6. solve sparse composition by adding inner cards or inset panels
7. split a card's primary ownership between title row and subsection row
8. vary icon alignment arbitrarily inside the same grammar family

## Must do

Use these tools to create hierarchy:

- spacing
- divider rhythm
- type scale
- alignment
- one-time accent use

Do not use extra nested cards as a substitute for hierarchy.

## Header and action grammar

1. title and primary action stay on the same header row
2. subsection actions are allowed only for a real independent workspace
3. single-destination entry belongs to row/card/module/chevron, not redundant `보기/열기`

## Tab grammar

### Row 1

- text + straight underline only
- even sibling spacing
- no pill fallback
- no U-shaped shells

### Row 2

- straight bookmark/book-tab only
- straight planar top edge
- no curved U-shell
- no pillized metric tabs

## Empty-state grammar

Default empty state:

1. sits on the current rear/background plane
2. uses icon + title + optional short copy only
3. does not create a framed mini-card by default

Alignment:

- standalone empty-state icon: centered with copy
- title-row icon: banned unless semantically necessary
- mixed left/center alignment across sibling empty states: fail

## Icon grammar

1. decorative icons are banned by default
2. icons may appear only when they carry real category/state meaning
3. similar components must share one alignment rule
4. omission is better than a placeholder icon

## Review checklist

Before any UI pass is approved:

1. What is the active plane grammar?
2. Is an exception class used?
3. Did any nested surface appear?
4. Did any empty state become a box?
5. Did any title icon reappear without semantic need?
6. Did any primary action drift off the header row?
7. Did row-1 or row-2 tabs revert to pills or U-shells?
