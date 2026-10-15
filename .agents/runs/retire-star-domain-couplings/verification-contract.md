# Verification contract — retire-star-domain-couplings

Slice: retire star-domain couplings (local defaults + target shim; entry
registration only). Written before production edits (2026-10-15).

## RED artifacts (must fail before the code edits)

| ID | Artifact | Reproduces |
|---|---|---|
| R1 | `apps/miroflow-agent/tests/data_agents/test_star_domain_retirement.py::test_gemma4_default_resolves_off_star` | gemma4 default endpoint = star URL today |
| R2 | `...::test_rerank_default_is_not_star` | `_DEFAULT_RERANK_URL` = star today |
| R3 | `...::test_script_default_profiles_resolve_off_star` | every script default profile resolves to star today |
| R4 | `...::test_only_allowlisted_profiles_point_at_star` | gemma4 (a default) is in the star set today |
| R5 | `apps/admin-console/tests/test_star_coupling_defaults.py::test_seed_publication_profile_default_resolves_off_star` | seed publication extractor default = gemma4 → star |

Run: `cd apps/miroflow-agent && uv run pytest tests/data_agents/test_star_domain_retirement.py -q`
and `cd apps/admin-console && uv run pytest tests/test_star_coupling_defaults.py -q`.

## GREEN criteria

1. R1–R5 pass after the edits.
2. Adjacent suites green:
   - `apps/miroflow-agent`: `tests/providers/test_rerank.py`,
     `tests/data_agents/professor/test_llm_profiles.py`
   - `apps/admin-console`: the suites touching `backend/api/seeds.py`
3. Fresh-process probe (new interpreter, switch-line PYTHONPATH) prints:
   - `gemma4 -> http://100.64.0.27:1231/v1`
   - `rerank -> http://100.64.0.27:18006`
4. `git diff --name-only` contains no `canonical_v2/*.py` (digest neutrality).
5. Target machine: listener `100.64.0.27:18005` gone; `nginx -t` ok; site
   `/chat` + `/api/health` 200; `nginx -T` star-free; passive capture during a
   keep-warm turn shows no `172.18.24.245` connection.

## Not verified by this contract (declared)

- The star gateway showing zero *other* consumers (needs the school's client-IP
  logs; request sent).
- The live 18188 process picking up the new defaults (dormant paths; next
  planned restart). Behaviour is proven by tests + fresh-process probe.
- The dbg21 `/guoxian` removal (deliberately not executed today).
