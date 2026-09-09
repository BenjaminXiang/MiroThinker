"""Rule-based paper-title plausibility guard.

Round 7.12' targets a narrow failure mode in ``paper.title_clean``: author
lists and editorial bios pasted into the title field. This v1 is intentionally
rule-based only; there is no LLM fallback.
"""

from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")
_PAREN_PREFIX_RE = re.compile(r"^\(\d+\)[A-Z]")
_EDITORIAL_ROLE_RE = re.compile(
    r"(?:\bassociate editor\b|\beditor(?:-in-chief)?\b|\bco-chair\b|\bchair\b|主席)",
    re.IGNORECASE,
)
_STANDALONE_ROLE_RE = re.compile(
    r"^(?:associate\s+editor|editor(?:-in-chief)?|co-?chair|chair|reviewer|"
    r"committee\s+member)\.?$",
    re.IGNORECASE,
)
_STANDALONE_AWARD_OR_SERVICE_RE = re.compile(
    r"^(?:best\s+paper(?:\s+award)?|(?:[A-Z]{2,}\s+)?TPC\s+co-?chair)\.?$",
    re.IGNORECASE,
)
_STANDALONE_SECTION_LABEL_RE = re.compile(
    r"^[【\[\(\s]*(?:patents?|专利|awards?|honou?rs?|projects?|科研项目)"
    r"[\]）\)】\s]*$",
    re.IGNORECASE,
)
_PUBLICATION_SECTION_LABEL_RE = re.compile(
    r"^(?:"
    r"representative\s+publication(?:s)?|selected\s+recent\s+works?|"
    r"selected\s+publications?|selected\s+research\s+articles?|"
    r"research\s+projects?|"
    r"book\s+chapters?|conference\s+papers?|journal\s+papers?|"
    r"invited\s+paper|turing\s+lecture\s+slides|"
    r"selected\s+as\s+cover\s+pictures?"
    r")$",
    re.IGNORECASE,
)
_JOURNAL_METRIC_FRAGMENT_RE = re.compile(
    r"^(?:"
    r"[\(（]?\s*IF\s*[:=]\s*\d+(?:\.\d+)?"
    r"(?:\s*[\(（]?\s*(?:JCR\d*|SCI|Q[1-4])\s*[\)）]?)?"
    r"\s*[\)）]?"
    r"|[\(（]?\s*(?:中科院|JCR|SCI|ESI).{0,60}"
    r"(?:区|IF\s*[:=]|Q[1-4]|Top).{0,40}"
    r"|(?:\d+(?:\.\d+)?\s*)?[\(（]?\s*(?:JCR|SCI|ESI)\s*Q[1-4][\)）]?"
    r"|(?:category\s+)?quartile\s*[:：]?\s*Q[1-4]"
    r"|highly\s+cited(?:\s+paper)?"
    r")$",
    re.IGNORECASE,
)
_JOURNAL_METRIC_TAIL_RE = re.compile(
    r"(?:\bIF\s*[:=]\s*\d+(?:\.\d+)?(?:\s*[\(（]?\s*(?:JCR\d*|SCI|Q[1-4])\s*[\)）]?)?"
    r"|(?:中科院|JCR|SCI|ESI).{0,60}(?:区|IF\s*[:=]|Q[1-4]|Top))",
    re.IGNORECASE,
)
_UPDATE_METADATA_RE = re.compile(
    r"^(?:更新时间|更新日期|updated(?:\s+at| on)?|last\s+updated)\s*[:：]?\s*"
    r"(?:19|20)\d{2}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?$",
    re.IGNORECASE,
)
_HIGHLIGHTED_NOISE_RE = re.compile(r"^highlighted\s+in\b", re.IGNORECASE)
_REPRESENTATIVE_RESULT_PROSE_RE = re.compile(
    r"^(?:a\s+)?representative\s+result\s+of\s+my\s+works\s+is\s+the\s+article\b",
    re.IGNORECASE,
)
_PUBLICATION_TABLE_EXCERPT_RE = re.compile(
    r"(?:代表性论文|论文发表|发表论文).{0,80}"
    r"(?:序号|论文名称).{0,80}(?:期刊|会议|作者|时间).{0,120}"
    r"(?:\b\d{1,3}\b|[一二三四五六七八九十百]+)",
    re.IGNORECASE,
)
_YEAR_PREFIX_CITATION_METADATA_RE = re.compile(
    r"^\((?:19|20)\d{2}\)\s*:.{20,}"
    r"\b(?:ABDC|ABS|SCI|SSCI|JCR|IF\s*=)\b",
    re.IGNORECASE,
)
_LEADING_CITATION_YEAR_RE = re.compile(
    r"^\((?:19|20)\d{2}\.\)\.?\s+.{8,}$",
    re.IGNORECASE,
)
_PROJECT_STATUS_NOISE_RE = re.compile(
    r"^\d+(?:\.\d+)?\s*(?:万|万元|万美元|元)\s*[,，、]\s*"
    r"(?:在研|结题|主持|参与|负责人)\b"
    r"|^(?:19|20)\d{2}年?[，,]?\s*(?:入选|获|荣获).{1,60}"
    r"(?:Fellow|人才|计划|奖|院士|教授)$"
    r"|^(?:19|20)\d{2}.{0,24}博士后.{0,24}计划$"
    r"|^.{0,40}(?:基金|项目|计划|专项|课题|任务)[：:].{2,120}"
    r"(?:负责人|主持|参与|在研|结题|经费|资助)\s*$"
    r"|^.{0,40}(?:基金|项目|计划|专项|课题|任务).{0,20}"
    r"(?:No\.?|编号|负责人|主持|在研|结题|经费|资助).{0,80}$"
    r"|^(?:主持|参与).{0,20}(?:基金|项目|计划|专项|课题|任务)一项$"
    r"|^\d{5,12}\s*[,，、]\s*\d+(?:\.\d+)?\s*(?:万|万元|元)$"
    r"|^(?:国家|中国|美国|广东省|深圳市|山东省).{0,30}"
    r"(?:基金|项目|计划|专项|课题|任务)"
    r"(?:\s*(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2})?$",
    re.IGNORECASE,
)
_CONTACT_PROFILE_FRAGMENT_RE = re.compile(
    r"^(?:e-?mail|邮箱|电子邮件)\s*[:：]?\s*\S+@\S+$",
    re.IGNORECASE,
)
_CJK_TEACHING_GUIDANCE_AWARD_RE = re.compile(
    r"^指导.{0,30}(?:大学生|本科生|研究生).{0,80}"
    r"(?:优秀|获奖|校级|院级|毕业设计|创新创业训练计划).*$"
)
_CJK_TALENT_TITLE_FRAGMENT_RE = re.compile(
    r"^.{0,40}(?:英才|人才).{0,24}"
    r"(?:[A-Z]\s*类人才|类人才|高层次人才|青年人才).{0,40}$"
)
_CJK_PROJECT_GRANT_AWARD_FRAGMENT_RE = re.compile(
    r"^(?:近年来)?.{0,40}(?:教师考评优秀|年度教师考评优秀).*$"
    r"|^符合条件的博士后人员.*(?:补助|人才支持项目).*$"
    r"|^.{0,80}(?:科研启动经费|科技合作项目|平台建设项目|"
    r"青年科技启明星人才计划|人才支持项目).{0,80}$"
    r"|^.{0,80}(?:基金|项目|计划|经费)[,，(（].{0,120}"
    r"(?:立项|结题|已结题|[A-Z]{1,8}\d{3,}|[A-Z]?\d{4,}).*$",
    re.IGNORECASE,
)
_CJK_PROJECT_YEAR_RANGE_FRAGMENT_RE = re.compile(
    r"^.{0,40}(?:基金|项目|计划|专项|课题)\s+"
    r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}$"
)
_CJK_RESEARCH_INTEREST_PROSE_RE = re.compile(
    r"^(?:近[一二三四五六七八九十0-9]+年|当前|目前).{0,30}"
    r"研究(?:工作|兴趣|方向|领域).{0,80}"
    r"(?:集中在|主要集中在|包括|围绕).{0,100}(?:方面|方向|领域)$"
)
_CJK_PROFILE_TEACHING_RESEARCH_PROSE_RE = re.compile(
    r"^(?:主要|长期|目前|当前)?(?:从事|承担).{0,80}"
    r"(?:教学科研工作|科研工作|教学工作|课程).*$"
)
_CJK_EDUCATION_BIO_THESIS_RESIDUE_RE = re.compile(
    r"^(?:[\u4e00-\u9fffA-Za-z0-9/-]{2,80})\s+"
    r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}"
    r".{0,80}(?:获.{0,20}学位|学位论文|博士|硕士|学士).{0,160}$"
)
_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_INITIAL_RE = re.compile(r"[A-Z]\.")
_CAPITALIZED_RE = re.compile(r"[A-Z][a-z]+(?:[-'][A-Z][a-z]+)*")
_UPPER_RE = re.compile(r"[A-Z]{2,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TRUNCATED_TRAILING_PAREN_RE = re.compile(r"\([A-Za-z0-9]{1,3}$")
_BROKEN_LETTER_SPACING_RE = re.compile(r"\b[A-Z]\s+[a-z]{1,12}\b")
_BOOK_OR_TRANSLATION_RECORD_RE = re.compile(
    r"^[\u4e00-\u9fffA-Za-z·.\s、，,]{1,30}"
    r"(?:主编|主译|编著|选编|译|著)[《『「].{2,200}[》』」]"
)
_CITATION_TAIL_RE = re.compile(
    r"(?:[\"”’][《『「].{2,80}[》』」].{0,80}"
    r"(?:\b(?:19|20)\d{2}\b|第\s*\d+\s*[卷期]|Vol\.?|No\.?\s*\d+|pp?\.?))"
    r"|(?:\b(?:19|20)\d{2}\b.{0,80}\b(?:Vol\.?|No\.?\s*\d+|pp?\.?)\b)"
    r"|(?:\b(?:Vol\.?|No\.?\s*\d+|pp?\.?)\b.{0,80}\b(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)
_COMMA_WITH_AUTHOR_TAIL_RE = re.compile(
    r",\s*with\s+[A-Z][A-Za-z.-]+(?:\s+[A-Z][A-Za-z.-]+){0,4}\b",
    re.IGNORECASE,
)
_MONTH_YEAR_FRAGMENT_RE = re.compile(
    r"^(?:\d{1,4}|[A-Z][A-Za-z .&-]{2,80}),\s*"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?)\s+(?:19|20)\d{2}$",
    re.IGNORECASE,
)
_PUBLISHER_YEAR_FRAGMENT_RE = re.compile(
    r"^(?:Elsevier|Springer|Wiley|IEEE|ACM|CRC\s+Press|"
    r"Cambridge\s+University\s+Press|Oxford\s+University\s+Press|"
    r"Taylor\s*&\s*Francis|Nature\s+Publishing\s+Group|MDPI|"
    r"Frontiers|ScienceDirect),?\s*(?:19|20)\d{2}$",
    re.IGNORECASE,
)
_PUBLISHER_SERIES_VOLUME_FRAGMENT_RE = re.compile(
    r"^(?:Springer)\s+(?:LNCS|LNAI|CCIS)\s+\d{2,6}$",
    re.IGNORECASE,
)
_KNOWN_VENUE_ONLY_TITLES = {
    "applied catalysis b: environmental",
    "autonomous agents and multi-agent systems (jaamas)",
    "acm transactions on evolutionary learning and optimization",
    "ieee transactions on knowledge and data engineering (tkde)",
    "international journal of human-computer studies",
    "palaeogeography, palaeoclimatology",
    "sci. china chem",
    "sensors and actuators b: chemical",
}
_KNOWN_PROFILE_NOISE_TITLES = {
    "the waterfront of toronto, canada",
    "创意向善 设计为众/innovation for good - design for all",
    "近五年的研究工作集中在协作与人机交互方面",
    "当前研究兴趣主要集中在数据驱动设计、人工智能辅助设计和可持续设计方面",
}
_WESTERN_NAME_WORD_RE_PART = r"[A-Z][A-Za-z'’.-]+(?:-[A-Z][A-Za-z'’.-]+)?"
_STANDALONE_PERSON_ALIAS_RE = re.compile(
    rf"^{_WESTERN_NAME_WORD_RE_PART}\s+"
    rf"\({_WESTERN_NAME_WORD_RE_PART}(?:\s+{_WESTERN_NAME_WORD_RE_PART}){{0,2}}\)"
    rf"\s+{_WESTERN_NAME_WORD_RE_PART}$"
)
_EDITOR_RECORD_RE = re.compile(
    r"^[A-Z][A-Za-z.\-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z.\-]+"
    r"(?:\s+[A-Z][A-Za-z.\-]+){0,2}|(?:\s+[A-Z][A-Za-z.\-]+){1,3})"
    r"\s*\((?:ed\.?|eds\.?|editor(?:s)?)\)\.?$",
    re.IGNORECASE,
)
_TRUNCATED_VENUE_TAIL_RE = re.compile(
    r"\.\.\.,\s*[^,]{2,80},\s*(?:vol|no|pp?|doi|q[1-4])\.?\s*$",
    re.IGNORECASE,
)
_PROFILE_OR_SERVICE_PROSE_RE = re.compile(
    r"(?:\bhas\s+published\s+over\s+\d+\s+articles\b|"
    r"\b(?:he|she|they)\s+received\s+(?:his|her|their)?\s*"
    r"(?:B\.?S\.?|M\.?S\.?|Ph\.?D\.?|degree)\b|"
    r"\bselected\s+professional\s+activities\b|"
    r"\breviewer\s+for\s+[A-Z]{2,}\b|"
    r"\bselected\s+service\b|"
    r"\bresearch\s+interests\b|"
    r"\bresearch\s+interests\s+include\b|"
    r"\bhigh-level\s+professional\s+talent\b|"
    r"\b(?:senior\s+)?pc\s+member\b|"
    r"\barea\s+chair\b|"
    r"\bprogram\s+committee\b|"
    r"\b(?:master|phd|doctoral)\s+(?:student|supervisor)\b|"
    r"\b(?:first\s+author|co-?first\s+author)\s+published\b)",
    re.IGNORECASE,
)
_CJK_PROFILE_OR_SERVICE_SNIPPET_RE = re.compile(
    r"(?:\d{2}级(?:硕士|博士|本科)|第一作者发表|通讯作者发表|学生发表|"
    r"博士生|硕士生|本科生|高层次.{0,8}人才|程序委员会委员|"
    r"全球前\s*\d+%?\s*顶尖科学家|高级会员|第一发明人|"
    r"一流本科课程|教学获奖|教学教改|研制者|"
    r"历任.{0,30}(?:学会|委员会).{0,12}(?:主任|委员))",
    re.IGNORECASE,
)
_CJK_GROUP_HOMEPAGE_NAVIGATION_RE = re.compile(
    r"(?:详见|参见|查看|访问).{0,40}(?:课题组|实验室|主页|首页|网站)|"
    r"(?:课题组|实验室).{0,30}(?:情况|成员|介绍).{0,40}(?:主页|首页|网站)"
)
_PATENT_RECORD_RE = re.compile(
    r"(?:"
    r"(?:授权)?(?:发明)?专利\s*$|"
    r"\bPCT/[A-Z]{2}\d{4}/\d{4,}\b|"
    r"\bpatent\s+(?:no|number)\.?\s*[:：]?\s*[A-Z]{0,4}\s*\d|"
    r"\bpatent\s+NO\.?\s*[:：]?|"
    r"\bZL\s*\d|"
    r"ZL\d|"
    r"(?:发明人|授权|专利号).{0,80}(?:ZL|\d{6,})"
    r")",
    re.IGNORECASE,
)
_PATENT_APPLICATION_NUMBER_TAIL_RE = re.compile(
    r"[\u4e00-\u9fff].*[,，]\s*(?:19|20)\d{9,12}(?:\.\d+)?\s*$"
)
_ENGLISH_PATENT_TITLE_RE = re.compile(
    r"^(?:method|device|apparatus|system)\s+and\s+"
    r"(?:method|device|apparatus|system)\s+for\b",
    re.IGNORECASE,
)
_CJK_PATENT_LIKE_TITLE_RE = re.compile(
    r"^(?:一种)?[\u4e00-\u9fff\d]{2,28}(?:处理|分类|渲染|训练)方法$"
    r"|^(?:一种)?[\u4e00-\u9fff\d]{2,40}(?:方法及装置|方法和装置|方法以及相关装置|方法、装置)"
    r"|^.{2,60}(?:装置及存储介质|计算机设备|存储介质)$"
    r"|^基于.{2,60}(?:方法及装置|方法、装置|模型训练方法及装置|模型训练方法以及相关装置)$"
    r"|^一种用于.{2,40}机器人辅助.{2,20}系统研究$"
)
_BOOK_CHAPTER_FRAGMENT_RE = re.compile(
    r"(?:\(\s*chapter\s+\d+\s*$|\bchapter\s+\d+\s*$)",
    re.IGNORECASE,
)
_PAPER_LIST_PROFILE_NAV_RE = re.compile(
    r"^full\s+paper\s+list\s+available\s+at\s+my\s+(?:google|goolge)\s+scholar$",
    re.IGNORECASE,
)
_VENUE_ARTICLE_NUMBER_TAIL_RE = re.compile(
    r"(?:[:,])\s*[A-Z][A-Za-z&.\s-]{6,80},\s*(?:[A-Za-z]?\d{5,}|\d+\(\d+\):[\d–—-]+)\s*(?:\((?:19|20)\d{2}\))?$",
    re.IGNORECASE,
)
_VENUE_VOLUME_FRAGMENT_TAIL_RE = re.compile(
    r"(?:\bACS\s*Nano\s*\d+\s*\(\d+\)$|"
    r"\bACS\s+Photonics\s+\d+\s*$)",
    re.IGNORECASE,
)
_VENUE_VOLUME_PAGE_YEAR_TAIL_RE = re.compile(
    r",\s*[A-Z][A-Za-z.&\s]{2,80}\.{1,2}\s+"
    r"\d+\(\d+\):[\d–—-]+\s*\((?:19|20)\d{2}\)$",
    re.IGNORECASE,
)
_SITE_NAVIGATION_TAIL_RE = re.compile(
    r"(?:继续了解\s*>>|本科招生|人才招聘|科研平台|招生简章|联系我们)"
)
_PUBLICATION_SECTION_HEADING_RE = re.compile(
    r"^(?:selected\s+(?:list|examples?\s+of\s+"
    r"(?:recent\s+publications|invited\s+review\s+articles))|"
    r"representative\s+works?)"
    r"(?:\s*\([^)]{1,80}\))?$",
    re.IGNORECASE,
)
_AUTHOR_LEGEND_OR_NOTE_RE = re.compile(
    r"^(?:note\s*:\s*)?(?:"
    r".*\b(?:equal\s+contributions?|co-?first\s+authors?|"
    r"co-?corresponding\s+authors?|correspondence\s+author)\b.*|"
    r"\(\*+\s*correspondence\s+author\))$",
    re.IGNORECASE,
)
_STANDALONE_INSTITUTION_RE = re.compile(
    r"^(?:[A-Z][A-Za-z&.'-]+|[A-Z]{2,})"
    r"(?:\s+(?:[A-Z][A-Za-z&.'-]+|of|and|the|for|[A-Z]{2,})){0,6}"
    r"\s+(?:University|College|Institute|School|Hospital|Academy|"
    r"Laborator(?:y|ies)|Lab|Center|Centre|Department)\.?$"
)
_PROFILE_TIMELINE_FRAGMENT_RE = re.compile(
    r"^(?:after|before|since|prior\s+to)\s+(?:joining|working\s+at|"
    r"moving\s+to|arriving\s+at)\b",
    re.IGNORECASE,
)
_VOLUME_PAGE_FRAGMENT_RE = re.compile(
    r"^(?:\d+\s*\(\s*[A-Za-z0-9-]+\s*\)\s*:\s*"
    r"(?:[A-Za-z]?\d+[A-Za-z0-9-]*|[A-Za-z]{2,8}\d+[A-Za-z0-9-]*)|"
    r"no\.?\s*\d+\s*,\s*pp\.?|"
    r"pp?\.?\s*[\d\s-]+)$",
    re.IGNORECASE,
)
_LEADING_VOLUME_PAGE_FRAGMENT_RE = re.compile(
    r"^vol\.?\s*\d+\s*,\s*no\.?\s*\d+\s*,\s*pp\.?\s*[\d\s-]+$",
    re.IGNORECASE,
)
_AUTHOR_JOURNAL_VOLUME_FRAGMENT_RE = re.compile(
    r"^[A-Z][A-Za-z'’-]+,\s*"
    r"(?:[A-Z][A-Za-z]*\.?\s*){1,8},\s*"
    r"Vol\.?\s*\d+\b",
    re.IGNORECASE,
)
_INLINE_CITATION_MARKER_RE = re.compile(r"\[[A-Z](?:/[A-Z]+)+\]//")
_VENUE_VOLUME_PAGE_TAIL_RE = re.compile(
    r",\s*(?:IEEE|ACM|IET|IEE|Elsevier|Springer|Wiley|Nature|Science|"
    r"[A-Z][A-Za-z]*\.\s*(?:[A-Z][A-Za-z]*\.\s*){1,8})"
    r".{0,120}\bvol\.?\s*\d+.{0,120}\bpp\.?\s*[\d\s-]+",
    re.IGNORECASE,
)
_EMBEDDED_VENUE_METADATA_TAIL_RE = re.compile(
    r"(?:,|\.)\s*(?:"
    r"(?:IEEE|ACM)\s+Trans\.|"
    r"Proc\.\s+VLDB\s+Endow|"
    r"BMC\s+bioinformatics|"
    r"J\.\s+d[’']Analyse\s+Math|"
    r"Comm(?:\.|unications?)?\b"
    r").{0,80}(?:\bvol\.?\s*\d+|\b\d+\s*,\s*[\d-]+|\b\d+\(\d+\)|$)",
    re.IGNORECASE,
)
_AUTHOR_PREFIX_METADATA_RE = re.compile(
    r"^(?:[A-Z][a-z]+|[A-Z][a-z]+\s+[A-Z][a-z]+)[：:].{10,}"
    r"(?:\bProc\.|\bEndow\b|\bBMC\b|\bbioinformatics\b|"
    r"\bmethodological\s+review\b|\bQuery\s+Processing\b)",
    re.IGNORECASE,
)
_WITH_COAUTHOR_PREFIX_RE = re.compile(
    r"^\(with\s+[^)]{3,80}\)\s+.{10,},\s*[A-Z][A-Za-z. ]{2,20}$",
    re.IGNORECASE,
)
_TRUNCATED_TITLE_END_RE = re.compile(
    r"(?:\b(?:of|for|with|without|into|using|via|and|or|by)\b|"
    r"\bminimum-energy)$",
    re.IGNORECASE,
)
_LOW_INFORMATION_ANALYSIS_FRAGMENT_RE = re.compile(
    r"^in-[a-z]{3,20}\s+analysis$",
    re.IGNORECASE,
)
_TRUNCATED_GUIDELINE_BODY_PART_RE = re.compile(
    r"\bguidelines?\s+for\s+the\s+diagnosis\s+and\s+treatment\s+of\s+"
    r"(?:hand|foot|mouth|skin|eye|ear)$",
    re.IGNORECASE,
)
_CJK_PROJECT_PROFILE_RESIDUE_RE = re.compile(
    r"^(?:\d{1,3}[：:].*[\(（]\d{6,}[\)）]|"
    r".{0,40}(?:假肢手|多模态视觉跟踪).{0,80}(?:技术研究|方法研究).{0,80}|"
    r".{0,40}获得.{0,40}(?:竞赛冠军|奖).{0,40}|"
    r"(?:理论与实际相结合|率先设计|研制了).{4,80})$"
)
_TRUNCATED_JOURNAL_ABBREV_TAIL_RE = re.compile(
    r"[\"'“”]\s+[A-Z]\.\s*[A-Za-z]{2,}\.?$"
)
_JOURNAL_DATE_DOI_RECORD_RE = re.compile(
    r"^[A-Z][A-Za-z.-]{2,40}\.\s+(?:19|20)\d{2}\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"\d{1,2};\s*\d+(?:\(\d+\))?:[\d–—-]+\.?\s+doi:\s*10\.\S+$",
    re.IGNORECASE,
)
_ISSUE_PAGE_FRAGMENT_RE = re.compile(
    r"^Iss\s+\d+\s*\([A-Za-z]{3,9}\)\s+pp?\.?\s*[\d\s–—-]+$",
    re.IGNORECASE,
)
_JOURNAL_ABBREV_VOLUME_ARTICLE_FRAGMENT_RE = re.compile(
    r"^[A-Z][A-Za-z.]{2,12}\.?\s+\d{1,4}\.?\s+"
    r"[A-Za-z]?\d{2,8}\s*\((?:19|20)\d{2}\)$",
    re.IGNORECASE,
)
_KNOWN_JOURNAL_VOLUME_ARTICLE_FRAGMENT_RE = re.compile(
    r"^(?:Nature\s+Communications)\s+\d{1,4}\s*,\s*"
    r"[A-Za-z]?\d{2,8}$",
    re.IGNORECASE,
)
_SHORT_VENUE_ONLY_FRAGMENT_RE = re.compile(
    r"^(?:ACS\s+Energy\s+Lett|ACS\s+na\s+no\s+(?:19|20)\d{2})$",
    re.IGNORECASE,
)
_CJK_JOINT_LAB_OR_PROJECT_RESIDUE_RE = re.compile(
    r"^.{0,80}(?:联合实验室|重点实验室|工程中心).{0,80}$"
)
_AUTHOR_LIST_WITH_VENUE_VOLUME_RE = re.compile(
    r"^(?:[A-Z]\.\s*[A-Z][A-Za-z-]+(?:\s+\d+)?,\s*){3,}"
    r".{0,120}\b(?:ACS|IEEE|ACM|Nano|Trans\.)\b.{0,80}\bVol\.?\s*\d+",
    re.IGNORECASE,
)
_CJK_PAGE_TAIL_RE = re.compile(r"第\s*\d+\s*[-–—]\s*\d+\s*页")
_CJK_PARTIAL_PUBLICATION_NOTE_RE = re.compile(r"部分(?:英文|中文)?发表")
_STANDALONE_VENUE_LINE_RE = re.compile(
    r"^(?=.{8,120}$)(?:"
    r"Conference\s+(?:of|on)\s+.*(?:\([A-Z0-9/-]{2,30}\))?"
    r"|"
    r"(?:IEEE|ACM|AAAI|IJCAI|CVPR|ICCV|ECCV|NeurIPS|ICML|ACL|EMNLP|"
    r"IEEE/CVF)\b.*\b(?:Conference|Proceedings|Workshop|Symposium)\b.*"
    r"(?:,\s*(?:19|20)\d{2})?|"
    r".*\bConference\s+on\b.*(?:,\s*(?:19|20)\d{2})?|"
    r"(?:Proceedings\s+of\s+the\s+)?[A-Z][A-Za-z&/ .'-]{3,80}"
    r"(?:Conference|Proceedings|Symposium|Workshop)(?:\s*\([A-Z0-9/-]{2,20}\))?"
    r"(?:,\s*(?:19|20)\d{2})?"
    r")$",
    re.IGNORECASE,
)
_STANDALONE_JOURNAL_OR_TRANSACTIONS_RE = re.compile(
    r"^(?=.{16,140}$)(?:"
    r"(?:[A-Z][A-Za-z&.'–—-]+(?:\s+|$)){0,4}"
    r"(?:Journal|Transactions?|Letters|Proceedings)"
    r"\s+(?:of|on|in|for)\s+"
    r"[A-Z][A-Za-z0-9&.'’:/,–— -]{6,120}"
    r"|"
    r"(?:IEEE|ACM|AAAI|IJCAI|SIAM|INFORMS|Elsevier|Springer|Nature|Science)"
    r"\s+(?:Transactions?|Journal|Letters|Proceedings)\s+"
    r"(?:on|of|in|for)\s+"
    r"[A-Z][A-Za-z0-9&.'’:/,–— -]{6,120}"
    r")$",
    re.IGNORECASE,
)
_STANDALONE_ACRONYM_VENUE_CHAIN_RE = re.compile(
    r"^(?:[A-Z][A-Z0-9]{2,}(?:/[A-Z][A-Z0-9]{2,}){1,5})$",
    re.IGNORECASE,
)
_LONG_STANDALONE_VENUE_HEADING_RE = re.compile(
    r"^(?:Annual\s+)?Conference\s+(?:of|on)\s+.+(?:\([A-Z0-9/-]{2,30}\))$",
    re.IGNORECASE,
)
_CJK_EDUCATION_PROJECT_FRAGMENT_RE = re.compile(
    r"^主持.{0,30}(?:自然科学基金|基金|产学研|教改|协同育人|教育部|省级).{0,80}"
    r"(?:项目|课题)\d+项.*$"
)
_LOST_BOUNDARY_MULTI_TITLE_RE = re.compile(
    r"[a-z][A-Z](?:n|he)\s+[A-Za-z][A-Za-z-]+.{40,}"
)
_DEGREE_RECORD_TAIL_RE = re.compile(
    r",\s*(?:Ph\.?\s*D|M\.?\s*S|MSc|BSc|MA|MBA)\.?$",
    re.IGNORECASE,
)
_STANDALONE_SINGLE_WORD_FRAGMENT_RE = re.compile(r"^[A-Za-z]{8,}$")
_COURSE_OR_TEXTBOOK_FRAGMENT_RE = re.compile(
    r"^(?:[A-Z][A-Za-z0-9&'-]*\s+){1,5}(?:Course|Textbook|Syllabus)$",
    re.IGNORECASE,
)
_MOJIBAKE_ROMAN_NAME_FRAGMENT_RE = re.compile(
    r"^(?:[A-Z][A-Za-z]+\s+[A-Z]？[A-Za-z]+|[A-Z]？[A-Za-z]+\s+[A-Z][A-Za-z]+)$"
)
_MOJIBAKE_ROMAN_NAME_SEGMENT_RE = re.compile(
    r"^(?:"
    r"[A-Z][A-Za-z'’.-]+\s+[A-Z]？[A-Za-z'’.-]+|"
    r"[A-Z]？[A-Za-z'’.-]+\s+[A-Z][A-Za-z'’.-]+|"
    r"[A-Z][A-Za-z'’.-]*？[A-Za-z'’.-]+"
    r"(?:\s+[A-Z][A-Za-z'’.-]+){0,2}|"
    r"[A-Z][A-Za-z'’.-]+(?:\s+[A-Z][A-Za-z'’.-]+){0,2}"
    r")\*?$"
)
_AUTHOR_STAR_PREFIX_FRAGMENT_RE = re.compile(
    r"^[A-Z][A-Za-z]+(?:[A-Z][a-z]+)?(?:\s+[A-Z]\s+[a-z])?"
    r"\s*\*?\.?\*\.?\s+[A-Z][A-Za-z].{20,}$"
)
_TRAILING_AUTHOR_STAR_TAIL_RE = re.compile(
    r"\s+[A-Z][A-Za-z'’.-]+\s+[A-Z][A-Za-z'’.-]+\*+$"
)
_YEAR_ORG_AUTHOR_FRAGMENT_RE = re.compile(
    r"^(?:19|20)\d{2}\s+[A-Z][A-Za-z&.-]{2,40}:\s+"
    r"[A-Z][A-Za-z'’.-]+\*+(?:,\s*[A-Z][A-Za-z'’.-]+\*+)*$"
)
_LEADING_ETC_TITLE_FRAGMENT_RE = re.compile(r"^etc,\s+[A-Z].{20,}$", re.IGNORECASE)
_TRUNCATED_VOLUME_PAREN_TAIL_RE = re.compile(
    r"\(\s*vol(?:ume)?\.?\s+\d{1,4}$",
    re.IGNORECASE,
)
_COMMON_PINYIN_SURNAME_TOKENS = {
    "bai",
    "cao",
    "chen",
    "deng",
    "fan",
    "gao",
    "guo",
    "han",
    "he",
    "huang",
    "jiang",
    "li",
    "liang",
    "lin",
    "liu",
    "lu",
    "luo",
    "ma",
    "pi",
    "qian",
    "shen",
    "song",
    "sun",
    "tang",
    "wang",
    "wu",
    "xiao",
    "xie",
    "xu",
    "yang",
    "yu",
    "zhai",
    "zhang",
    "zhao",
    "zhou",
    "zhu",
}
_AUTHOR_PREFIX_TECHNICAL_PHRASE_TOKENS = {
    "adaptive",
    "adversarial",
    "camera",
    "childhood",
    "clinical",
    "classification",
    "data",
    "deep",
    "detection",
    "dermatitis",
    "binder",
    "cell",
    "control",
    "cooling",
    "efficiency",
    "electric",
    "engineering",
    "energy",
    "environmental",
    "estimation",
    "exposure",
    "efficacy",
    "fast",
    "fuel",
    "fusion",
    "high",
    "hybrid",
    "image",
    "joint",
    "learning",
    "matrices",
    "management",
    "microbiome",
    "mini",
    "model",
    "models",
    "motion",
    "network",
    "networks",
    "nonlinear",
    "object",
    "optimization",
    "oxygen",
    "parameters",
    "point",
    "proton",
    "propulsion",
    "radar",
    "range",
    "representation",
    "rank",
    "signal",
    "signals",
    "smoothing",
    "splines",
    "structured",
    "supervisor",
    "symmetry",
    "target",
    "targets",
    "transfer",
    "transport",
    "using",
    "via",
}


def _normalize(title: str) -> str:
    return _WHITESPACE_RE.sub(" ", title.replace("\ufeff", " ")).strip()


def _is_name_token(token: str) -> bool:
    return bool(
        _INITIAL_RE.fullmatch(token)
        or _CAPITALIZED_RE.fullmatch(token)
        or _UPPER_RE.fullmatch(token)
    )


def _looks_like_first_last(segment: str) -> bool:
    if "," in segment:
        return False
    tokens = segment.split()
    if not 2 <= len(tokens) <= 4:
        return False
    if not all(_is_name_token(token) for token in tokens):
        return False
    return any(_CAPITALIZED_RE.fullmatch(token) for token in tokens)


def _looks_like_lastname_first(segment: str) -> bool:
    if segment.count(",") != 1:
        return False
    last, first = (part.strip() for part in segment.split(",", 1))
    if not last or not first:
        return False
    last_tokens = last.split()
    first_tokens = first.split()
    if not 1 <= len(last_tokens) <= 3 or not 1 <= len(first_tokens) <= 3:
        return False
    if not all(_is_name_token(token) for token in last_tokens + first_tokens):
        return False
    return any(_CAPITALIZED_RE.fullmatch(token) for token in last_tokens + first_tokens)


def _looks_like_author_segment(segment: str) -> bool:
    cleaned = segment.strip().strip("()[]{}")
    cleaned = cleaned.rstrip(".")
    cleaned = cleaned.replace("…", "").replace("...", "").strip()
    if not cleaned:
        return False
    return _looks_like_lastname_first(cleaned) or _looks_like_first_last(cleaned)


def _count_author_like_segments(title: str, separator: str) -> int:
    parts = [part.strip() for part in title.split(separator)]
    return sum(1 for part in parts if _looks_like_author_segment(part))




def _looks_like_comma_author_list(title: str) -> bool:
    if title.count(", ") < 3:
        return False
    parts = [part.strip() for part in title.split(",")]
    if len(parts) < 4:
        return False
    author_like = [part for part in parts if _looks_like_author_segment(part)]
    return len(author_like) >= 4 and len(author_like) >= len(parts) - 1


def _looks_like_editorial_bio(title: str) -> bool:
    return bool(_EDITORIAL_ROLE_RE.search(title) and len(_ACRONYM_RE.findall(title)) >= 2)


def _looks_like_project_status_noise(title: str) -> bool:
    return bool(_CJK_RE.search(title) and _PROJECT_STATUS_NOISE_RE.search(title))


def _looks_like_short_author_fragment(title: str) -> bool:
    if title.count(",") != 1:
        return False
    left, right = (part.strip() for part in title.split(",", 1))
    if not left or not right:
        return False
    if len(title.split()) > 5:
        return False
    right_is_name = _looks_like_author_segment(right) or _is_name_token(
        right.rstrip(".")
    )
    return _looks_like_first_last(left) and right_is_name


def _looks_like_initial_lastname_pair(segment: str) -> bool:
    return bool(
        re.fullmatch(
            r"[A-Z]\.?\s+[A-Z][A-Za-z'’.-]+",
            segment.strip().rstrip("."),
        )
    )


def _looks_like_single_lastname_author_fragment(title: str) -> bool:
    if title.count(",") != 1:
        return False
    left, right = (part.strip().rstrip(".") for part in title.split(",", 1))
    if not left or not right:
        return False
    if len(title.split()) > 4:
        return False
    if _looks_like_initial_lastname_pair(left) and _looks_like_initial_lastname_pair(
        right
    ):
        return True
    return _is_name_token(left) and _looks_like_first_last(right)


def _looks_like_short_pinyin_author_chain(title: str) -> bool:
    if not re.search(r"[,，、]", title):
        return False
    parts = [part.strip().rstrip(".") for part in re.split(r"[,，、]", title)]
    parts = [part for part in parts if part]
    if not 2 <= len(parts) <= 4:
        return False
    for part in parts:
        tokens = part.split()
        if not 1 <= len(tokens) <= 2:
            return False
        if not all(_is_name_token(token) for token in tokens):
            return False
        if not any(token.casefold() in _COMMON_PINYIN_SURNAME_TOKENS for token in tokens):
            return False
    return True


def _looks_like_broken_letter_spacing(title: str) -> bool:
    matches = _BROKEN_LETTER_SPACING_RE.findall(title)
    if len(matches) < 3:
        return False
    return len(matches) >= max(3, len(title.split()) // 5)


def _author_prefix_has_name_signal(*segments: str) -> bool:
    tokens = {
        token.casefold().rstrip(".")
        for segment in segments
        for token in segment.split()
    }
    return bool(tokens & _COMMON_PINYIN_SURNAME_TOKENS)


def _looks_like_author_prefixed_citation_record(title: str) -> bool:
    and_prefix = re.match(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+and\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(.{20,})",
        title,
    )
    if and_prefix:
        left, right, rest = and_prefix.groups()
        candidate_author_tokens = {
            token.lower() for token in (*left.split(), *right.split())
        }
        if candidate_author_tokens & _AUTHOR_PREFIX_TECHNICAL_PHRASE_TOKENS:
            return False
        if (
            all(_looks_like_first_last(segment) for segment in (left, right))
            and _author_prefix_has_name_signal(left, right)
            and not re.match(
                r"^(?:by|via|with|for|in|on|of|to|from|using|based)\b",
                rest,
                re.IGNORECASE,
            )
        ):
            return True
    return bool(
        re.match(
            r"^[A-Z][A-Za-z.-]+\s+[A-Z][A-Za-z.-]+,\s+"
            r"[A-Z][A-Za-z.-]+\s+[A-Z][A-Za-z.-]+ .{20,}",
            title,
        )
        and _CITATION_TAIL_RE.search(title)
    )


def _looks_like_author_prefixed_title_record(title: str) -> bool:
    if title.count(",") != 1:
        return False
    left, right = (part.strip() for part in title.split(",", 1))
    if not _looks_like_first_last(left):
        return False
    if len(right) < 40:
        return False
    return bool(
        re.match(
            r"^(?:A|An|The|Using|Based|Towards?|Toward|From|On|In|For)\b",
            right,
            re.IGNORECASE,
        )
    )


def _looks_like_standalone_person_name(title: str) -> bool:
    tokens = title.split()
    if len(tokens) != 2:
        return False
    first, second = tokens
    return first.isupper() and first.isalpha() and _CAPITALIZED_RE.fullmatch(second)


def _looks_like_hyphenated_person_name(title: str) -> bool:
    tokens = title.split()
    if len(tokens) != 2:
        return False
    if not any("-" in token for token in tokens):
        return False
    if any(
        token.casefold()
        in {
            "analysis",
            "control",
            "detection",
            "learning",
            "method",
            "model",
            "network",
            "optimization",
            "recognition",
            "system",
        }
        for token in tokens
    ):
        return False
    return all(_CAPITALIZED_RE.fullmatch(token) for token in tokens)


def _looks_like_and_joined_person_names(title: str) -> bool:
    if " and " not in title:
        return False
    parts = [part.strip() for part in title.split(" and ")]
    if len(parts) != 2:
        return False
    if sum(len(part.split()) for part in parts) > 5:
        return False
    if not all(_looks_like_first_last(part) for part in parts):
        return False
    return True


def _looks_like_standalone_pinyin_name_fragment(title: str) -> bool:
    tokens = title.split()
    if len(tokens) == 3 and tokens[-1].isdigit():
        tokens = tokens[:2]
    if len(tokens) != 2:
        return False
    if not all(_CAPITALIZED_RE.fullmatch(token) for token in tokens):
        return False
    return any(token.lower() in _COMMON_PINYIN_SURNAME_TOKENS for token in tokens)


def _looks_like_short_semicolon_author_fragment(title: str) -> bool:
    if ";" not in title or len(title) > 40:
        return False
    parts = [part.strip() for part in re.split(r"[;,；，]", title) if part.strip()]
    if len(parts) < 2:
        return False
    author_like = 0
    for part in parts:
        compact = part.replace(".", "").replace(" ", "")
        if re.fullmatch(r"[A-Z]{1,3}", compact):
            author_like += 1
            continue
        if _is_name_token(part.rstrip(".")):
            author_like += 1
            continue
        if _looks_like_author_segment(part):
            author_like += 1
    return author_like >= len(parts)


def _looks_like_mojibake_author_list(title: str) -> bool:
    if "？" not in title:
        return False
    parts = [part.strip() for part in re.split(r"[,，/]", title) if part.strip()]
    if not parts:
        return False
    if len(title) <= 30:
        return True
    if len(parts) == 1:
        return bool(_MOJIBAKE_ROMAN_NAME_SEGMENT_RE.fullmatch(parts[0]))

    author_like = 0
    for part in parts:
        cleaned = part.rstrip("*").strip()
        if _MOJIBAKE_ROMAN_NAME_SEGMENT_RE.fullmatch(part):
            author_like += 1
        elif _looks_like_author_segment(cleaned):
            author_like += 1
    return author_like == len(parts)


def _strip_author_markers(segment: str) -> str:
    cleaned = re.sub(r"\([^)]{0,12}\)", " ", segment)
    cleaned = re.sub(r"\d+", " ", cleaned)
    cleaned = cleaned.replace("*", " ")
    cleaned = cleaned.replace("&", " ")
    return _WHITESPACE_RE.sub(" ", cleaned).strip(" ,.;:")


def _looks_like_compact_author_segment(segment: str) -> bool:
    cleaned = _strip_author_markers(segment)
    if not cleaned:
        return False
    if _looks_like_author_segment(cleaned):
        return True
    if _looks_like_initial_lastname_pair(cleaned):
        return True
    tokens = cleaned.split()
    if len(tokens) == 1:
        return bool(_CAPITALIZED_RE.fullmatch(tokens[0]))
    if len(tokens) == 2:
        return all(_is_name_token(token) for token in tokens)
    return False


def _looks_like_author_list_prefix_before_title(title: str) -> bool:
    if title.count(",") < 2:
        return False
    marker = re.search(r"\*\.?\s+[A-Z][A-Za-z-]+", title)
    if not marker:
        return False
    prefix = title[: marker.start()]
    rest = title[marker.end() :].strip()
    if len(rest) < 20:
        return False
    parts = [part.strip() for part in prefix.split(",") if part.strip()]
    if len(parts) < 3:
        return False
    author_like = sum(1 for part in parts if _looks_like_compact_author_segment(part))
    return author_like >= 3 and author_like >= len(parts) - 1


def _looks_like_starred_author_prefix_before_title(title: str) -> bool:
    return bool(
        re.match(
            r"^[A-Z][A-Za-z'’.-]+\s+[A-Z][A-Za-z'’.-]+\*?&\s*"
            r"[A-Z][A-Za-z'’.-]+\s+[A-Z][A-Za-z'’.-]+\*?\.\s+"
            r"[A-Z][A-Za-z].{20,}$",
            title,
        )
    )


def _looks_like_title_with_comma_author_tail(title: str) -> bool:
    if title.count(",") < 4:
        return False
    parts = [part.strip() for part in title.split(",") if part.strip()]
    if len(parts) < 5 or len(parts[0]) < 30:
        return False

    ignorable_tail = {"in press", "the"}
    for index in range(1, min(3, len(parts) - 2)):
        tail = parts[index:]
        relevant = [
            part
            for part in tail
            if _strip_author_markers(part).casefold() not in ignorable_tail
        ]
        if len(relevant) < 4:
            continue
        author_like = sum(
            1 for part in relevant if _looks_like_compact_author_segment(part)
        )
        if author_like >= 4 and author_like >= len(relevant) - 1:
            return True
    return False


def _looks_like_author_prefixed_title_with_star(title: str) -> bool:
    if "*." not in title or "." not in title:
        return False
    prefix, rest = title.split(".", 1)
    if len(rest.strip()) < 20:
        return False
    parts = [part.strip() for part in re.split(r"[,，&]", prefix) if part.strip()]
    if len(parts) < 2:
        return False
    author_like = sum(1 for part in parts if _looks_like_compact_author_segment(part))
    return author_like >= 2 and author_like >= len(parts) - 1


def _looks_like_slash_author_list(title: str) -> bool:
    if "/" not in title:
        return False
    parts = [part.strip() for part in title.split("/") if part.strip()]
    if len(parts) < 2:
        return False

    author_like = 0
    for part in parts:
        cleaned = part.rstrip("*").strip()
        if _looks_like_author_segment(cleaned):
            author_like += 1
            continue
        if len(cleaned.split()) == 1 and _CAPITALIZED_RE.fullmatch(cleaned):
            author_like += 1
    return author_like == len(parts)


def _looks_like_title_with_trailing_author_star(title: str) -> bool:
    match = _TRAILING_AUTHOR_STAR_TAIL_RE.search(title)
    if not match:
        return False
    prefix = title[: match.start()].strip()
    if len(prefix) < 50:
        return False
    return len(prefix.split()) >= 6


def _looks_like_known_venue_only_title(title: str) -> bool:
    return (
        title.replace("–", "-").replace("—", "-").casefold()
        in _KNOWN_VENUE_ONLY_TITLES
    )


def _looks_like_known_profile_noise_title(title: str) -> bool:
    return (
        title.replace("–", "-").replace("—", "-").casefold()
        in _KNOWN_PROFILE_NOISE_TITLES
    )


def is_plausible_paper_title(title: str | None) -> bool:
    """Return whether *title* looks like a real paper title."""
    if title is None:
        return False
    normalized = _normalize(str(title))
    if len(normalized) < 8 or len(normalized) > 300:
        return False
    if _REPRESENTATIVE_RESULT_PROSE_RE.match(normalized):
        return False
    if _JOURNAL_METRIC_FRAGMENT_RE.match(normalized):
        return False
    if _JOURNAL_METRIC_TAIL_RE.search(normalized):
        return False
    if _STANDALONE_SECTION_LABEL_RE.match(normalized):
        return False
    if _PUBLICATION_SECTION_LABEL_RE.match(normalized):
        return False
    if _LEADING_CITATION_YEAR_RE.match(normalized):
        return False
    if _YEAR_PREFIX_CITATION_METADATA_RE.search(normalized):
        return False
    if _CJK_PAGE_TAIL_RE.search(normalized):
        return False
    if _CJK_PARTIAL_PUBLICATION_NOTE_RE.search(normalized):
        return False
    if _MONTH_YEAR_FRAGMENT_RE.match(normalized):
        return False
    if _JOURNAL_DATE_DOI_RECORD_RE.match(normalized):
        return False
    if _ISSUE_PAGE_FRAGMENT_RE.match(normalized):
        return False
    if _JOURNAL_ABBREV_VOLUME_ARTICLE_FRAGMENT_RE.match(normalized):
        return False
    if _KNOWN_JOURNAL_VOLUME_ARTICLE_FRAGMENT_RE.match(normalized):
        return False
    if _SHORT_VENUE_ONLY_FRAGMENT_RE.match(normalized):
        return False
    if _PUBLISHER_YEAR_FRAGMENT_RE.match(normalized):
        return False
    if _PUBLISHER_SERIES_VOLUME_FRAGMENT_RE.match(normalized):
        return False
    if _CJK_RESEARCH_INTEREST_PROSE_RE.match(normalized):
        return False
    if _CJK_PROFILE_TEACHING_RESEARCH_PROSE_RE.match(normalized):
        return False
    if _looks_like_known_venue_only_title(normalized):
        return False
    if _looks_like_known_profile_noise_title(normalized):
        return False
    if _STANDALONE_VENUE_LINE_RE.match(normalized):
        return False
    if _STANDALONE_JOURNAL_OR_TRANSACTIONS_RE.match(normalized):
        return False
    if _STANDALONE_ACRONYM_VENUE_CHAIN_RE.match(normalized):
        return False
    if _LONG_STANDALONE_VENUE_HEADING_RE.match(normalized):
        return False
    if _STANDALONE_PERSON_ALIAS_RE.match(normalized):
        return False
    if _EDITOR_RECORD_RE.match(normalized):
        return False
    if _BOOK_OR_TRANSLATION_RECORD_RE.search(normalized):
        return False
    if _CITATION_TAIL_RE.search(normalized):
        return False
    if _TRUNCATED_VENUE_TAIL_RE.search(normalized):
        return False
    if _COMMA_WITH_AUTHOR_TAIL_RE.search(normalized):
        return False
    if _looks_like_author_prefixed_citation_record(normalized):
        return False
    if _looks_like_author_prefixed_title_record(normalized):
        return False
    if _looks_like_short_semicolon_author_fragment(normalized):
        return False
    if _PROFILE_OR_SERVICE_PROSE_RE.search(normalized):
        return False
    if _CJK_PROFILE_OR_SERVICE_SNIPPET_RE.search(normalized):
        return False
    if _CJK_GROUP_HOMEPAGE_NAVIGATION_RE.search(normalized):
        return False
    if _PATENT_RECORD_RE.search(normalized):
        return False
    if _PATENT_APPLICATION_NUMBER_TAIL_RE.search(normalized):
        return False
    if _ENGLISH_PATENT_TITLE_RE.match(normalized):
        return False
    if _CJK_PATENT_LIKE_TITLE_RE.search(normalized):
        return False
    if _BOOK_CHAPTER_FRAGMENT_RE.search(normalized):
        return False
    if _PAPER_LIST_PROFILE_NAV_RE.match(normalized):
        return False
    if _VENUE_ARTICLE_NUMBER_TAIL_RE.search(normalized):
        return False
    if _VENUE_VOLUME_FRAGMENT_TAIL_RE.search(normalized):
        return False
    if _VENUE_VOLUME_PAGE_YEAR_TAIL_RE.search(normalized):
        return False
    if _SITE_NAVIGATION_TAIL_RE.search(normalized):
        return False
    if _PUBLICATION_SECTION_HEADING_RE.match(normalized):
        return False
    if _AUTHOR_LEGEND_OR_NOTE_RE.match(normalized):
        return False
    if _STANDALONE_INSTITUTION_RE.match(normalized):
        return False
    if _PROFILE_TIMELINE_FRAGMENT_RE.match(normalized):
        return False
    if _VOLUME_PAGE_FRAGMENT_RE.match(normalized):
        return False
    if _LEADING_VOLUME_PAGE_FRAGMENT_RE.match(normalized):
        return False
    if _AUTHOR_JOURNAL_VOLUME_FRAGMENT_RE.match(normalized):
        return False
    if _INLINE_CITATION_MARKER_RE.search(normalized):
        return False
    if _VENUE_VOLUME_PAGE_TAIL_RE.search(normalized):
        return False
    if _EMBEDDED_VENUE_METADATA_TAIL_RE.search(normalized):
        return False
    if _AUTHOR_PREFIX_METADATA_RE.match(normalized):
        return False
    if _WITH_COAUTHOR_PREFIX_RE.match(normalized):
        return False
    if _LEADING_ETC_TITLE_FRAGMENT_RE.match(normalized):
        return False
    if _TRUNCATED_TITLE_END_RE.search(normalized):
        return False
    if _LOW_INFORMATION_ANALYSIS_FRAGMENT_RE.match(normalized):
        return False
    if _TRUNCATED_GUIDELINE_BODY_PART_RE.search(normalized):
        return False
    if _TRUNCATED_JOURNAL_ABBREV_TAIL_RE.search(normalized):
        return False
    if _AUTHOR_LIST_WITH_VENUE_VOLUME_RE.match(normalized):
        return False
    if _DEGREE_RECORD_TAIL_RE.search(normalized):
        return False
    if _STANDALONE_SINGLE_WORD_FRAGMENT_RE.match(normalized):
        return False
    if _COURSE_OR_TEXTBOOK_FRAGMENT_RE.match(normalized):
        return False
    if _YEAR_ORG_AUTHOR_FRAGMENT_RE.match(normalized):
        return False
    if _MOJIBAKE_ROMAN_NAME_FRAGMENT_RE.match(normalized):
        return False
    if _looks_like_mojibake_author_list(normalized):
        return False
    if _AUTHOR_STAR_PREFIX_FRAGMENT_RE.match(normalized):
        return False
    if _looks_like_author_list_prefix_before_title(normalized):
        return False
    if _looks_like_starred_author_prefix_before_title(normalized):
        return False
    if _looks_like_author_prefixed_title_with_star(normalized):
        return False
    if _looks_like_title_with_comma_author_tail(normalized):
        return False
    if _looks_like_slash_author_list(normalized):
        return False
    if _looks_like_title_with_trailing_author_star(normalized):
        return False
    if _TRUNCATED_VOLUME_PAREN_TAIL_RE.search(normalized):
        return False
    if _PUBLICATION_TABLE_EXCERPT_RE.search(normalized):
        return False
    if _CONTACT_PROFILE_FRAGMENT_RE.match(normalized):
        return False
    if _looks_like_project_status_noise(normalized):
        return False
    if _CJK_TEACHING_GUIDANCE_AWARD_RE.match(normalized):
        return False
    if _CJK_TALENT_TITLE_FRAGMENT_RE.match(normalized):
        return False
    if _CJK_PROJECT_GRANT_AWARD_FRAGMENT_RE.match(normalized):
        return False
    if _CJK_PROJECT_YEAR_RANGE_FRAGMENT_RE.match(normalized):
        return False
    if _CJK_EDUCATION_BIO_THESIS_RESIDUE_RE.match(normalized):
        return False
    if _CJK_PROJECT_PROFILE_RESIDUE_RE.match(normalized):
        return False
    if _CJK_JOINT_LAB_OR_PROJECT_RESIDUE_RE.match(normalized):
        return False
    if _CJK_EDUCATION_PROJECT_FRAGMENT_RE.match(normalized):
        return False
    if _LOST_BOUNDARY_MULTI_TITLE_RE.search(normalized):
        return False
    if _HIGHLIGHTED_NOISE_RE.match(normalized):
        return False
    if _STANDALONE_ROLE_RE.match(normalized):
        return False
    if _STANDALONE_AWARD_OR_SERVICE_RE.match(normalized):
        return False
    if _UPDATE_METADATA_RE.match(normalized):
        return False
    if normalized.count(";") > 3:
        return False
    if normalized.count("; ") >= 2 and _count_author_like_segments(normalized, ";") >= 3:
        return False
    if _looks_like_comma_author_list(normalized):
        return False
    if _looks_like_short_author_fragment(normalized):
        return False
    if _looks_like_single_lastname_author_fragment(normalized):
        return False
    if _looks_like_short_pinyin_author_chain(normalized):
        return False
    if _looks_like_standalone_person_name(normalized):
        return False
    if _looks_like_hyphenated_person_name(normalized):
        return False
    if _looks_like_and_joined_person_names(normalized):
        return False
    if _looks_like_standalone_pinyin_name_fragment(normalized):
        return False
    if _TRUNCATED_TRAILING_PAREN_RE.search(normalized):
        return False
    if _looks_like_broken_letter_spacing(normalized):
        return False
    if _PAREN_PREFIX_RE.match(normalized):
        return False
    if _looks_like_editorial_bio(normalized):
        return False
    return True


def is_clearly_garbage_paper_title(title: str | None) -> bool:
    """High-precision "clearly not a paper title" classifier for title-cleanup.

    Unlike :func:`is_plausible_paper_title` (high-RECALL: used by the W0b identity
    gate to *leave* implausible titles alone), this is high-PRECISION: it returns
    ``True`` only for high-confidence non-paper garbage — parser noise, journal-
    metric fragments, profile/editorial prose, citation records, patent records,
    book records, high-confidence author lists, and venue-only/section-label
    fragments.

    It deliberately SPARES real technical titles that the broad guard over-flags
    (e.g. "Kinetic Modeling and Reaction Engineering" mistaken for two person
    names; substring journal-metric matches on long technical titles), because
    rejecting a real paper is worse than leaving some ambiguous garbage. Truncated
    real titles are also spared (those are a C2/C3 truncation repair, not a
    reject). Use this for the title-cleanup scan's rejection decision, NOT for
    the W0b identity gate.
    """
    if title is None:
        return True
    normalized = _normalize(str(title))
    if not (8 <= len(normalized) <= 300):
        return True
    if re.search(r"not explicitly (?:provided|titled) in text", normalized, re.IGNORECASE):
        return True
    if _JOURNAL_METRIC_FRAGMENT_RE.match(normalized):
        return True
    if re.search(r"[\(（]\s*IF\s*[:=]\s*\d", normalized, re.IGNORECASE):
        return True
    if _PROFILE_OR_SERVICE_PROSE_RE.search(normalized):
        return True
    if _EDITORIAL_ROLE_RE.search(normalized) and len(_ACRONYM_RE.findall(normalized)) >= 2:
        return True
    if _CJK_PROFILE_OR_SERVICE_SNIPPET_RE.search(normalized):
        return True
    if _CITATION_TAIL_RE.search(normalized):
        return True
    if _JOURNAL_DATE_DOI_RECORD_RE.match(normalized):
        return True
    if _YEAR_PREFIX_CITATION_METADATA_RE.search(normalized):
        return True
    if _PATENT_RECORD_RE.search(normalized):
        return True
    if _CJK_PATENT_LIKE_TITLE_RE.search(normalized):
        return True
    if _ENGLISH_PATENT_TITLE_RE.match(normalized):
        return True
    if _BOOK_OR_TRANSLATION_RECORD_RE.search(normalized):
        return True
    if _looks_like_comma_author_list(normalized):
        return True
    if _looks_like_mojibake_author_list(normalized):
        return True
    if _looks_like_slash_author_list(normalized):
        return True
    if _looks_like_known_venue_only_title(normalized):
        return True
    if _STANDALONE_VENUE_LINE_RE.match(normalized):
        return True
    if _STANDALONE_JOURNAL_OR_TRANSACTIONS_RE.match(normalized):
        return True
    if _STANDALONE_SECTION_LABEL_RE.match(normalized):
        return True
    if _PUBLICATION_SECTION_LABEL_RE.match(normalized):
        return True
    if _STANDALONE_SINGLE_WORD_FRAGMENT_RE.match(normalized):
        return True
    return False
