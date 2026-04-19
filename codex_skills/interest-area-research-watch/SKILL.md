# Interest Area Research Watch Skill

Use this skill for the `interest_area_research_watch` schedule.

## Role

Detect whether enabled interest areas have meaningful new research, product, regulatory, clinical, academic, patent, or commercialization outcomes that could affect the outlook of linked stocks.

## Inputs

Use only the supplied JSON context:

- `interest_areas`: enabled fields of interest with category, keywords, memo, and linked tickers.
- `stocks`: linked stock candidates derived from the interest areas.
- `prices`: current price refresh result when available.
- `enabled_sources`: approved news, disclosure, expert, and social sources.
- `provider_notes`: provider availability and limitations.

Do not invent live news. If the context does not include collected research/news items, say that detection is pending provider connection.

## Detection Standard

Set `major_signal_detected=true` only when the context contains a concrete, source-backed outcome with likely market relevance, such as:

- peer-reviewed or high-confidence research breakthrough with clear commercial path,
- clinical or regulatory milestone,
- patent, license, partnership, product launch, or capex signal,
- government funding or policy decision,
- disclosure that directly links the field to a listed company,
- credible expert source explicitly connecting the development to stock outlook.

Set `major_signal_detected=false` when evidence is absent, stale, vague, or not linked to a stock outlook.

## Report Structure

Return JSON matching `codex_schemas/schedule_analysis.schema.json`.

The Markdown must include:

1. `# 관심분야 연구성과 감지`
2. `## 판정`
3. `## 관심분야별 점검`
4. `## 연결 종목 영향`
5. `## 알림 기준`
6. `## 다음 확인`

When `major_signal_detected=true`, make `notification_summary` a concise Korean alert summary. When false, use `null`.
