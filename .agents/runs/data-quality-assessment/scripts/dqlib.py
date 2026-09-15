"""Shared helpers for read-only data-quality analysis of the run15 serving pack."""
import gzip, json, os, re, collections

DATA = '/home/longxiang/MiroThinker/.agents/runs/data-quality-assessment/data'

def load(domain):
    with gzip.open(os.path.join(DATA, f'{domain}.jsonl.gz'), 'rt', encoding='utf-8') as fh:
        for line in fh:
            yield json.loads(line)

# ---- placeholder families (independent re-implementation; see sealer report for the reference version) ----
EXACT_PLACEHOLDERS = {
    '-', '–', '—', '/', 'n/a', 'na', 'none', 'null', 'nil', '无', '暂无', '未知', '未找到',
    '无数据', '暂无数据', '待补充', '未提供', '未公开', '不详', '待定', '待完善', 'undefined',
    'not available', 'not applicable', 'no data', 'no info', 'unknown', 'tbd', 'to be determined',
}
PREFIX_PLACEHOLDERS = (
    '未找到', '暂无', '待补充', '未提供', '未公开', '不详',
    'not supplied', 'no dedicated summary was supplied', 'not provided', 'no summary',
    'not available', 'none supplied',
)
GLUE_TOKEN = '未找到'
# placeholder produced by an over-eager prompt/redaction step: a real substring replaced by 未找到
EN_SENT_PREFIX = re.compile(r'^\s*(not supplied|no dedicated summary|no summary|not provided)\b', re.I)

def classify_str(s):
    """Return None if clean, else a placeholder family name."""
    if s is None:
        return None
    t = s.strip()
    if t == '':
        return 'empty'
    low = t.lower()
    if low in EXACT_PLACEHOLDERS or t in EXACT_PLACEHOLDERS:
        return 'placeholder-exact'
    for p in PREFIX_PLACEHOLDERS:
        if low.startswith(p):
            return 'placeholder-prefix'
    if EN_SENT_PREFIX.match(t):
        return 'placeholder-prefix'
    if GLUE_TOKEN in t:
        return 'placeholder-glued'
    return None

def label_of(v):
    """Resolve a {reference_id,name} ref or plain value to its human label."""
    if isinstance(v, dict):
        if 'label' in v: return v['label']
        if set(v.keys()) == {'reference_id','name'}: return v['name']
    return v

def is_filled(v):
    """Structural fill test (ignores placeholder quality)."""
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ''
    if isinstance(v, dict) and 'label' in v:
        return isinstance(v['label'], str) and v['label'].strip() not in ('', None)
    if isinstance(v, list):
        return len(v) > 0
    if isinstance(v, dict):
        if 'len' in v and 'head' in v:      # TEXT preview
            return v['len'] > 0
        if 'n' in v and 'v' in v:           # LIST preview
            return v['n'] > 0
        if '_str' in v:
            return v['_str'].strip() != ''
        if v.get('kind') == 'list':
            return v.get('n', 0) > 0
        if v.get('kind') == 'dict':
            return True
        return True
    return True

def true_str(v):
    """Recover the best-effort string/list-of-strings for text analysis."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    if isinstance(v, dict):
        if 'len' in v and 'head' in v:
            return [v['head']]
        if 'n' in v and 'v' in v:
            return v['v']
        if 'label' in v:
            return [v['label']] if isinstance(v['label'], str) else []
        if '_str' in v:
            return [v['_str']]
        if v.get('sample'):
            return [v['sample']]
    return []

def pct(n, d):
    return f'{(100.0*n/d):.1f}%' if d else 'n/a'
