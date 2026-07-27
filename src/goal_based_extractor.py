# src/goal_based_extractor.py
#
# The EXTRACTOR_PROMPT below is adapted from Tongyi DeepResearch
# by Alibaba-NLP / Tongyi Lab: https://github.com/Alibaba-NLP/DeepResearch
# Copyright (c) Alibaba-NLP / Tongyi Lab.
# Licensed under the Apache License, Version 2.0 — full text in
# licenses/DeepResearch-Apache-2.0.txt.
# CHANGE NOTICE (Apache-2.0 §4(b)): EXTRACTOR_PROMPT was extracted from
# DeepResearch's inference/prompt.py into this standalone module, and integrated
# with the Deep Research engine (src/deep_research.py), in Odysseus (Copyright
# (c) 2025 Odysseus Contributors, MIT) BEFORE the MyPaiOS fork point (upstream
# commit 8354948) — this module and the prompt already existed there. MyPaiOS
# added this attribution/change header in 2026 and made no change to the prompt
# text.
"""
Goal-based content extraction prompt adapted from Alibaba Tongyi DeepResearch
(Apache-2.0 — see header above).
"""

EXTRACTOR_PROMPT = """Please process the following webpage content and user goal to extract relevant information:

## **Webpage Content**
{webpage_content}

## **User Goal**
{goal}

## **Task Guidelines**
1. **Content Scanning for Rational**: Locate the **specific sections/data** directly related to the user's goal within the webpage content
2. **Key Extraction for Evidence**: Identify and extract the **most relevant information** from the content, you never miss any important information, output the **full original context** of the content as far as possible, it can be more than three paragraphs.
3. **Summary Output for Summary**: Organize into a concise paragraph with logical flow, prioritizing clarity and judge the contribution of the information to the goal.

**Final Output Format using JSON format has "rational", "evidence", "summary" fields**

Example output:
{{
    "rational": "This section discusses X which directly relates to the goal of understanding Y",
    "evidence": "Full quotes and context from the page...",
    "summary": "Concise summary of how this information answers the goal"
}}
"""
