"""Transform helper function to extract relevant incidents only from the full dataset"""

import re
from typing import Optional

PATTERNS = {
    "Extreme Heat": re.compile(
        r"\b("
        r"heat\s*(?:exhaustion|stress|illness|cramp[s]?|stroke|prostration|collapse|syncope|fatigue)|"
        r"heatstroke|sunstroke|hyperthermia|dehydrat(?:ed|ion)|overheat(?:ed|ing)|"
        r"(?:extreme|excessive|oppressive|high)\s*(?:heat|temperature[s]?|temp[s]?)|"
        r"heat\s*(?:index|wave|advisory|warning)|"
        r"working\s*in\s*(?:the\s*)?(?:heat|sun|hot\s*sun)|"
        r"hot\s*(?:weather|day|afternoon|sun|climate|conditions)"
        r")\b",
        re.IGNORECASE,
    ),
    "Lightning": re.compile(
        r"\b("
        r"lightning(?:\s*(?:strike[s]?|struck|bolt[s]?|flash|discharge))?|"
        r"struck\s*by\s*lightning|"
        r"hit\s*by\s*lightning"
        r")\b",
        re.IGNORECASE,
    ),
    "Flood": re.compile(
        r"\b("
        r"flood(?:s|ed|ing)?|"
        r"flash\s*flood(?:s|ing)?|"
        r"(?:rising|high|rushing|swift|surging|receding)\s*waters?|"
        r"flood\s*waters?|"
        r"(?:river|creek|stream|lake|canal|stormwater|surge)\s*(?:overflowed|crested|flooded|breached)|"
        r"storm\s*surge|"
        r"(?:submerged|swept\s*away|inundated)\s*by\s*(?:water|flood|current)"
        r")\b",
        re.IGNORECASE,
    ),
    "Wildlife": re.compile(
        r"\b("
        r"(?:stung|bitten|attacked|mauled|trampled|kicked|gored|swarmed)\s*by\s*(?:an?|the|\d+)?\s*\w+|"
        r"(?:dog|canine|snake|rattlesnake|spider|gator|alligator|bee[s]?|wasp[s]?|hornet[s]?|yellow\s*jacket[s]?)\s*bite[s]?|"
        r"(?:bee[s]?|wasp[s]?|hornet[s]?|yellow\s*jacket[s]?|insect[s]?|ant[s]?)\s*sting[s]?|"
        r"alligator[s]?|gator[s]?|crocodile[s]?|rattlesnake[s]?|copperhead[s]?|cottonmouth[s]?|water\s*moccasin[s]?|"
        r"venomous\s*snake[s]?|snake\s*bite[s]?|"
        r"yellow\s*jacket[s]?|wasp[s]?|hornet[s]?|fire\s*ant[s]?|killer\s*bee[s]?|"
        r"brown\s*recluse|black\s*widow|scorpion[s]?|"
        r"(?:stray|feral|vicious|attack|police|k9|guard)\s*dog[s]?|"
        r"(?:feral|wild)\s*(?:boar[s]?|hog[s]?|pig[s]?)|"
        r"(?:kicked|trampled|struck|charged|pinned)\s*by\s*(?:a\s*)?(?:horse|bull|cow|steer|cattle|mule)"
        r")\b",
        re.IGNORECASE,
    ),
    "Soil Saturation": re.compile(
        r"\b("
        r"soil\s*saturation|saturated\s*soil|"
        r"(?:trench|ditch|excavation|embankment)\s*(?:cave[- ]?in|collapse[ds]?|caved|sloughed)|"
        r"ground\s*(?:caved|collapsed)|"
        r"cave[- ]?in|"
        r"sinkhole[s]?|"
        r"mudslide[s]?|landslide[s]?"
        r")\b",
        re.IGNORECASE,
    ),
    "Wildfire": re.compile(
        r"\b("
        r"wildfire[s]?|"
        r"brush\s*fire[s]?|"
        r"forest\s*fire[s]?|"
        r"grass\s*fire[s]?|"
        r"controlled\s*burn[s]?|"
        r"prescribed\s*burn[s]?"
        r")\b",
        re.IGNORECASE,
    ),
}

