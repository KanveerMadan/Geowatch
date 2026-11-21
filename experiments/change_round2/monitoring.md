# Forward water and vegetation monitoring

The six small plots cover 54 cells in Kolkata, Pune, Bandung, Dakar, Utrecht and Haarlem. They include humid monsoon, semi-arid coast and temperate urban settings. Each acquisition cutoff is the last complete UTC date when the command runs. A month-to-date report can include early positive evidence; missed acquisitions remain missing. Water gain is ineligible on the permanent-water mask. Forest detections require historical forest support. Monitoring targets water and forest loss. The building experiment uses annual endpoint labels and a different evaluation period.

From the isolated repository use its configured Python environment. The default durable store sits in a sibling directory called `.geowatch-round2-monitor`. Use `--store` consistently for an alternative. Source retrieval uses the existing Earth Engine account and disk checks before downloads. A single process lock serializes Earth Engine requests across round-2 tasks. The monitor also caps each plot at nine 100 m blocks. Process exit releases the lock.

```sh
caffeinate -i env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 geowatch-env/bin/python -m experiments.change_round2.monitor run
caffeinate -i env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 geowatch-env/bin/python -m experiments.change_round2.monitor_review make
```

The first command stores all source- and track-specific candidates, confirmations, usable observations, masks and per-target observability in SQLite. The second command creates independent Landsat RGB and SWIR image strips. The acquisition-day ledger preserves actual receipt times, including arrivals whose observation date was earlier. Rerunning a completed cutoff retrieves the original receipt. Technical failures leave the failed site available for retry. A later invocation starts at its actual date; the system cannot reconstruct when an unseen earlier alert would have arrived. A new method fingerprint opens a separate collection series. The individual observation keys count new evidence dates across cutoffs. One physical event may affect many cells or generate several evidence dates.

**Blind review.** Read only the anonymous PNG files in the `blind` directory printed by the second command. The marks bound the 100 m reporting cell. Negative offsets are earlier observations, positive offsets are in the monitoring month. Flagged and quiet samples are mixed in hash order. Sites can lack either stratum. Clear observations need to support a substantial change inside the same cell. Look for corresponding water expansion or retreat on the RGB and SWIR panel at independent dates. Persistently unchanged water occupancy requires one clear prior day and two distinct clear days in the monitoring period. Evaluate a substantial greenness loss separately. Missing observations, ambiguous boundaries or agricultural/seasonal ambiguity for forest change warrant an unknown verdict. Shadows, cloud and turbidity can cause disagreement. The input contains acquisition-day evidence; between-image events can escape the reviewer.

Write one entry per anonymous ID. The common file format is shown below. Water accepts `stable`, `gain`, `loss`, `both` or `unknown`, vegetation accepts `stable`, `loss` or `unknown`. The reason should explain the evidence for both targets.

```json
{"reviewer":"reviewer identity","prediction_blind":true,"cases":{"anonymous-id":{"water":"unknown","vegetation":"unknown","reason":"Only a pre-month observation was clear."}}}
```

Use a cutoff-specific label file in the private store. Joining seals the original verdicts before reporting the sampled comparison with the silent baseline. Review selection is purposive; per-cell comparisons help identify failure modes but cannot establish a full-city false-alert rate. The independent Landsat interpretation is an optical proxy for surface change. It does not establish flood cause, canopy removal, or continuous water occupancy between acquisition dates.

```sh
geowatch-env/bin/python -m experiments.change_round2.monitor_review join --labels PATH_TO_LABELS
geowatch-env/bin/python -m experiments.change_round2.monitor summary
```

Both review commands accept `--cutoff YYYY-MM-DD`. This supports finishing a pending review on a later day without relabeling a new window. The `run` command always collects through the actual latest complete UTC day. No monitoring command sends a public alert.

## First actual collection and independent review

Method `c9f3cd60` collected the six plots through November 20, 2026 UTC. The ledger holds 54 complete cell snapshots. Two cells produced candidates and none reached confirmation. One candidate was a water observation and one was a forest observation. All 54 cells could be judged for at least one target. Eligibility differs by target and this sample bounds only 0.54 km² across all six cities.

Before opening the predictions, Codex reviewed all eight anonymous Landsat strips in hash order. The sample comprised two candidate cells and six quiet cells. Three cells showed stable visible water occupancy on multiple monitoring dates; the remaining five had insufficient imagery or ambiguous boundaries. For vegetation, one reference supported stable greenness, while that cell's forest-loss screen abstained. Seven vegetation cases lacked a sufficiently clear independent endpoint. The water detector and always-silent baseline agreed on the three decided water cases. Zero confirmed changes in these small plots provides no estimate of confirmation precision or a whole-city false-alarm rate. [First receipts summary](monitor_first_summary.json) · [Sealed reviews, evidence and baseline comparison](monitor_first_review.json)
