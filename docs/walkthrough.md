# 3-minute walkthrough: Smart-Meter Revenue Protection

A timed script for a Loom recording of about 3 minutes (screen plus camera bubble, 1080p). Say it in your own words; the lines are a guide, not a teleprompter.

**Open these tabs before you press record:** README, dbt/models, spark/, results/detection.md, GitHub Actions.

| Time | On screen | What to say |
|---|---|---|
| 0:00–0:20 | Portfolio card, then the README title | Inspectors can visit only a few homes a week, so the list must be short and right. On 167.8 million real London smart-meter readings, more than half of the top 167 meters on this list are real theft cases, against a 3.2% base rate. |
| 0:20–0:45 | README intro and the Data section | As an engineering data analyst at a Nigerian electricity distributor, I analysed smart-meter and vending data in SQL and recovered NGN 5M in revenue in three months. This rebuilds the problem on UK Power Networks' public trial data. No employer data is used. |
| 0:45–1:10 | README architecture: Delta Lake → dbt → scoring | 8.5 GB of CSV becomes 1.0 GB of Delta in under 4 minutes, partitioned by date and Z-ordered by meter. |
| 1:10–1:35 | The weekly consumed-versus-bought gap and feeder-loss models | Detection uses only what a utility can see: metered energy, credit bought and feeder supply. Theft is planted on 3% of meters as ground truth. |
| 1:35–2:00 | `results/detection.md` | Explainable rules reach 54.5% precision, against 32.9% for an Isolation Forest, and each meter shows the rule that fired. |
| 2:00–2:30 | The Spark-equals-dbt test and the reverted experiment | The PySpark version is tested equal to dbt to the watt-hour. A feeder-balance check cut precision to 38%, so I reverted it and documented why. |
| 2:30–2:45 | `docs/design_doc.md`, the options table | The decision I'd defend in an interview: Keep ground truth out of every detection model, enforced by a lineage test, so the score can't cheat. |
| 2:45–3:00 | Back to the README top | For a utility, that means a ranked inspection list with the revenue at stake on each visit. The repo, numbers and design doc are linked under the video. |

## Recording checklist
- Close email, chat and notifications. Zoom the browser to 125% so code is readable.
- Run `make fixture-all` once before recording, so CI-style output is fresh if you show it.
- Keep to one take per section; Loom lets you trim. Aim for 2:45 to 3:10.
- Show real numbers on screen as you say them; never estimate on camera.
- Say "synthetic" out loud wherever the README labels data as synthetic.

## After recording
1. Copy the Loom share link.
2. In `README.md`, replace the roadmap line with `- [x] [3-minute Loom walkthrough](<your Loom link>)` and add the link under the title.
3. Add the link to this project's card on saigwe.github.io.
