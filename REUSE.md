# Licenses and attribution

The [MIT License](LICENSE) covers original RAF source code, including experiment, analysis, and figure-generation scripts. [CC BY 4.0](LICENSE-DATA) covers the original RAF measurements, derived results, and figures. This distinction follows the material even where a directory contains both code and data. For attribution to the research work, see [CITATION.cff](CITATION.cff).

## Bundled components

| Component | License and notices |
| --- | --- |
| ALEMS platform, fitting code, and historical driver variants | MIT, with the original notices in [platform](experiments/platform/LICENSE), [fitting](experiments/fitting/LICENSE), and [variants](experiments/variants/LICENSE). Bundled dependencies retain their own notices, including the [Darwin sensor code](experiments/platform/core/readers/darwin/vendor/LICENSE). |
| BFCL benchmark software and data | [Apache 2.0](experiments/platform/alems-plugin-bfcl/LICENSE.upstream), with the [upstream notice](experiments/platform/alems-plugin-bfcl/NOTICE) and [attribution](experiments/platform/alems-plugin-bfcl/UPSTREAM.md). |
| earctl controller, parameters, and decision fixtures | Distributed together under the [included Apache 2.0 license](earctl/LICENSE). Its [source manifest](earctl/src/earctl/_vendor/SOURCES.json) identifies the vendored files. |
