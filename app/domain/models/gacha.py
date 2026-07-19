from pydantic import BaseModel, Field
from typing import Optional


class EvolutionStage(BaseModel):
    name: str = Field(description="Name of the evolution stage form")
    description: str = Field(description="Short, playful description of the form")
    visual_prompt: str = Field(
        description="A detailed English prompt describing the appearance of this form. "
        "Focus on its physical features, colors, and body shape. "
        "Describe ONLY the creature itself. Do NOT include any background, environment, "
        "setting, or surrounding objects. Keep the background completely blank."
    )


class GachaPetDesign(BaseModel):
    name: str = Field(description="Base name of the monster species")
    stage1: EvolutionStage = Field(
        description="Stage 1 (baby/basic/only form) design details"
    )
    stage2: Optional[EvolutionStage] = Field(
        None,
        description="Stage 2 (evolved/mid form) design details. MUST be null/None for Legendary and God rarities.",
    )
    stage3: Optional[EvolutionStage] = Field(
        None,
        description="Stage 3 (final/epic form) design details. MUST be null/None for Legendary and God rarities.",
    )
    mega: Optional[EvolutionStage] = Field(
        None,
        description="Mega form design details (None/null if not capable or if Legendary/God)",
    )


class AlignedPrompts(BaseModel):
    stage2: Optional[EvolutionStage] = Field(
        None, description="Stage 2 aligned prompts"
    )
    stage3: Optional[EvolutionStage] = Field(
        None, description="Stage 3 aligned prompts"
    )
    mega: Optional[EvolutionStage] = Field(None, description="Mega aligned prompts")
