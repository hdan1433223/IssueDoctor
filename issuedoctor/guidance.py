"""User-facing explanations for the audit workflow and score catalog."""

DIMENSIONS = {
    "D1": {
        "name": "响应效率",
        "summary": "维护者是否及时看到并回应新 Issue，以及较老 Issue 是否仍有人跟进。",
        "question": "提问后，多久能得到维护者回应？",
    },
    "D2": {
        "name": "处理与积压",
        "summary": "Issue 的关闭速度、长期未关闭比例，以及新增与关闭是否保持平衡。",
        "question": "积压是否持续增长，问题能否及时处理？",
    },
    "D3": {
        "name": "信息质量",
        "summary": "Issue 是否包含复现步骤、环境、预期结果等足以开展排查的信息。",
        "question": "维护者拿到 Issue 后，信息够不够用？",
    },
    "D4": {
        "name": "分类与标签",
        "summary": "Issue 是否被正确分类，标签体系是否清晰、一致且有说明。",
        "question": "问题能否被快速分流到正确的处理队列？",
    },
    "D5": {
        "name": "协作闭环",
        "summary": "Issue 是否关联到 PR、合并或明确关闭原因，避免处理过程失去上下文。",
        "question": "从提出问题到修复关闭，过程是否形成闭环？",
    },
    "D6": {
        "name": "重复与知识沉淀",
        "summary": "是否存在大量相似问题，以及模板、贡献指南和 FAQ 等知识设施是否完善。",
        "question": "重复问题能否被减少，经验有没有沉淀下来？",
    },
}


METRICS = {
    "M1.1": {
        "name": "首次维护者响应中位时间",
        "meaning": "有维护者回应的 Issue，从创建到首次回应所需小时数的中位数。",
        "better": "越低越好",
    },
    "M1.2": {
        "name": "未响应 Issue 比例",
        "meaning": "分析范围内从未得到维护者回应的 Issue 占比。",
        "better": "越低越好",
    },
    "M1.3": {
        "name": "老旧 Issue 无近期维护活动比例",
        "meaning": "开放超过 30 天的 Issue 中，最近 14 天没有维护者活动的占比。",
        "better": "越低越好",
    },
    "M2.1": {
        "name": "关闭耗时中位数",
        "meaning": "已关闭 Issue 从创建到关闭所需天数的中位数。",
        "better": "越低越好",
    },
    "M2.2": {
        "name": "长期开放 Issue 比例",
        "meaning": "当前开放 Issue 中，已开放超过 90 天的占比。",
        "better": "越低越好",
    },
    "M2.3": {
        "name": "关闭/新增平衡比",
        "meaning": "时间窗口内关闭的 Issue 数除以新增 Issue 数；接近或达到 1 表示没有继续累积。",
        "better": "越高越好",
    },
    "M3.1": {
        "name": "Bug 信息完整度",
        "meaning": (
            "Bug Issue 对版本、环境、复现步骤、预期/实际结果、日志和补充上下文的加权覆盖率。"
        ),
        "better": "越高越好",
    },
    "M3.2": {
        "name": "低信息 Issue 比例",
        "meaning": "去除 Markdown 标记后，正文有效内容少于 80 个字符的 Issue 占比。",
        "better": "越低越好",
    },
    "M3.3": {
        "name": "结构化模板使用率",
        "meaning": "正文包含至少 3 个 Markdown 标题、呈现结构化填写痕迹的 Issue 占比。",
        "better": "越高越好",
    },
    "M4.1": {
        "name": "标签覆盖率",
        "meaning": "至少带有一个标签的 Issue 占比。",
        "better": "越高越好",
    },
    "M4.2": {
        "name": "类型标签覆盖率",
        "meaning": "带有 bug、feature、question、docs 等类型标签的 Issue 占比。",
        "better": "越高越好",
    },
    "M4.3": {
        "name": "冲突或同义标签比例",
        "meaning": "已使用标签中，名称归一化后重复或属于同义组的标签占比。",
        "better": "越低越好",
    },
    "M4.4": {
        "name": "标签描述覆盖率",
        "meaning": "已使用的唯一标签中，填写了描述的标签占比。",
        "better": "越高越好",
    },
    "M5.1": {
        "name": "明确关闭原因比例",
        "meaning": "已关闭 Issue 中，能从合并 PR、标签或维护者说明识别关闭原因的占比。",
        "better": "越高越好",
    },
    "M5.2": {
        "name": "关联 PR 合并率",
        "meaning": "存在关联 PR 的 Issue 中，至少有一个关联 PR 已合并的占比。",
        "better": "越高越好",
    },
    "M5.3": {
        "name": "无明确依据关闭比例",
        "meaning": "已关闭 Issue 中，找不到合并 PR、原因标签或维护者解释的占比。",
        "better": "越低越好",
    },
    "M5.4": {
        "name": "Issue 到合并耗时中位数",
        "meaning": "Issue 创建到首个关联 PR 合并所需天数的中位数。",
        "better": "越低越好",
    },
    "M6.1": {
        "name": "高相似 Issue 涉及比例",
        "meaning": "参与高相似候选对（相似度至少 0.82）的 Issue 占比。",
        "better": "越低越好",
    },
    "M6.2": {
        "name": "重复问题聚类比例",
        "meaning": "进入至少包含 3 个 Issue 的相似问题聚类的 Issue 占比。",
        "better": "越低越好",
    },
    "M6.3": {
        "name": "知识治理设施得分",
        "meaning": "根据 Issue 模板、贡献指南、模板配置、支持/FAQ 和分诊文档累计，满分 3 分。",
        "better": "越高越好",
    },
    "AI3.1": {
        "name": "AI 语义信息质量",
        "meaning": "AI 根据标题和正文判断 Issue 是否具体、清晰并包含推进处理所需的语义信息。",
        "better": "越高越好",
    },
    "AI5.1": {
        "name": "AI 协作闭环质量",
        "meaning": "AI 根据关闭状态、正文语义和可见关联判断处理结果是否交代清楚。",
        "better": "越高越好",
    },
    "AI6.1": {
        "name": "AI 重复候选复核",
        "meaning": "AI 对本地向量筛出的高相似候选对做语义复核，减少仅靠相似度造成的误报。",
        "better": "确认重复越少越好",
    },
}


