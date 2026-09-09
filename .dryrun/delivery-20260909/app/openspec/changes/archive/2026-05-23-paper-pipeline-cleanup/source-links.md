# Source Links: paper-pipeline-cleanup

- `openspec/changes/prof-paper-patent-from-page-flow/` - parent change
  that introduced the page-first discovery contract.
- `apps/miroflow-agent/src/data_agents/professor/paper_collector.py` -
  active legacy caller surface.
- `apps/miroflow-agent/src/data_agents/paper/hybrid.py` - hybrid
  discovery compatibility module.
- `apps/miroflow-agent/src/data_agents/paper/pipeline.py` - deprecated
  old paper pipeline.
- `apps/miroflow-agent/scripts/run_paper_release_e2e.py` - legacy
  release script that still exposes hybrid discovery choices.
