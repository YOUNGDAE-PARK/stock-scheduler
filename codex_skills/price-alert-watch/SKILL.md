# Price Alert Watch Skill

Use this skill for price alert watch schedules.

## Role

Define the rule-based alert summary for current price monitoring.

## Rules

- Use KIS current prices for KR stocks when available.
- Use local snapshots for non-KR stocks until a live provider is connected.
- Send an alert for each manual run summary.
- Do not claim a rapid move unless prior comparison data exists.
- Include failed provider lookups in the alert body.

## Alert Shape

- Total successful lookups
- Total failed lookups
- Up to 10 updated stocks with ticker and price
- Failed tickers with short reason
