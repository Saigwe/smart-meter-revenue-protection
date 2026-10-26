# Detection against planted theft

5,200 meters scored (reporting in both Oct-Dec 2012 and Oct-Dec 2013); 167 planted cases.

- Rules flag 451 meters: precision 35.5%, recall 95.8%.
- False positives are 18% time-of-use customers (vs 20% of all meters).
- Revenue at risk, top 167: £59,082 a year (£31,832 from planted cases). Estimated unbilled energy is 1.06x the true amount for planted meters.

| Method | k | Precision | Recall |
|---|---:|---:|---:|
| rule_score | 50 | 52.0% | 15.6% |
| rule_score | 100 | 52.0% | 31.1% |
| rule_score | 167 | 38.9% | 38.9% |
| iforest_score | 50 | 64.0% | 19.2% |
| iforest_score | 100 | 44.0% | 26.3% |
| iforest_score | 167 | 31.1% | 31.1% |
| combined_score | 50 | 66.0% | 19.8% |
| combined_score | 100 | 49.0% | 29.3% |
| combined_score | 167 | 46.1% | 46.1% |

| Theft type | Planted | Caught by a rule | In combined top k |
|---|---:|---:|---:|
| bypass | 42 | 39 | 6 |
| credit_tamper | 42 | 38 | 26 |
| flatline | 42 | 42 | 42 |
| night_bypass | 41 | 41 | 3 |