WORKFLOW_STEPS = [
    {"number": 1, "name": "填写仓库", "summary": "输入 owner/repo 或完整 GitHub 链接。"},
    {"number": 2, "name": "仓库预检", "summary": "确认仓库、数据量、API 额度和分析上限。"},
    {"number": 3, "name": "运行审计", "summary": "采集数据并计算六维评分、相似问题和建议。"},
    {"number": 4, "name": "阅读结果", "summary": "先看总览，再从问题清单进入指标和原始证据。"},
    {
        "number": 5,
        "name": "执行治理",
        "summary": "预览治理包；需要写入时再人工确认 PR 或标签操作。",
    },
]


AI_PROVIDERS = [
    {
        "name": "GroqCloud",
        "status": "免费计划（有速率限制）",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-20b",
        "note": "兼容性和固定模型最明确，建议优先尝试。",
        "docs_url": "https://console.groq.com/docs/overview",
        "key_url": "https://console.groq.com/keys",
    },
    {
        "name": "Google Gemini",
        "status": "免费层（地区与账户配额可能不同）",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.5-flash-lite",
        "note": "若模型不可用，请以 AI Studio 中当前项目可见的 Flash-Lite 型号为准。",
        "docs_url": "https://ai.google.dev/gemini-api/docs/openai",
        "key_url": "https://aistudio.google.com/app/apikey",
    },
    {
        "name": "OpenRouter",
        "status": "免费模型路由（有每日请求限制）",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "openrouter/free",
        "note": "会自动选择支持当前请求能力的免费模型，具体底层模型可能变化。",
        "docs_url": "https://openrouter.ai/docs/quickstart",
        "key_url": "https://openrouter.ai/settings/keys",
    },
]


AI_CATEGORY_NAMES = {
    "bug": "缺陷",
    "feature": "功能建议",
    "question": "使用问题",
    "docs": "文档",
    "support": "支持请求",
    "other": "其他",
}


AI_FIELD_NAMES = {
    "version": "版本信息",
    "environment": "运行环境",
    "reproduction_steps": "复现步骤",
    "expected_result": "预期结果",
    "actual_result": "实际结果",
    "logs": "日志或错误堆栈",
    "context": "补充上下文或最小示例",
}


AI_ACTION_NAMES = {
    "none": "无需额外动作",
    "request_more_information": "请求补充信息",
    "add_or_fix_label": "补充或修正标签",
    "link_pull_request": "关联解决 PR",
    "review_as_duplicate": "复核为重复问题",
    "document_or_faq": "沉淀为文档或 FAQ",
    "review_closure": "复核关闭依据",
}
