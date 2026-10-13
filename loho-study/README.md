# LIBERO-LoHo study

- [Installation and reproduction guide](../docs/setup.md)
- [Three-sentence findings](post.md)
- [Astra versus Opus static-camera comparison with API waiting: 40x overview and 4x replay](videos/README.md)
- [Astra versus Opus bar plots: scores, tokens, cost, time, calls and steps](plots/README.md)
- [Alternative figures and results tables](plots/options/README.md)
- [Task 0 results and camera videos](<task 0/README.md>)
- [Task 0 five-trial comparison](<task 0/task0_uncapped_extend_20261011_221112_combined_REPORT.md>)
- [Task 1 results and camera videos](<task 1/README.md>)
- [Task 1 five-trial comparison](<task 1/task1_uncapped_20261011_234048_REPORT.md>)
- [Task 4 results and camera videos](<task 4/README.md>)
- [Task 4 five-trial retained results](<task 4/task4_retained_20261012_135134_REPORT.md>)

Task 0's current comparison contains five GPT-6 Astra max and five Opus 5.5 max trials, all with simulator-confirmed full success. Earlier task-0 experiments and startup records are also retained in that folder and labeled separately. Each run retains its static and wrist MP4s, scores, prompts, actions and cost records. No standalone PNGs are retained.

Task 1's five-trial-per-model comparison is complete: place the alphabet soup, butter and tomato sauce into the basket. Both models achieved 3/5 full successes. Astra averaged 86.7% final goal completion at an estimated $14.4565750 USD total; Opus averaged 80.0% at $44.0600766 USD. All twenty camera videos are verified. [Task-1 results, settings and stopping reasons](<task 1/README.md>).

Task 4 contains five retained Astra max runs and five retained Opus 5.5 max runs, all with 100% simulator-confirmed completion. Estimated retained-run totals are $22.7302665 USD for Astra and $29.5998880 USD for Opus. All twenty camera videos are verified. [Task-4 results and settings](<task 4/README.md>).

The linked comparison reports are the authoritative completed result sets.

Runtime code is in [src/](../src/), with model settings and pricing snapshots in [config/](../config/). The simulator is installed separately through the setup guide; credentials stay in the ignored local `.env`. [Workspace README](../README.md).
