# Open-source release checklist

## Repository and rights

- [ ] Apache-2.0 `LICENSE` and `NOTICE` are present.
- [ ] Third-party notices and data policies are current.
- [ ] No third-party raw, normalized, processed, or record-level QA data is tracked.
- [ ] Product specifications, PDFs, screenshots, and internal reports have an explicit publication decision.
- [ ] No secret, credential, signed URL, personal path, or private attachment is tracked.

## Reproducibility

- [ ] `scripts/bootstrap.ps1` succeeds from a clean checkout.
- [ ] `scripts/test_public.ps1` succeeds without third-party historical data.
- [ ] Full data tests succeed in an authorized local data environment.
- [ ] The Web production build succeeds.
- [ ] README commands and supported runtime versions are current.

## Quality and security

- [ ] CI passes on `main`.
- [ ] `scripts/release_audit.ps1` passes.
- [ ] Dependency manifests and lock files are committed.
- [ ] Dependency/license and vulnerability reviews have no unresolved release blockers.
- [ ] SECURITY, CONTRIBUTING, and Code of Conduct files are present.

## GitHub release

- [ ] Default branch is `main`.
- [ ] Branch protection requires CI.
- [ ] Private vulnerability reporting is enabled.
- [ ] Issue and pull-request templates are enabled.
- [ ] Release notes clearly state that historical data is not bundled.
- [ ] The release tag points to the reviewed commit.
