# Change Log

## 2026-05-28

- Added the requirement that Yiou site-filter organic search must not apply news-style recency-only filters by default. Live investigation showed `深圳旭宏医疗科技有限公司 site:data.iyiou.com` returns zero organic results with `tbs=qdr:y` but returns the Yiou company profile without the recency filter.
- Added the requirement that Yiou adapter must reject generic Yiou landing/list pages. Live validation showed search can return `https://data.iyiou.com/` or `https://data.iyiou.com/company`, which are source-site pages but not company evidence.
- Added normalized-name fallback and company-name confirmation requirements. Follow-up probing showed some zero-result companies had Yiou records under normalized names, so zero results from a single registered-name query cannot be treated as proof that Yiou has no data.
- Fixed production ingest routing so the Yiou connector receives the company canonical name instead of unified credit code.
- Added PitchHub as a second site-filter web-search source using `site:pitchhub.36kr.com`, because PitchHub project and organization pages expose product, financing, industrial/commercial, and team evidence.
- Added source-search context generation from XLSX/snapshot fields, including project name, description-derived aliases, founder names, and keywords.
- Tightened deterministic alias extraction so explicit short-name/brand/project markers are used, while generic product/service/technology phrases are not sent as standalone source-search aliases.
- Added reader-fallback detail fetch for accepted PitchHub pages after URL/path/name confirmation.
