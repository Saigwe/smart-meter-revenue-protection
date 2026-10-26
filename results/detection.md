# Detection against planted theft

5,200 meters scored (reporting in both Oct-Dec 2012 and Oct-Dec 2013); 167 planted cases.

- Rules flag 450 meters: precision 35.6%, recall 95.8%.
- False positives are 18% time-of-use customers (vs 20% of all meters).
- Revenue at risk, top 167: £55,772 a year (£29,321 from planted cases). Estimated unbilled energy is 1.06x the true amount for planted meters.

| Method | k | Precision | Recall |
|---|---:|---:|---:|
| rule_score | 50 | 58.0% | 17.4% |
| rule_score | 100 | 50.0% | 29.9% |
| rule_score | 167 | 54.5% | 54.5% |
| iforest_score | 50 | 48.0% | 14.4% |
| iforest_score | 100 | 45.0% | 26.9% |
| iforest_score | 167 | 32.9% | 32.9% |
| combined_score | 50 | 58.0% | 17.4% |
| combined_score | 100 | 50.0% | 29.9% |
| combined_score | 167 | 54.5% | 54.5% |

| Theft type | Planted | Caught by a rule | In combined top k |
|---|---:|---:|---:|
| bypass | 42 | 39 | 2 |
| credit_tamper | 42 | 38 | 14 |
| flatline | 42 | 42 | 42 |
| night_bypass | 41 | 41 | 33 |
