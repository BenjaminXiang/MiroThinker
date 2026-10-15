# Tasks: retire-star-domain-couplings

## Slice 1 — local defaults off star (this round)

- [x] 1. Probe `http://100.64.0.27:1231/v1/models` with the repo key loader:
      serves `qwen3.6-35b-a3b` (same model as star `qwen36`).
- [x] 2. Verification contract written
      (`.agents/runs/retire-star-domain-couplings/verification-contract.md`).
- [x] 3. RED: new regression tests fail against the current defaults.
- [x] 4. `professor/llm_profiles.py`: `gemma4.local.base_url` →
      `http://100.64.0.27:1231/v1` (comment records why).
- [x] 5. `providers/rerank.py`: `_DEFAULT_RERANK_URL` →
      `http://100.64.0.27:18006`.
- [x] 6. `deploy/preflight.sh` (s11-consolidation tree): `DEFAULT_LLM_URL` →
      `http://100.64.0.27:1231/v1`.
- [x] 7. GREEN: new tests pass; adjacent suites (`test_rerank`,
      `test_llm_profiles`, console seeds/rerank-touching suites) pass.
- [x] 8. Fresh-process probe: resolving `gemma4` and the 12 script defaults now
      yields non-star endpoints.

## Slice 2 — target machine shim removal

- [x] 9. Record current state (shim file, `100.64.0.27:18005` listener,
      `nginx -T` star lines).
- [x] 10. Check whether `gxzx-origin-map.conf` is referenced by active configs.
- [x] 11. Backup + disable `miro-embed-shim.conf`; `nginx -t`; reload.
- [x] 12. Verify: no `:18005` listener, site `/chat` + `/api/health` 200,
      `nginx -T` has no star reference, no new star connections.

## Slice 3 — registration & documents

- [x] 13. `deploy/retire-star-entry.sh` (dbg21 `/guoxian` removal: backup,
      block removal, reload, verification) — **prepared, not executed**
      (user decision: wait for the school's date).
- [x] 14. `deploy/README.md`: entry marked "retirement pending school date".
- [x] 15. Human docs: `docs/plans/2026-10-15-star-couplings-retirement.md`
      (plan) + `docs/plans/2026-10-15-star-couplings-retirement-log.md` (round 1)
      + `docs/plans/index.md` line.

## Slice 4 — "certainty" closures (round 2, user-approved)

- [x] 17. Local 18188 restarted (290 s to health 200); live code verified to carry the new
      defaults; entry still 200; post-restart real question = **star 0**.
- [x] 18. Target run-9 hardened: star key renamed `.disabled-20261015`; unit file moved aside
      + `/dev/null` mask symlink + `daemon-reload`; `systemctl start` refused; v2 line untouched.
- [x] 19. Fresh 4-min capture on the target's new pack: **star 0**; hedge env proven inert.

## Follow-ups (not this round)

- [ ] Repoint or delete `qwen35` / `mirothinker` / `ark.local` profiles when the
      school gives the shutdown date (allowlist test defines the target set).
- [ ] Fold the `CHAT_LLM_PROFILE` fallback constant (`gemma4`) change into the
      next serving-pack re-seal (digest-coupled).
- [ ] Remove the star gateway's `/guoxian` rule (school side) and, on that day,
      run `deploy/retire-star-entry.sh` on dbg21 (+ tightenf firewall rule).
- [ ] Hand the star-gateway owner the consumer-attribution note (ask for client
      IPs for the Oct 13/14 residual 45/29 requests).
