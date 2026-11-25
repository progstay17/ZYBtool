# ZYBTool — Visual Design System

**Direction:** Cyber Operations / Field Data Verification  
**Mood:** black graphite, restrained signal-green, precise instrumentation, industrial software.  
**Purpose:** desktop application for inspecting, verifying, grouping, reporting and safely preparing camera recordings for OSS.  
**Status:** Settings desktop slice implemented as the first UI increment; other screens remain design-only and are not represented as available.

## 1. Design intent

ZYBTool should feel like serious operations software used by a technical team handling valuable field recordings—not a game HUD, hacker movie prop, crypto dashboard or generic AI-generated admin template.

Priorities, in order:
1. What data is being processed?
2. Is the evidence trustworthy?
3. What needs operator attention?
4. What action is safe next?
5. Has output or upload actually completed?

Keep the interface dark, calm, information-dense and readable. Green is a functional signal, not wallpaper. Use strong alignment, crisp separators, compact labels and useful tables. No fake telemetry, invented metrics or decorative charts.

## 2. Art direction

### Color tokens

| Token | Hex | Use |
|---|---|---|
| canvas | #080D0B | Main background |
| surface-1 | #0E1511 | Sidebar and primary panels |
| surface-2 | #131D17 | Cards, table headers, toolbars |
| surface-3 | #19251D | Hover and selected surfaces |
| line | #26372C | Borders and separators |
| text-primary | #E8F0E9 | Main text |
| text-secondary | #A0B0A4 | Supporting text |
| text-muted | #718176 | Quiet labels |
| signal-green | #A3F36B | Primary action, verified state, focus |
| signal-green-deep | #5DBB45 | Secondary accent |
| warning | #F2B84B | Warnings |
| danger | #FF6B68 | Invalid, destructive or failed |
| info | #77B9D8 | Informational state |

Reserve the brightest green for primary action, keyboard focus, selected navigation and verified evidence. Do not make every button green. Avoid large neon glows.

### Typography

- UI: Inter or system sans-serif fallback.
- Technical values, IDs, paths, hashes and timestamps: IBM Plex Mono or system monospace.
- Tabular numerals for durations, sizes and counters.
- Suggested scale: 12 px metadata, 13–14 px dense table text, 14–15 px body, 18–20 px section titles, 24–28 px page title.
- No futuristic display fonts or all-caps paragraphs.

### Shape and effects

- Panels: 8–10 px radius; controls: 6–8 px.
- Thin solid borders; subtle shadows only for floating menus/dialogs.
- Avoid glassmorphism, blurred translucent panels, giant gradients, scanlines, random grid backgrounds, excessive pills and glow on every element.
- Use consistent 16–18 px line icons; pair unfamiliar icons with labels.

## 3. Application shell

Desktop-first for Windows at 1280×800 and 1440×900; remain usable at 1024×700.

- Left navigation: 220–240 px.
- Top bar: 52–58 px.
- Main content: flexible, max-width about 1500 px, 24 px page padding.
- Bottom activity strip appears only while a real background job is running.

Navigation:
1. Overview
2. Verify Recordings
3. Review Queue
4. Output & Reports
5. OSS Transfers
6. Activity Log
7. Settings

Use explicit labels. Active navigation gets a muted green surface and a narrow green indicator—not a glowing block. Page headers contain title, one-line purpose, breadcrumb where needed and one clear primary action.

## 4. Key screens

### Overview

This is an operational dashboard, not a marketing dashboard.

- Primary action: New verification.
- Compact real metrics: folders discovered, recordings verified, attention required, upload status. Use actual persisted job data; show an em dash if unavailable.
- Recent jobs table: source, date, recordings, result, output destination, last activity.
- Attention queue: actionable items such as AMBIGUOUS, INCOMPLETE, METADATA_MISMATCH and failed transfers.
- Empty state explains how to start. Never show fabricated sample counts.

Prefer counts and tables over donut charts or decorative graphs.

### Verify Recordings

Use a clear workflow:
Source → Discover → Verify → Review → Prepare output.

- Source: choose folder, show exact path, available disk space and read-only source notice.
- Discover: show final/live/partial folders and file counts. Include hidden .live_* folders.
- Verify: show actual progress for metadata, video timeline, QR, grouping and hashes.
- Review: list grouped recordings and issues; never hide warnings behind one green success state.
- Prepare output: preview exact folder tree and destination before copying.

Allow safe navigation between stages without losing completed results. Pause/cancel only where technically safe.

### Verification results

The results table is the core screen. Columns:
Status, operational identity/recorder, camera device, session ID, segments, actual duration, QR evidence, metadata consistency, integrity, action.

Status must include text and icon; color is supplementary:
- VERIFIED: green + check.
- VERIFIED_WITH_WARNING: amber.
- METADATA_ONLY: neutral blue/grey; never green.
- AMBIGUOUS, INCOMPLETE, METADATA_MISMATCH: amber.
- INVALID_SIGNATURE, UNKNOWN_DEVICE, REPLAY_DETECTED, CORRUPTED: red.

