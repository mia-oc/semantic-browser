# Action-set benchmark (10 sites, 20 tasks)

Methods:
- Standard browser use (raw page text + naive click-by-text)
- OpenClaw browser (snapshot refs + click)
- Semantic Browser (auto route + planner action IDs)

| Method | Success rate | Stuck rate | Median speed ms | Median tok-in | Median tok-out |
|---|---:|---:|---:|---:|---:|
| Standard browser use | 0.75 | 0.25 | 2408.2 | 159.0 | 13.0 |
| OpenClaw browser | 0.60 | 0.40 | 2452.5 | 2644.0 | 13.0 |
| Semantic Browser | 0.80 | 0.20 | 5478.9 | 1039.0 | 13.0 |

Note: `tok-out` is measured as the action payload token count emitted by the method policy for each task step.
