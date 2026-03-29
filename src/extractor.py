"""
src/extractor.py
─────────────────
The LLM extraction layer. This is the core intelligence of the pipeline.

Key concepts you'll learn here:

1. Structured output (.with_structured_output)
   Instead of asking the LLM to "return JSON" and hoping,
   we bind a Pydantic schema directly to the model.
   LangChain uses function calling / tool use under the hood
   to guarantee the output matches our schema. No parsing, no retries.

2. Batching
   We send 5 job descriptions per LLM call, not 1.
   This reduces API calls by 5x and is much faster.
   The prompt is designed so the model returns a list of results.

3. Skill normalisation
   The LLM handles variants like "python3" → "Python",
   "lang chain" → "LangChain", "k8s" → "Kubernetes".
   We reinforce this in the prompt with explicit examples.

4. Error handling
   If the LLM fails or returns unexpected data, we log and skip
   that batch rather than crashing the whole pipeline.
"""

import asyncio
import logging
from typing import AsyncIterator

from langchain_classic.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from src.config import get_llm, get_settings
from src.models import RawJobPost, ExtractedSkills, ExtractedSkill, SkillCategory

logger = logging.getLogger(__name__)


# ─── Batch Schema ─────────────────────────────────────────────────────────────

class BatchExtractedSkills(BaseModel):
    """
    Wrapper for extracting skills from multiple job posts in one LLM call.
    Each item in `results` corresponds to one job post in the batch.
    """
    results: list[ExtractedSkills] = Field(
        description="One ExtractedSkills object per job posting, in the same order."
    )


# ─── Prompt ───────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a technical recruiter analysing job postings.
Extract ALL technical skills from each job description.

Rules:
- Normalise skill names: "python3" → "Python", "k8s" → "Kubernetes", "lang chain" → "LangChain", "ML" → "Machine Learning"
- Include frameworks, languages, tools, cloud platforms, ML concepts, databases
- Categorise each skill accurately
- Mark as required=false only if the posting says "nice-to-have", "preferred", "bonus", or "plus"
- Skip soft skills (communication, teamwork) — technical only
- Return exactly one result object per job posting, in order
- Limit to 20 skills per job (the most important ones)""",
    ),
    (
        "human",
        """Extract skills from these {n} job postings:

{job_descriptions}

Return one result per posting, in the same order.""",
    ),
])


# ─── Extractor Class ──────────────────────────────────────────────────────────

class SkillExtractor:
    """
    Batched LLM skill extractor.

    Usage:
        extractor = SkillExtractor()
        results = await extractor.extract_batch(job_posts)
    """

    def __init__(self):
        settings = get_settings()
        self.batch_size = settings.extraction_batch_size
        # Bind the schema to the LLM — this is what enables structured output
        self._chain = EXTRACTION_PROMPT | get_llm().with_structured_output(
            BatchExtractedSkills
        )

    async def extract_batch(
        self, posts: list[RawJobPost]
    ) -> list[tuple[RawJobPost, ExtractedSkills | None]]:
        """
        Extract skills from a list of job posts.

        Splits into batches internally, runs them, pairs results back
        with original posts.

        Returns:
            List of (RawJobPost, ExtractedSkills | None) pairs.
            None means extraction failed for that post.
        """
        all_results: list[tuple[RawJobPost, ExtractedSkills | None]] = []

        # Split into batches
        batches = [
            posts[i: i + self.batch_size]
            for i in range(0, len(posts), self.batch_size)
        ]

        logger.info(
            f"Extracting skills from {len(posts)} posts "
            f"in {len(batches)} batches of {self.batch_size}"
        )

        for i, batch in enumerate(batches):
            logger.debug(f"Processing batch {i+1}/{len(batches)}")
            batch_results = await self._extract_one_batch(batch)
            all_results.extend(batch_results)

            # Small delay between batches to avoid rate limits
            if i < len(batches) - 1:
                await asyncio.sleep(0.5)

        return all_results

    async def _extract_one_batch(
        self, batch: list[RawJobPost]
    ) -> list[tuple[RawJobPost, ExtractedSkills | None]]:
        """
        Call the LLM on a single batch of job posts.
        Returns (post, extracted) pairs. extracted=None on failure.
        """
        # Format the job descriptions for the prompt
        job_descriptions = self._format_batch_for_prompt(batch)

        try:
            # This is an async call — we await the LLM response
            # The .with_structured_output() ensures we get BatchExtractedSkills back
            response: BatchExtractedSkills = await self._chain.ainvoke({
                "n": len(batch),
                "job_descriptions": job_descriptions,
            }) # type: ignore

            # Pair results back with original posts
            # If model returned wrong number of results, pad with None
            results = response.results
            pairs = []
            for j, post in enumerate(batch):
                extracted = results[j] if j < len(results) else None
                pairs.append((post, extracted))

            return pairs

        except Exception as e:
            logger.error(f"Batch extraction failed: {e}")
            # Return all posts with None — they'll be skipped in the pipeline
            return [(post, None) for post in batch]

    def _format_batch_for_prompt(self, batch: list[RawJobPost]) -> str:
        """
        Format a batch of job posts into the prompt text.
        We number them so the model knows the ordering.
        """
        parts = []
        for i, post in enumerate(batch, 1):
            parts.append(
                f"--- Job {i} ---\n"
                f"Title: {post.title}\n"
                f"Company: {post.company}\n"
                f"Description:\n{post.description[:1500]}"  # cap per job
            )
        return "\n\n".join(parts)


# ─── Fallback: Tag-based extraction ──────────────────────────────────────────

# Some jobs have pre-parsed tags (RemoteOK, Arbeitnow).
# If LLM extraction fails, we can fall back to these.
# They're less rich but better than nothing.

KNOWN_LANGUAGES  = {"python", "typescript", "javascript", "go", "rust", "java", "scala", "ruby", "kotlin", "swift", "r"}
KNOWN_FRAMEWORKS = {"langchain", "langgraph", "fastapi", "django", "react", "nextjs", "pytorch", "tensorflow", "huggingface"}
KNOWN_CLOUD      = {"aws", "gcp", "azure", "kubernetes", "docker", "terraform"}
KNOWN_DATABASES  = {"postgresql", "mysql", "redis", "mongodb", "chromadb", "pinecone", "weaviate", "elasticsearch"}
KNOWN_ML         = {"rag", "llm", "fine-tuning", "transformers", "nlp", "computer vision", "rlhf", "embeddings"}


def extract_skills_from_tags(tags: list[str]) -> ExtractedSkills:
    """
    Fallback: convert pre-parsed source tags into ExtractedSkill objects.
    Used when LLM extraction fails.
    """
    skills = []
    for tag in tags:
        tag_lower = tag.lower().strip()
        if not tag_lower:
            continue

        if tag_lower in KNOWN_LANGUAGES:
            cat = SkillCategory.LANGUAGE
        elif tag_lower in KNOWN_FRAMEWORKS:
            cat = SkillCategory.FRAMEWORK
        elif tag_lower in KNOWN_CLOUD:
            cat = SkillCategory.CLOUD
        elif tag_lower in KNOWN_DATABASES:
            cat = SkillCategory.DATABASE
        elif tag_lower in KNOWN_ML:
            cat = SkillCategory.ML_CONCEPT
        else:
            cat = SkillCategory.OTHER

        # Capitalise properly
        name = tag.title() if tag.islower() else tag

        skills.append(ExtractedSkill(
            name=name,
            category=cat,
            is_required=True,
        ))

    return ExtractedSkills(
        skills=skills[:20],
        role_category="Software Engineer",
    )