Row detail shows evidence summary, trust level, QR/device evidence, session facts, segment timeline, actual-vs-claimed duration, SHA-256 status and exact reasons for warnings/rejections. Never reduce trust to an unexplained percentage.

### Review Queue

A focused worklist for AMBIGUOUS, QR_MISSING, INCOMPLETE, METADATA_MISMATCH, CORRUPTED and naming conflicts. Every item explains:
- What is wrong.
- Which evidence supports the finding.
- What operator decision is required.

No one-click “fix all” for evidence conflicts.

### Output & Reports

- Show exact destination and readable output tree preview.
- Preserve original recording_primary_* directory names and all contents.
- Distinguish source folders from newly created operational parent folders.
- Default is copy, never silently move or rename source data.
- Show copy progress, verification result and skipped items.
- Supervisor summary first; expandable technical evidence second.

### OSS Transfers

Treat upload as a separate controlled stage:
- Show bucket, endpoint and prefix before starting.
- Show object count, bytes, measured transfer rate, completed/remaining and retry state only when available.
- Make resumable status explicit.
- Upload is not complete until remote size/checksum validation succeeds.
- Existing-object conflict stops for operator decision. No overwrite by default.
- Destructive actions are visually isolated and require explicit confirmation.

### Activity Log

Chronological, searchable and filterable. Show severity, timestamp, job ID and module. Use monospace for paths, object keys and hashes. Allow copy. Redact credentials and secrets. Do not make a terminal-like log the default home screen.

### Settings

Group Storage & OSS, Verification, Output Naming, Security & Keys, Appearance and Diagnostics. Use explicit browse buttons and inline path validation. No unexplained default paths. Mask secrets and never log them.

## 5. Interaction rules

- Primary: solid signal-green with dark text.
- Secondary: neutral surface with border.
- Tertiary: text action.
- Destructive: red, separated, consequence explained.
- Disabled controls explain why.
- Visible keyboard focus and full keyboard navigation.
- Tables support sorting, filtering and sensible empty states.
- Truncated paths expose full value on hover/copy.
- Confirm consequential operations, not ordinary navigation.
- Persistent job status belongs in the page; toasts are for brief completion feedback.

## 6. Motion and feedback

- 120–180 ms transitions for hover, selection and dialogs.
- Progress bars reflect actual file/byte/stage progress.
- Indeterminate spinner only when progress cannot be measured.
- No blinking decorations, perpetual pulse, fake waveform or background particles.
- Respect reduced-motion preferences.

## 7. Responsive behavior

- 1280 px+: full sidebar and multi-column workspace.
- 1024–1279 px: narrower sidebar; tables may scroll horizontally.
- Below 1024 px: collapsible navigation; adapt tables only if all evidence remains accessible.
- Never hide status, warning reason or destructive-action context to save space.

## 8. Accessibility

- Target WCAG 2.2 AA contrast.
- Never communicate status by color alone.
- Minimum desktop interactive target 36×36 px.
- Keyboard-only operation and visible focus.
- Indonesian UI copy by default; technical identifiers remain exact.
- Explicit timezone for timestamps.
- Avoid tiny, low-contrast helper text.

## 9. Reusable component language

AppShell, SidebarNav, PageHeader, StatusLabel, EvidenceLevel, MetricTile, WorkflowStepper, StageProgress, DataTable, FilterBar, EmptyState, EvidencePanel, SegmentTimeline, FileTree, PathField, JobProgress, DangerConfirmDialog, Toast, InlineNotice and LogViewer.

Each component supports relevant loading, empty, success, warning, error and disabled states.

## 10. Product-specific constraints

- Evidence and reasons are more important than decorative metrics.
- METADATA_ONLY must never look equivalent to VERIFIED.
- AMBIGUOUS invites review, not automatic grouping.
- Source data is read-only; show this during source selection and output preview.
- Explain QR/crypto details without hiding technical audit evidence.
- A signed device does not prove the identity of the person holding it.
- Never fabricate device health, upload speed, scan progress or verification counts.

## 11. Design acceptance checklist

- [ ] Professional dark operations tool at first glance.
- [ ] Green is a restrained signal, not a full-screen glow.
- [ ] Supervisor can distinguish verified, warning and rejected recordings at a glance.
- [ ] Operator can understand why a result is not verified.
- [ ] Source/output distinction and original folder preservation are unmistakable.
- [ ] Upload conflicts and destructive actions are hard to trigger accidentally.
- [ ] Tables remain readable at 1280×800 and 1024×700.
- [ ] No fake data, decorative charts, AI-style gradients or meaningless HUD elements.
- [ ] Keyboard, contrast, empty, loading and error states are specified.
