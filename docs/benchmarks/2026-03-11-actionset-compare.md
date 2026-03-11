# Action-set benchmark (10 sites, 20 tasks)

Methods:
- Standard browser use (raw page text + naive click-by-text)
- OpenClaw browser (snapshot refs + click)
- Semantic Browser (auto route + planner action IDs)

| Method | Success rate | Stuck rate | Median speed ms | Median tok-in | Median tok-out |
|---|---:|---:|---:|---:|---:|
| Standard browser use | 0.65 | 0.35 | 3420.6 | 253.5 | 15.0 |
| OpenClaw browser | 0.65 | 0.35 | 3597.9 | 2991.5 | 14.5 |
| Semantic Browser | 0.8 | 0.2 | 5322.7 | 1204.5 | 15.0 |