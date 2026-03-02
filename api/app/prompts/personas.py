from __future__ import annotations

DEFAULT_PERSONA = "sales_representative"

PERSONA_DEFAULT_PROMPTS: dict[str, str] = {
    "sales_representative": (
        "Prioritize deal progression. Provide concise next steps, discovery questions, "
        "and follow-up messaging suggestions tied to the account's business priorities."
    ),
    "marketing_specialist": (
        "Prioritize positioning and pipeline generation. Recommend campaign angles, "
        "content hooks, and measurable GTM actions aligned to persona and industry."
    ),
    "se": (
        "Prioritize technical validation. Focus on architecture fit, migration risks, "
        "POC design, and concrete technical proof points relevant to the workload."
    ),
}

PERSONA_LABELS: dict[str, str] = {
    "sales_representative": "Sales Representative",
    "marketing_specialist": "Marketing Specialist",
    "se": "SE",
}

PERSONA_ALIASES: dict[str, str] = {
    "sales representative": "sales_representative",
    "sales_rep": "sales_representative",
    "rep": "sales_representative",
    "marketing": "marketing_specialist",
    "marketing specialist": "marketing_specialist",
    "se": "se",
    "sales engineer": "se",
}


def normalize_persona(value: str | None) -> str:
    if not value:
        return DEFAULT_PERSONA
    lowered = value.strip().lower().replace("-", "_")
    if lowered in PERSONA_DEFAULT_PROMPTS:
        return lowered
    lowered = lowered.replace("_", " ")
    alias = PERSONA_ALIASES.get(lowered)
    if alias:
        return alias
    return DEFAULT_PERSONA


def get_default_persona_prompt(persona_name: str | None) -> str:
    normalized = normalize_persona(persona_name)
    return PERSONA_DEFAULT_PROMPTS[normalized]


def get_persona_label(persona_name: str | None) -> str:
    normalized = normalize_persona(persona_name)
    return PERSONA_LABELS[normalized]
