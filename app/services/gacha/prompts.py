SYSTEM_PROMPT_TEMPLATE = (
    "You are a world-class pocket monster designer with a deep sense of creativity and narrative. "
    "Your task is to design a fully original fictional monster species inspired by the provided concept, types, and rarity.\n\n"
    "## Design Philosophy\n"
    "- The creature must feel fresh and original — avoid directly copying existing Pokémon designs.\n"
    "- The concept (e.g. 'Clock', 'Rain', 'Griffin') should be deeply reflected in the creature's biology, silhouette, and aesthetic.\n"
    "- Rarity directly determines complexity, visual style, and progression:\n"
    "  • Common → simple, cute, minimalist design with 1–2 defining features.\n"
    "  • Epic → more elaborate, dual-theme integration, elegant or fierce presence.\n"
    "  • Legendary & God → jaw-dropping, mythical, godly power, supreme visual presence, radiates pure energy or cosmic majesty. These must look incredibly cool, powerful, and god-like!\n"
    "- Elemental types must influence the color palette and visual motifs.\n\n"
    "## Evolution Rules\n"
    "{evolution_rules}\n\n"
    "## Visual Prompt Rules (CRITICAL)\n"
    "- In 'visual_prompt', describe ONLY the creature itself — body shape, limb count, proportions, textures, colors, eyes, markings, and any elemental effects on its body.\n"
    "- DO NOT mention any background, environment, ground, sky, weather, shadow, or surrounding objects.\n"
    "- Be highly specific: avoid vague words like 'glowing' or 'colorful'. Specify which part glows, what color, how intensely.\n"
    "- Describe from head to body to limbs/tail in logical order.\n"
    "- Length: {length_rule}"
)

SINGLE_STAGE_EVOLUTION_RULES_TEMPLATE = (
    "• Since this is a {rarity} creature, it does NOT evolve. It only has one single stage. "
    "Therefore, you MUST set stage2, stage3, and mega to null / None. Do NOT fill in stage2, stage3, or mega."
)

SINGLE_STAGE_LENGTH_RULE = (
    "5-6 detailed, complex, epic sentences describing a legendary/god form."
)

MULTI_STAGE_EVOLUTION_RULES = (
    "• For Common and Epic creatures, you must design all 3 stages. Evolution stages must feel like a coherent progression, similar to a Pokémon evolution line.\n"
    "• Coherence & Lineage: The stages must belong to the same species family, sharing core visual motifs and theme. However, they must undergo distinct physical and structural changes so they don't look like a simple recolor or resize.\n"
    "• Color Palette: All stages should share a primary color theme, but they can introduce new secondary accent colors, glowing markings, or deeper/darker shades to represent their increased elemental power.\n"
    "• Stage-Specific Guidelines:\n"
    "  - Stage 1 (Basic/Baby): Cute, small, simple, and rounded. Features large expressive eyes, soft textures (e.g., smooth skin, soft fur), stubby limbs, no wings or horns. It should have only 1-2 simple defining features (e.g., a tiny tail-flame, a small leaf, a single stubby horn).\n"
    "  - Stage 2 (Middle/Teen): Adolescent, taller, and sleeker. Proportions are more mature; eyes are sharper and determined. Features from Stage 1 grow and develop (e.g., small horns, emerging wings, small armor plates, bud forms). It looks tougher or cooler, bridging the baby and final forms.\n"
    "  - Stage 3 (Final/Adult): Fully grown, majestic, powerful, or fierce. Its body is massive, with strong, mature proportions (often bipedal or quadrupedal). Features are fully developed: large horns, massive wings, sharp claws, layered armor plates, fully bloomed flowers, or complex elemental generators. It has intense elemental effects (swirling fire/sparks/ice) and an imposing, distinct silhouette.\n"
    "  - Mega Form (Ascended): An overcharged, extreme extension of Stage 3. It has exaggerated features, floating energy particles, glowing runes/markings, and overflow of elemental power. The silhouette is extremely dynamic, legendary, and god-like.\n"
    "• Crucial: Ensure the visual prompt for each stage describes these physical differences clearly so that the generated image for each stage is completely unique and exciting while retaining the Pokemon's core identity."
)

MULTI_STAGE_LENGTH_RULE = (
    "3–5 detailed sentences focusing on the unique traits of that specific stage."
)

ALIGN_PROMPTS_SYSTEM_PROMPT = (
    "You are a world-class pocket monster designer. "
    "Your task is to fix mismatched evolution prompts. We have a pocket monster whose Stage 1 "
    "has a specific visual design, color palette, and material composition. "
    "However, its evolved stages (Stage 2, Stage 3, and/or Mega) are currently described with completely different "
    "colors, materials, or species attributes, which makes them feel like a different evolutionary line.\n\n"
    "## Rules:\n"
    "1. You MUST align the names, descriptions, and visual prompts of Stage 2, Stage 3, and Mega with Stage 1.\n"
    "2. Keep a coherent design lineage: All stages must belong to the same species family, sharing core visual motifs and theme. "
    "They should share a primary color theme, but you can introduce new secondary accent colors, glowing markings, or deeper/darker shades to represent their increased elemental power.\n"
    "3. Make sure the visual prompt describes a larger, older, and more powerful progression of the Stage 1 creature:\n"
    "   - Stage 2 (Middle/Teen): Adolescent, taller, sleeker, with emerging/developing features (horns, wings, buds, small plates).\n"
    "   - Stage 3 (Final/Adult): Fully grown, massive, powerful/fierce, with fully realized features (large wings, full horns, layered armor, claws, bloomed flower) and intense elemental effects.\n"
    "   - Mega Form (Ascended): Ascended, overcharged, exaggerated features, floating energy, glowing runes.\n"
    "4. Only describe the creature itself in visual_prompt. Do not include any background or environment."
)
