# End-to-end benchmark (5 AI-driven multi-step public-site tasks)

Methods compared per task request:
- Standard browser tooling (raw DOM extraction + JS actions)
- OpenClaw browser tooling (snapshot refs + browser actions)
- Semantic Browser (observe/act with semantic action IDs)

Each method ran the exact same 5 prompts and used the same planner model route.
Planner route: `codex:gpt-5.3-codex`

Cost model: Sonnet 4.6 estimated pricing constants (input $3.00 / 1M, output $15.00 / 1M).

| Method | Success rate | Failures | Median speed ms | Median tok-in | Median tok-out | Est. cost/request (USD) |
|---|---:|---:|---:|---:|---:|---:|
| Standard browser tooling | 0.4 | 3 | 18471.5 | 24885.0 | 408.0 | 0.138962 |
| OpenClaw browser tooling | 0.4 | 3 | 60000.0 | 22858.0 | 289.0 | 0.119324 |
| Semantic Browser | 0.4 | 3 | 52384.3 | 20892.0 | 320.0 | 0.123281 |

## Per-run journals

- JSON journals directory: `docs/benchmarks/journals/2026-03-11`
- One journal file is written for every method x task run (15 files total).

## Tasks

- **amazon_deals_electronics** (amazon): Open Today's Deals, then navigate to Electronics deals.
- **reddit_popular_askreddit** (reddit): Open the Popular feed, then open r/AskReddit.
- **youtube_explore_trending** (youtube): Open Explore, then open Trending.
- **bbc_news_technology** (bbc): Open BBC News, then open the Technology section.
- **wikipedia_english_current_events** (wikipedia): Open English Wikipedia, then open Current events.

Artifacts: `docs/benchmarks/2026-03-11-actionset-compare.md` and `docs/benchmarks/2026-03-11-actionset-compare.json`