EXCLUSIONS = {
    "Extreme Heat": re.compile(
        r"\b("
        r"fryer|deep\s*fryer|grill|cooktop|stove|oven|skillet|broiler|"
        r"hot\s*(?:oil|grease|water|liquid|tar|asphalt|steam|sauce|soup|metal|pipe|engine)|"
        r"scald(?:ed|ing)?|welding|molten|furnace|boiler"
        r")\b",
        re.IGNORECASE,
    ),
    "Lightning": re.compile(
        r"\b("
        r"arc\s*flash|power\s*line|transformer|circuit|breaker|panel|"
        r"electrical\s*(?:wire|panel|conduit|switch|cabinet|equipment)|"
        r"high[- ]voltage|overhead\s*line|utility\s*pole"
        r")\b",
        re.IGNORECASE,
    ),
    "Flood": re.compile(
        r"\b("
        r"slipped\s*(?:on|in)\s*(?:water|wet\s*floor|puddle|ice|spill)|"
        r"wet\s*(?:floor|tile|concrete|surface|linoleum)|"
        r"mop\s*(?:bucket|water)|leaking\s*(?:pipe|sink|roof|cooler|toilet)|"
        r"puddle\s*on\s*the\s*floor"
        r")\b",
        re.IGNORECASE,
    ),
    "Wildlife": re.compile(
        r"\b("
        r"butterfly\s*valve|"
        r"hog\s*(?:ring|tie|wire|feeder|panel|slat)|"
        r"chicken\s*(?:wire|coop|breast|tender|nugget|salad)|"
        r"cathead|cat\s*(?:track|loader)|"
        r"bull\s*(?:float|pin|dozer)|"
        r"ram\s*(?:cylinder|hydraulic)|"
        r"crane\s*(?:boom|cable|hook)|"
        r"pig\s*(?:trap|launcher|receiver|tail)|pigging|"
        r"dog\s*(?:clutch|leg)|"
        r"snake\s*(?:camera|auger|cable)"
        r")\b",
        re.IGNORECASE,
    ),
}

CRITICAL_EVENTS = {"Lightning", "Wildfire", "Flood"}

PRIORITY_ORDER = [
    "Lightning",
    "Extreme Heat",
    "Flood",
    "Wildlife",
    "Soil Saturation",
    "Wildfire",
]


def classify_narrative(narrative: Optional[str]) -> str:
    if not narrative or not isinstance(narrative, str):
        return "Other (None of the above)"

    for category in PRIORITY_ORDER:
        pattern = PATTERNS.get(category)
        if not pattern or not pattern.search(narrative):
            continue

        if category == "Extreme Heat":
            if EXCLUSIONS["Extreme Heat"].search(narrative) and not re.search(
                r"\b(heat\s*(?:exhaustion|stroke|illness|stress|cramp)|heatstroke|sunstroke|hyperthermia|dehydrat)\b",
                narrative,
                re.IGNORECASE,
            ):
                continue

        elif category == "Flood":
            if EXCLUSIONS["Flood"].search(narrative) and not re.search(
                r"\b(flash\s*flood|flood\s*water|storm\s*surge|river\s*overflow)\b",
                narrative,
                re.IGNORECASE,
            ):
                continue

        elif category == "Wildlife":
            if EXCLUSIONS["Wildlife"].search(narrative) and not re.search(
                r"\b(stung|bitten|bite|sting|attacked|mauled|envenomation)\b",
                narrative,
                re.IGNORECASE,
            ):
                continue

        if category in CRITICAL_EVENTS:
            return "Critical Events (Lightning, Wildfire, Flood)"

        return category

    return "Other (None of the above)"

