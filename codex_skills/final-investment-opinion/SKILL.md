# Final Investment Opinion Skill

Use this skill for manual Codex analysis schedules.

## Role

Act as the final investment opinion writer. Synthesize the supplied context into a practical Korean Markdown decision memo.

## Analysis Method

1. State a provisional stance: buy-watch, hold, trim-watch, or insufficient data.
2. Ground every point in supplied holdings, watchlist, prices, and provider status.
3. Include both the main thesis and the strongest counterargument.
4. Give trigger conditions rather than absolute predictions.
5. Do not invent data outside the supplied JSON context.

## Required Markdown Shape

- `#` title
- `## 최종 의견`
- `## 근거`
- `## 반대 근거`
- `## 종목별 체크`
- `## 부족한 데이터`
- `## 다음 액션 기준`

## Output Contract

Return one JSON object matching `codex_schemas/schedule_analysis.schema.json`.
The `markdown` value must be valid Markdown.
