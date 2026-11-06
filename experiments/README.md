# Running the recovery experiments

The [platform snapshot](platform) includes the ALEMS core execution and metering source, database migrations, SDK, vLLM and BFCL plugins, recovery hooks and study drivers from ALEMS tag [raf-e3b](https://github.com/deepakpanigrahy03/alems-platform/tree/7b2102d1df2c17acbf20f4c00b44fa591c387161). The runtime configuration uses a local vLLM endpoint and SQLite. Configure the provider, model IDs, measurement devices and empty run store for the target node. The tagged upstream is recorded for attribution and version comparison. The [fitting snapshot](fitting/scripts/raf) includes the available controller analysis drivers at [662e69a](https://github.com/deepakpanigrahy03/alems-platform/tree/662e69aa89e46faa46a2ae6bff1f43e135ecb3c5/scripts/raf). See the [input guide](../analysis/r5/INPUTS.md) for the recorded historical fitting revision.

The [version index](study-versions.json) lists the upstream commit and local driver paths for each public RAF tag. Paths in the index start at the repository root. Shared driver versions appear once. Earlier driver versions with different contents are in [variants/](variants). Site-specific input paths have been made relative to the run directory; configure the paths for your node before launching a run.

To inspect a schedule, open [e1_gn100.yaml](platform/scripts/raf/e1_gn100.yaml) or [e3_gn100.yaml](platform/scripts/raf/e3_gn100.yaml). They specify task IDs, failure positions, repetitions and seeds. The [pilot driver](platform/scripts/raf/pilot_driver.py) takes the provider, served model and study configuration. With a configured ALEMS runtime, model server, study artifacts, and disposable measurement store, install the platform and plugin packages on the measurement node. For example, from the repository root:

```bash
cd experiments/platform
python -m pip install -r requirements.txt
python -m pip install -e . -e ./alems-sdk -e ./alems-plugin-bfcl -e ./alems-plugin-vllm
```

Set `PLATFORM` to the absolute path of `experiments/platform`. From a configured run sandbox, use the study driver in that platform installation:

```bash
python "$PLATFORM/scripts/raf/pilot_driver.py" --provider "$PROVIDER" --model "$MODEL" --config "$PLATFORM/scripts/raf/e1_gn100.yaml" --smoke
```

The driver records the execution and energy counters. For analyses on original experiment records, the [exporter](../scripts/export_dataset.py) and [goal accounting code](../scripts/paper_numbers.py) define selection, correctness and energy. To inspect outcomes without a node, use the exported CSVs and the [Table 1 calculation](../analysis/late_tool_recovery.py).
