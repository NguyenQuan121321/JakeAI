# FastEmbed Pillow 13 compatibility release

`fastembed-0.8.0+jakeai.1-py3-none-any.whl` is a JakeAI-maintained,
metadata-only downstream release of Qdrant FastEmbed 0.8.0 (Apache-2.0).
Every Python module, model description, tokenizer/inference implementation,
data file, LICENSE and NOTICE is byte-for-byte upstream. The wheel retains
the complete upstream LICENSE and NOTICE in its dist-info directory.

Only distribution metadata changes: version `0.8.0+jakeai.1`, Python >=3.11,
Pillow >=13,<14 and a prominent downstream-modification notice. The dist-info
directory and RECORD follow the new version.
This project already requires Python >=3.11. Pillow 13 closes the current image
decoder/encoder advisories. Upstream 0.8/0.9 still constrain Pillow below 13.
No forced installation, dependency override, scanner exception or inference
replacement is involved.

`fastembed-provenance.json` pins the official PyPI wheel URL and SHA256 and the
downstream SHA256. From the repository root:

```sh
python backend/vendor/verify_fastembed.py --rebuild
python backend/vendor/verify_fastembed.py --check-installed
pip-audit -r backend/requirements.txt
```

The first command deterministically reproduces the stored wheel using an
uncompressed ZIP with fixed timestamps. The mandatory second gate retrieves
the pinned upstream release through PyPI, checks its active security advisories,
reconstructs the entire compatibility wheel, verifies every byte and verifies
the installed runtime modules/data. Network, inventory, hash, source/license or
active-advisory failure rejects CI. No advisory severity is ignored.

The unchanged pip-audit requirement gate audits the full resolved dependency
graph. The Docker builder and CI/CD verify provenance before installation as
well. PyPI cannot look up a private local version, so it reports that one
distribution as unavailable for its own feed. The additional mandatory gate
closes that gap using its proven exact upstream identity; it does not accept
an unknown local package or replace the normal dependency audit. Both gates
must pass. SBOM/license/image gates remain enabled and see the actual local
distribution version and its retained license files.

The embedding model remains `BAAI/bge-small-en-v1.5`, dimension 384, version
tag `v1.0`, with unchanged tokenizer, ONNX model, pooling and normalization.
Real before/after adapter inference with identical model-file hashes must
match within 1e-6 before accepting this patch. The current repair also tests
actual FastEmbed RGB/gray/alpha preprocessing, tensor resize, PNG/JPEG codecs
and image-bearing PDF parsing. No live reindex or migration is performed.

Maintenance: do not edit the binary or overwrite a released local version.
For any upstream/code/dependency change, increment the local version, update
the pinned provenance, repeat inference/vector and image compatibility checks,
and review the source/license/advisory changes. New upstream advisories block
this patch even if a future developer considers them inapplicable. Replace the
downstream package with an officially supported audited release when possible,
removing this bridge only after equivalent checks pass. Reverting to Pillow 12
reopens the security failure; changing embedding artifacts requires an explicit
persisted-vector compatibility/reindex decision.
