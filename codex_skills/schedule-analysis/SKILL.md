# Schedule Analysis Skill

Use this skill when a stock_scheduler schedule is manually executed and the backend asks for an analysis report.

## Role

Write a practical Korean Markdown report using only the supplied JSON context.

## Rules

- Do not invent live prices, news, disclosures, or social posts that are not in the context.
- If a provider is not connected or a data point is missing, say so directly.
- Focus on decision support, not investment guarantees.
- Keep the report structured and scannable.
- Include both bullish and bearish considerations when possible.
- End with concrete next actions or watch conditions.

## Required Markdown Shape

Use these sections:

1. `#` title
2. `## 요약`
3. `## 현재가와 대상`
4. `## 긍정 요인`
5. `## 리스크`
6. `## 확인할 데이터`
7. `## 다음 액션`

## Output Contract

Return one JSON object matching `codex_schemas/schedule_analysis.schema.json`.
The `markdown` value must be valid Markdown text.
