# 解决方案与经验沉淀索引

`docs/solutions/` 记录的是已经在代码、真实数据 E2E、发布链路或检索链路中验证过的问题与经验。这里的重点是帮助你快速找到当前仍有操作价值的文档，而不是平铺所有历史记录。

## 当前主线判断入口

- [workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md](./workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)
  教授主线的当前事实、执行口径与操作建议。
- [workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md](./workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md)
  哪些问题已经收住，哪些只是 residual 或新暴露问题。
- [workflow-issues/data-agent-real-e2e-gates-2026-04-02.md](./workflow-issues/data-agent-real-e2e-gates-2026-04-02.md)
  真实 E2E 作为最终验收口径的通用约束。
- [workflow-issues/professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md](./workflow-issues/professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md)
  serving refresh 与验收型 E2E 输入必须分流。

## 继续优化的主线主题

- 论文多源证据增强：
  [workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md](./workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md)
- 质量门与真实 E2E 验收：
  [best-practices/professor-prd-real-data-phase-a-gate-2026-04-14.md](./best-practices/professor-prd-real-data-phase-a-gate-2026-04-14.md)
- 官方第二证据源：
  [best-practices/official-linked-orcid-second-evidence-source-2026-04-15.md](./best-practices/official-linked-orcid-second-evidence-source-2026-04-15.md)
- 深圳高校 adapter 架构方向：
  [best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md](./best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)

## 已完成但仍值得保留的闭环经验

- [best-practices/discipline-aware-professor-quality-gate-2026-04-14.md](./best-practices/discipline-aware-professor-quality-gate-2026-04-14.md)
- [best-practices/professor-safe-search-dedupe-and-duplicate-retrieval-warning-2026-04-15.md](./best-practices/professor-safe-search-dedupe-and-duplicate-retrieval-warning-2026-04-15.md)
- [best-practices/workbook-closure-via-source-backfill-and-serving-side-knowledge-fields-2026-04-16.md](./best-practices/workbook-closure-via-source-backfill-and-serving-side-knowledge-fields-2026-04-16.md)

## Best Practices

- [best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md](./best-practices/professor-school-adapter-architecture-for-limited-shenzhen-seeds-2026-04-16.md)
- [best-practices/discipline-aware-professor-quality-gate-2026-04-14.md](./best-practices/discipline-aware-professor-quality-gate-2026-04-14.md)
- [best-practices/professor-safe-search-dedupe-and-duplicate-retrieval-warning-2026-04-15.md](./best-practices/professor-safe-search-dedupe-and-duplicate-retrieval-warning-2026-04-15.md)
- [best-practices/professor-prd-real-data-phase-a-gate-2026-04-14.md](./best-practices/professor-prd-real-data-phase-a-gate-2026-04-14.md)
- [best-practices/official-linked-orcid-second-evidence-source-2026-04-15.md](./best-practices/official-linked-orcid-second-evidence-source-2026-04-15.md)
- [best-practices/workbook-closure-via-source-backfill-and-serving-side-knowledge-fields-2026-04-16.md](./best-practices/workbook-closure-via-source-backfill-and-serving-side-knowledge-fields-2026-04-16.md)

## Workflow Issues

- [workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md](./workflow-issues/professor-pipeline-current-findings-and-operating-guidance-2026-04-16.md)
- [workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md](./workflow-issues/professor-pipeline-current-closed-vs-open-issues-2026-04-16.md)
- [workflow-issues/professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md](./workflow-issues/professor-serving-refresh-must-use-full-harvest-not-sampled-e2e-2026-04-16.md)
- [workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md](./workflow-issues/paper-multi-source-rollout-must-be-phased-2026-04-08.md)
- [workflow-issues/professor-url-md-ready-paper-closure-2026-04-08.md](./workflow-issues/professor-url-md-ready-paper-closure-2026-04-08.md)
- [workflow-issues/testset-answer-workbook-coverage-validation-2026-04-16.md](./workflow-issues/testset-answer-workbook-coverage-validation-2026-04-16.md)

## Integration Issues

- [integration-issues/professor-seed-fallback-must-outrank-homepage-redirect-nav-candidates-2026-04-16.md](./integration-issues/professor-seed-fallback-must-outrank-homepage-redirect-nav-candidates-2026-04-16.md)
- [integration-issues/professor-seed-context-and-generic-faculty-direct-profile-misclassification-2026-04-16.md](./integration-issues/professor-seed-context-and-generic-faculty-direct-profile-misclassification-2026-04-16.md)
- [integration-issues/professor-thread-scoped-playwright-browser-for-threadpool-pipeline-2026-04-16.md](./integration-issues/professor-thread-scoped-playwright-browser-for-threadpool-pipeline-2026-04-16.md)
- [integration-issues/official-publication-evidence-fallback-2026-04-14.md](./integration-issues/official-publication-evidence-fallback-2026-04-14.md)
- [integration-issues/gemma-4-llm-integration-proxy-and-provider-compat-2026-04-06.md](./integration-issues/gemma-4-llm-integration-proxy-and-provider-compat-2026-04-06.md)
- [integration-issues/cuhk-ssl-crawler-markdown-fallback-2026-04-07.md](./integration-issues/cuhk-ssl-crawler-markdown-fallback-2026-04-07.md)

## Data Quality / Logic

- [data-quality/professor-paper-gap-root-cause-and-remediation-plan-2026-04-07.md](./data-quality/professor-paper-gap-root-cause-and-remediation-plan-2026-04-07.md)
- [data-quality/professor-pipeline-v3-data-gap-analysis-2026-04-07.md](./data-quality/professor-pipeline-v3-data-gap-analysis-2026-04-07.md)
- [data-quality/professor-research-direction-cleaner-overfiltered-hss-fields-2026-04-14.md](./data-quality/professor-research-direction-cleaner-overfiltered-hss-fields-2026-04-14.md)
- [data-quality/professor-homepage-root-overrode-profile-url-2026-04-14.md](./data-quality/professor-homepage-root-overrode-profile-url-2026-04-14.md)
- [logic-errors/professor-pipeline-v3-quality-gate-false-blocks-2026-04-07.md](./logic-errors/professor-pipeline-v3-quality-gate-false-blocks-2026-04-07.md)

## 其他仍值得保留的通用文档

- [admin-console-fastapi-sqlite-patterns-2026-04-04.md](./admin-console-fastapi-sqlite-patterns-2026-04-04.md)
- [professor-pipeline-v2-deployment-patterns-2026-04-05.md](./professor-pipeline-v2-deployment-patterns-2026-04-05.md)

## 历史参考

- [best-practices/professor-pipeline-v3-performance-optimization-2026-04-07.md](./best-practices/professor-pipeline-v3-performance-optimization-2026-04-07.md)
- [best-practices/professor-school-adapter-phase1-minimal-registry-and-real-e2e-2026-04-16.md](./best-practices/professor-school-adapter-phase1-minimal-registry-and-real-e2e-2026-04-16.md)
- [integration-issues/professor-discovery-wave4-hardening-with-targeted-real-e2e-2026-04-16.md](./integration-issues/professor-discovery-wave4-hardening-with-targeted-real-e2e-2026-04-16.md)

## 使用规则

- 先看“当前主线判断入口”，判断什么已经完成、什么还要继续优化。
- 再看“继续优化的主线主题”，确定当前主线任务。
- 需要解释“为什么之前这样修”，从 best-practices / integration-issues 往回找。
- 需要判断“今天的代码和文档是否还一致”，优先看 `workflow-issues` 下的 current docs，而不是直接看旧 baseline。
