# Action-set benchmark (10 sites, 20 tasks)

Methods:
- Standard browser use (raw page text + naive click-by-text)
- OpenClaw browser (snapshot refs + click)
- Semantic Browser (auto route + planner action IDs)

| Method | Success rate | Stuck rate | Median speed ms | Median tok-in | Median tok-out | Est. cost / request (USD) | Est. cost / 10 requests (USD) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Standard browser use | 0.75 | 0.25 | 2408.2 | 159.0 | 13.0 | 0.000672 | 0.006720 |
| OpenClaw browser | 0.60 | 0.40 | 2452.5 | 2644.0 | 13.0 | 0.008127 | 0.081270 |
| Semantic Browser | 0.80 | 0.20 | 5478.9 | 1039.0 | 13.0 | 0.003312 | 0.033120 |

Cost basis: Claude Sonnet 4.6 pricing = $3 / 1M input tokens and $15 / 1M output tokens (Anthropic public pricing page).

`tok-in`/`tok-out` are sourced from provider usage telemetry (`usage` in chat/completions responses), not local payload-size proxies.
