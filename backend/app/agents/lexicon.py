"""Lexicons and pattern rules for extracting entities from ancient and prophetic texts.

This module is deliberately *not* a language model. It is a curated set of terms and
regular expressions that finds the things these texts actually contain — celestial bodies,
calendars, empires, sacred numbers, prophetic formulae — with high precision and known
recall. It runs in both provider paths: offline it is the whole extraction step, and with
a model it provides a deterministic floor the model's output is merged into, so extraction
never regresses because a model had an off day.

Coverage is honest rather than exhaustive: these are the terms that recur across the
traditions the platform targets, in English and common transliterations. Recall on a text
using unusual vocabulary will be lower, which is why extraction confidence is reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.db.models.analysis import EntityType


@dataclass(frozen=True, slots=True)
class LexEntry:
    canonical: str
    entity_type: EntityType
    patterns: tuple[str, ...]
    description: str = ""
    attributes: dict | None = None


def _e(
    canonical: str,
    entity_type: EntityType,
    *patterns: str,
    description: str = "",
    **attributes,
) -> LexEntry:
    return LexEntry(canonical, entity_type, patterns or (canonical,), description, attributes or None)


# --------------------------------------------------------------------------------------
# Celestial bodies and phenomena
# --------------------------------------------------------------------------------------

CELESTIAL: list[LexEntry] = [
    _e("Sun", EntityType.ASTRONOMICAL_OBJECT, "sun", "sol", "helios", "shamash", "ra", "surya",
       description="The Sun.", body="Sun"),
    _e("Moon", EntityType.ASTRONOMICAL_OBJECT, "moon", "luna", "selene", "sin(?![a-z])",
       "nanna", "chandra", "yareach", description="The Moon.", body="Moon"),
    _e("Mercury", EntityType.PLANET, "mercury", "hermes", "nabu", "budha", description="Mercury.",
       body="Mercury"),
    _e("Venus", EntityType.PLANET, "venus", "aphrodite", "ishtar", "inanna", "morning star",
       "evening star", "day star", "lucifer", "shukra", "quetzalcoatl",
       description="Venus, the brightest planet and a major omen body across traditions.",
       body="Venus"),
    _e("Mars", EntityType.PLANET, "mars", "ares", "nergal", "mangala", "red planet",
       description="Mars.", body="Mars"),
    _e("Jupiter", EntityType.PLANET, "jupiter", "zeus", "marduk", "brihaspati", "guru",
       description="Jupiter, royal star of Babylonian astrology.", body="Jupiter"),
    _e("Saturn", EntityType.PLANET, "saturn", "kronos", "cronus", "ninurta", "shani",
       description="Saturn.", body="Saturn"),
    _e("Sirius", EntityType.STAR, "sirius", "sothis", "sopdet", "dog star",
       description="Sirius; its heliacal rising set the Egyptian year."),
    _e("Polaris", EntityType.STAR, "polaris", "pole star", "north star"),
    _e("Aldebaran", EntityType.STAR, "aldebaran"),
    _e("Antares", EntityType.STAR, "antares"),
    _e("Regulus", EntityType.STAR, "regulus", "cor leonis"),
    _e("Spica", EntityType.STAR, "spica"),
    _e("Pleiades", EntityType.CONSTELLATION, "pleiades", "seven sisters", "kimah", "subaru",
       description="Open cluster in Taurus, referenced from Job to the Maya."),
    _e("Orion", EntityType.CONSTELLATION, "orion", "kesil", "sah"),
    _e("Ursa Major", EntityType.CONSTELLATION, "ursa major", "great bear", "big dipper", "plough"),
    _e("Draco", EntityType.CONSTELLATION, "draco", "the dragon"),
    _e("Cygnus", EntityType.CONSTELLATION, "cygnus"),
    _e("Milky Way", EntityType.ASTRONOMICAL_OBJECT, "milky way", "galaxy"),
]

ZODIAC: list[LexEntry] = [
    _e(name, EntityType.ZODIAC_SIGN, name.lower(), *aliases)
    for name, aliases in [
        ("Aries", ("the ram",)), ("Taurus", ("the bull",)), ("Gemini", ("the twins",)),
        ("Cancer", ("the crab",)), ("Leo", ("the lion",)), ("Virgo", ("the virgin", "the maiden")),
        ("Libra", ("the scales", "the balance")), ("Scorpio", ("scorpius", "the scorpion")),
        ("Sagittarius", ("the archer",)), ("Capricorn", ("capricornus", "the goat")),
        ("Aquarius", ("the water bearer",)), ("Pisces", ("the fishes", "the fish")),
    ]
]

PHENOMENA: list[LexEntry] = [
    _e("Solar eclipse", EntityType.ECLIPSE, "solar eclipse", "eclipse of the sun",
       "sun (?:was |shall be |is )?darkened", "sun (?:became|becometh|shall be) black",
       "darkness (?:over|upon) the (?:whole )?land", "the sun (?:hid|withdrew) (?:his|its) light",
       description="Reference to the Sun being obscured.", event_type="solar_eclipse"),
    _e("Lunar eclipse", EntityType.ECLIPSE, "lunar eclipse", "eclipse of the moon",
       "moon (?:in)?to blood", "moon (?:shall be |was |became )?(?:turned )?(?:as |into )?blood",
       "blood moon", "moon (?:was |shall be )?darkened",
       description="Reference to the Moon reddening or darkening.", event_type="lunar_eclipse"),
    _e("Comet", EntityType.COMET, "comet", "broom star", "hairy star", "bearded star",
       "star with a tail", "sword.{0,12}(?:in|over) the (?:sky|heaven)",
       description="A comet or comet-like apparition.", event_type="comet"),
    _e("Meteor", EntityType.METEOR_SHOWER, "meteor", "shooting star", "falling star",
       "stars (?:shall )?fall", "stars of heaven fell", "fire from heaven",
       description="Meteors or a meteor storm.", event_type="meteor_shower"),
    _e("New moon", EntityType.MOON_PHASE, "new moon", "rosh chodesh", "first crescent",
       "new moon festival", event_type="moon_phase", phase="new"),
    _e("Full moon", EntityType.MOON_PHASE, "full moon", "fifteenth day of the month",
       event_type="moon_phase", phase="full"),
    _e("Equinox", EntityType.HISTORICAL_EVENT, "equinox", "equal day and night",
       event_type="equinox"),
    _e("Solstice", EntityType.HISTORICAL_EVENT, "solstice", "longest day", "shortest day",
       "sun stands still", event_type="solstice"),
    _e("Conjunction", EntityType.ASTRONOMICAL_OBJECT, "conjunction", "planets (?:did )?meet",
       "stars (?:did )?join", event_type="planetary_conjunction"),
    _e("Supernova", EntityType.ASTRONOMICAL_OBJECT, "guest star", "new star", "nova",
       "star (?:that )?appeared suddenly", event_type="supernova"),
    _e("Aurora", EntityType.ASTRONOMICAL_OBJECT, "northern lights", "aurora",
       "armies in the sky", "fire in the northern sky"),
]

# --------------------------------------------------------------------------------------
# Calendars, empires, peoples
# --------------------------------------------------------------------------------------

CALENDARS: list[LexEntry] = [
    _e("Hebrew calendar", EntityType.CALENDAR, "hebrew calendar", "jewish calendar",
       "nisan", "iyyar", "sivan", "tammuz(?! the)", "elul", "tishri", "tishrei",
       "marheshvan", "cheshvan", "kislev", "tevet", "shevat", "adar",
       calendar_key="hebrew"),
    _e("Islamic calendar", EntityType.CALENDAR, "hijri", "islamic calendar", "muharram",
       "safar", "rabi al", "jumada", "rajab", "sha'?ban", "ramadan", "shawwal",
       "dhu al", calendar_key="islamic"),
    _e("Egyptian calendar", EntityType.CALENDAR, "egyptian calendar", "thoth", "phaophi",
       "athyr", "choiak", "epagomenal", "wandering year", calendar_key="egyptian"),
    _e("Maya calendar", EntityType.CALENDAR, "long count", "tzolkin", "tzolk'?in", "haab",
       "baktun", "b'?ak'?tun", "katun", "k'?atun", "calendar round", "maya calendar",
       calendar_key="mayan_long_count"),
    _e("Julian calendar", EntityType.CALENDAR, "julian calendar", "old style", "o\\.s\\.",
       calendar_key="julian"),
    _e("Gregorian calendar", EntityType.CALENDAR, "gregorian calendar", "new style",
       calendar_key="gregorian"),
    _e("Babylonian calendar", EntityType.CALENDAR, "babylonian calendar", "nisannu",
       "simanu", "addaru", "arahsamnu", calendar_key=None),
    _e("Chinese calendar", EntityType.CALENDAR, "chinese calendar", "sexagenary",
       "stem[- ]branch", "lunar new year", calendar_key="chinese_sexagenary"),
    _e("Persian calendar", EntityType.CALENDAR, "persian calendar", "jalali", "nowruz",
       "farvardin", calendar_key="persian"),
    _e("Yuga cycle", EntityType.CALENDAR, "yuga", "kali yuga", "satya yuga", "mahayuga",
       "kalpa", calendar_key=None),
]

EMPIRES: list[LexEntry] = [
    _e("Babylonian Empire", EntityType.EMPIRE, "babylon", "babylonian", "chaldea", "chaldean",
       earliest_year=-1894, latest_year=-539),
    _e("Assyrian Empire", EntityType.EMPIRE, "assyria", "assyrian", "nineveh", "ashur",
       earliest_year=-2500, latest_year=-609),
    _e("Achaemenid Persia", EntityType.EMPIRE, "persia", "persian empire", "medes", "media",
       "achaemenid", earliest_year=-550, latest_year=-330),
    _e("Ancient Egypt", EntityType.EMPIRE, "egypt", "egyptian", "pharaoh", "memphis", "thebes",
       earliest_year=-3100, latest_year=-30),
    _e("Roman Empire", EntityType.EMPIRE, "rome", "roman", "caesar", "senate", "latin",
       earliest_year=-753, latest_year=476),
    _e("Greek world", EntityType.EMPIRE, "greece", "greek", "hellenic", "hellenistic",
       "macedon", "athens", "sparta", earliest_year=-800, latest_year=-31),
    _e("Kingdom of Judah", EntityType.NATION, "judah", "judea", "jerusalem", "zion",
       "israel", earliest_year=-1000, latest_year=70),
    _e("Han China", EntityType.EMPIRE, "han dynasty", "middle kingdom", "cathay",
       earliest_year=-206, latest_year=220),
    _e("Maya civilization", EntityType.CULTURE, "maya", "mayan", "yucatan", "tikal",
       "palenque", earliest_year=-2000, latest_year=1697),
    _e("Aztec Empire", EntityType.EMPIRE, "aztec", "mexica", "tenochtitlan",
       earliest_year=1345, latest_year=1521),
    _e("Ottoman Empire", EntityType.EMPIRE, "ottoman", "sublime porte",
       earliest_year=1299, latest_year=1922),
    _e("Byzantine Empire", EntityType.EMPIRE, "byzantium", "byzantine", "constantinople",
       earliest_year=330, latest_year=1453),
]

RELIGIONS: list[LexEntry] = [
    _e("Judaism", EntityType.RELIGION, "judaism", "jewish", "hebrew", "torah", "talmud",
       "rabbinic", "synagogue"),
    _e("Christianity", EntityType.RELIGION, "christian", "christianity", "gospel", "church",
       "apostle", "messiah", "christ"),
    _e("Islam", EntityType.RELIGION, "islam", "islamic", "muslim", "qur'?an", "koran",
       "hadith", "caliph"),
    _e("Hinduism", EntityType.RELIGION, "hindu", "vedic", "veda", "brahmin", "vishnu",
       "shiva", "purana"),
    _e("Buddhism", EntityType.RELIGION, "buddhis[tm]", "buddha", "dharma", "sutra"),
    _e("Zoroastrianism", EntityType.RELIGION, "zoroastr", "ahura mazda", "avesta", "magi"),
    _e("Mesopotamian religion", EntityType.RELIGION, "marduk", "enlil", "anu", "ishtar",
       "tiamat", "ziggurat"),
    _e("Egyptian religion", EntityType.RELIGION, "osiris", "isis", "horus", "amun", "ra(?![a-z])",
       "book of the dead"),
    _e("Greco-Roman religion", EntityType.RELIGION, "olympus", "oracle", "delphi", "sibyl",
       "augur", "haruspex"),
]

# --------------------------------------------------------------------------------------
# Sacred numbers and symbols
# --------------------------------------------------------------------------------------

SACRED_NUMBERS: dict[str, dict] = {
    "3": {"significance": "Divine completeness; trinities and triads across many traditions."},
    "4": {"significance": "The four directions, winds, rivers or living creatures."},
    "7": {"significance": "Completion. Seven days, seven seals, seven classical planets — the "
                         "last of which is likely the origin of the number's weight."},
    "10": {"significance": "Ordinal completeness; ten commandments, ten sefirot."},
    "12": {"significance": "Twelve tribes, twelve apostles, twelve zodiac signs, twelve months. "
                           "Rooted in the roughly twelve lunations per solar year."},
    "40": {"significance": "A period of testing or transition — flood, wilderness, fasting. "
                           "Often idiomatic for 'a long time' rather than an exact count."},
    "50": {"significance": "Jubilee; Pentecost."},
    "70": {"significance": "The nations; the seventy elders; Daniel's seventy weeks."},
    "144": {"significance": "12 × 12; the 144,000 of Revelation 7 and 14."},
    "153": {"significance": "The fish of John 21; a triangular number that attracted much "
                            "patristic numerology."},
    "216": {"significance": "6³; associated with Platonic and Pythagorean number mysticism."},
    "360": {"significance": "The idealised year of many ancient calendars, and degrees of a circle."},
    "432": {"significance": "Base of the Hindu yuga figures (432,000 years for the Kali Yuga)."},
    "666": {"significance": "The number of the beast, Revelation 13:18. Note the well-attested "
                            "616 variant in Papyrus 115."},
    "616": {"significance": "Variant of the beast's number in Papyrus 115 and Codex Ephraemi."},
    "1260": {"significance": "Days in Revelation 11–12; equals 42 months of 30 days, or "
                             "'time, times and half a time'."},
    "1290": {"significance": "Days in Daniel 12:11."},
    "1335": {"significance": "Days in Daniel 12:12."},
    "1656": {"significance": "Years from creation to the flood in the Masoretic chronology."},
    "2300": {"significance": "Evenings-mornings of Daniel 8:14."},
    "5778": {"significance": "A Hebrew calendar year (2017–2018 CE) that attracted attention "
                             "for numerological reasons."},
    "144000": {"significance": "The sealed of Revelation 7:4 and 14:1."},
}

SYMBOLS: list[LexEntry] = [
    _e("Dragon", EntityType.SYMBOL, "dragon", "leviathan", "serpent of the sea", "tiamat"),
    _e("Beast", EntityType.SYMBOL, "the beast", "beast (?:rising )?(?:out of|from) the sea"),
    _e("Horn", EntityType.SYMBOL, "horns?(?! of plenty)", "little horn"),
    _e("Crown", EntityType.SYMBOL, "crown", "diadem"),
    _e("Seal", EntityType.SYMBOL, "seals?(?! ?ed with)", "opened the seal"),
    _e("Trumpet", EntityType.SYMBOL, "trumpets?", "shofar"),
    _e("Vial/Bowl", EntityType.SYMBOL, "vials?", "bowls? of wrath"),
    _e("Sword", EntityType.SYMBOL, "sword"),
    _e("Lamb", EntityType.SYMBOL, "the lamb"),
    _e("Lion", EntityType.SYMBOL, "lion"),
    _e("Eagle", EntityType.SYMBOL, "eagle"),
    _e("Tree of Life", EntityType.SYMBOL, "tree of life"),
    _e("Wheel", EntityType.SYMBOL, "wheel within a wheel", "ophanim"),
    _e("Chariot", EntityType.SYMBOL, "chariot", "merkabah"),
    _e("Whore of Babylon", EntityType.SYMBOL, "whore of babylon", "mystery babylon"),
    _e("Four Horsemen", EntityType.SYMBOL, "four horsemen", "pale horse", "red horse",
       "white horse", "black horse"),
]

# --------------------------------------------------------------------------------------
# Prophetic and predictive formulae
# --------------------------------------------------------------------------------------

PROPHECY_MARKERS: list[tuple[str, str]] = [
    (r"\bthus (?:saith|says) the (?:lord|god)\b", "Prophetic messenger formula"),
    (r"\bin the (?:last|latter) days\b", "Eschatological time marker"),
    (r"\bthe day of the lord\b", "Day of the Lord formula"),
    (r"\bit shall come to pass\b", "Prophetic future formula"),
    (r"\bbehold,? I will\b", "Divine announcement formula"),
    (r"\bwoe (?:unto|to)\b", "Prophetic woe oracle"),
    (r"\bI saw\b.{0,40}\b(?:vision|dream)\b", "Visionary report"),
    (r"\b(?:time|times),? (?:and|&) (?:a )?half a time\b", "Apocalyptic period formula"),
    (r"\bthe end (?:of the world|of days|of the age)\b", "Eschatological marker"),
    (r"\bthere shall (?:arise|come)\b", "Predictive formula"),
    (r"\bhe that hath (?:an ear|understanding)\b", "Call to interpretation"),
    (r"\bthe (?:abomination of desolation|great tribulation)\b", "Apocalyptic technical term"),
    (r"\bprophe(?:cy|sy|t|tic)\b", "Explicit prophecy vocabulary"),
    (r"\bforetold?\b|\bforetell\b", "Explicit prediction vocabulary"),
]

# --------------------------------------------------------------------------------------
# Date expressions
# --------------------------------------------------------------------------------------

#: Spelled-out ordinals are the norm in these texts ("in the third year of..."), and a
#: digits-only regnal pattern misses most real occurrences.
ORDINAL_WORDS: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
    "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
    "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20,
    "thirtieth": 30, "fortieth": 40,
}

_ORDINAL_ALTERNATION = "|".join(ORDINAL_WORDS)

#: A ruler or month name: one to four capitalised words, optionally joined by "of".
#: Bounded deliberately — an unbounded run of word characters swallows the rest of the
#: sentence ("Belshazzar king of Babylon a vision appeared...").
_RULER = r"([A-Z][a-z]+(?:\s+(?:of\s+)?[A-Z][a-z]+){0,3})"

DATE_PATTERNS: list[tuple[str, str]] = [
    (rf"\b(?:in the )?(\d{{1,2}})(?:st|nd|rd|th)? year of (?:the reign of )?{_RULER}",
     "regnal_year"),
    (rf"\b(?:in the )?({_ORDINAL_ALTERNATION}) year of (?:the reign of )?{_RULER}",
     "regnal_year_spelled"),
    (rf"\b(?:in the )?({_ORDINAL_ALTERNATION}) (?:day|month) of (?:the )?{_RULER}",
     "spelled_day_month"),
    (r"\b(\d{1,4})\s*(?:BCE|BC)\b", "bce_year"),
    (r"\b(\d{1,4})\s*(?:CE|AD)\b", "ce_year"),
    (r"\bAnno Domini\s+(\d{1,4})\b", "ce_year"),
    (r"\bA\.?M\.?\s*(\d{3,5})\b", "anno_mundi"),
    (r"\bA\.?H\.?\s*(\d{1,4})\b", "hijri_year"),
    (r"\b(\d{1,2})\.(\d{1,2})\.(\d{1,2})\.(\d{1,2})\.(\d{1,2})\b", "maya_long_count"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)? day of (?:the month of )?([A-Z][a-z]{2,12})", "day_month"),
    (r"\bthe (\d{1,2})(?:st|nd|rd|th)? (?:day|month) of the (\d{1,2})(?:st|nd|rd|th)? (?:month|year)",
     "ordinal_day_month"),
    (r"\b(\d{1,4})\s+years?\b", "duration_years"),
    (r"\b(\d{1,5})\s+days?\b", "duration_days"),
    (r"\bOlympiad\s+(\d{1,3})\b", "olympiad"),
]

ALL_LEXICONS: list[LexEntry] = (
    CELESTIAL + ZODIAC + PHENOMENA + CALENDARS + EMPIRES + RELIGIONS + SYMBOLS
)


@dataclass(slots=True)
class Match:
    entry: LexEntry
    surface: str
    start: int
    end: int


def _compile(entry: LexEntry) -> list[re.Pattern]:
    compiled = []
    for pattern in entry.patterns:
        # Bare words get word boundaries; anything already containing regex syntax is
        # trusted as authored.
        if re.fullmatch(r"[\w' ]+", pattern):
            pattern = rf"\b{re.escape(pattern).replace(chr(92) + ' ', ' ')}\b"
        compiled.append(re.compile(pattern, re.IGNORECASE))
    return compiled


_COMPILED: dict[str, list[re.Pattern]] = {e.canonical: _compile(e) for e in ALL_LEXICONS}


def find_entities(text: str) -> list[Match]:
    """All lexicon hits in the text, de-overlapped, longest match wins."""
    matches: list[Match] = []
    for entry in ALL_LEXICONS:
        for pattern in _COMPILED[entry.canonical]:
            for m in pattern.finditer(text):
                matches.append(Match(entry, m.group(0), m.start(), m.end()))

    matches.sort(key=lambda m: (m.start, -(m.end - m.start)))

    # Keep overlapping matches only when they are different entity types: "morning star"
    # is Venus and the surrounding "star" is not a separate entity, but "Babylon" as an
    # empire and as a symbol ("Mystery Babylon") are genuinely two findings.
    kept: list[Match] = []
    for match in matches:
        clash = any(
            match.start < k.end
            and k.start < match.end
            and k.entry.entity_type == match.entry.entity_type
            for k in kept
        )
        if not clash:
            kept.append(match)
    return kept


#: Spelled-out forms that matter, notably in early-modern English translations. Longest
#: first, so "six hundred threescore and six" wins over the "six" inside it.
_SPELLED_NUMBERS: list[tuple[str, str]] = sorted(
    [
        ("an hundred forty and four thousand", "144000"),
        ("a hundred and forty-four thousand", "144000"),
        ("six hundred threescore and six", "666"),
        ("a thousand two hundred and threescore", "1260"),
        ("threescore and ten", "70"),
        ("seventy", "70"), ("forty", "40"), ("twelve", "12"), ("seven", "7"),
    ],
    key=lambda pair: -len(pair[0]),
)


def find_sacred_numbers(text: str) -> list[dict]:
    """Numbers in the text that carry recognised traditional significance.

    Matches are de-overlapped by span rather than by value, so the "144" inside a Maya
    Long Count and the "forty" inside "an hundred forty and four thousand" do not
    surface as findings of their own.
    """
    candidates: list[dict] = []

    for match in re.finditer(r"\b(\d[\d,]{0,9})\b", text):
        raw = match.group(1).replace(",", "")
        # Skip a numeral embedded in a dotted sequence (a Maya Long Count, a verse
        # reference): those digits are positional, not numerologically significant.
        neighbourhood = text[max(0, match.start() - 1) : match.end() + 1]
        if "." in neighbourhood or ":" in neighbourhood:
            continue
        if raw in SACRED_NUMBERS:
            candidates.append(
                {
                    "number": raw,
                    "significance": SACRED_NUMBERS[raw]["significance"],
                    "start": match.start(),
                    "end": match.end(),
                    "surface": match.group(0),
                    "form": "numeral",
                }
            )

    for phrase, number in _SPELLED_NUMBERS:
        for match in re.finditer(rf"\b{phrase}\b", text, re.IGNORECASE):
            candidates.append(
                {
                    "number": number,
                    "significance": SACRED_NUMBERS[number]["significance"],
                    "start": match.start(),
                    "end": match.end(),
                    "surface": match.group(0),
                    "form": "spelled",
                }
            )

    # Longest span first so an enclosing phrase suppresses the fragments inside it.
    candidates.sort(key=lambda c: (c["start"], -(c["end"] - c["start"])))

    kept: list[dict] = []
    seen_values: set[str] = set()
    for candidate in candidates:
        overlaps = any(
            candidate["start"] < k["end"] and k["start"] < candidate["end"] for k in kept
        )
        if overlaps or candidate["number"] in seen_values:
            continue
        seen_values.add(candidate["number"])
        kept.append(candidate)

    return sorted(kept, key=lambda f: f["start"])


def find_prophecy_markers(text: str) -> list[dict]:
    found = []
    for pattern, label in PROPHECY_MARKERS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            found.append(
                {
                    "marker": label,
                    "surface": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return sorted(found, key=lambda f: f["start"])


def find_date_expressions(text: str) -> list[dict]:
    found = []
    for pattern, kind in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            found.append(
                {
                    "kind": kind,
                    "surface": match.group(0),
                    "groups": [g for g in match.groups() if g is not None],
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    found.sort(key=lambda f: (f["start"], -(f["end"] - f["start"])))

    deduped: list[dict] = []
    for item in found:
        if not any(item["start"] < d["end"] and d["start"] < item["end"] for d in deduped):
            deduped.append(item)
    return deduped


__all__ = [
    "LexEntry",
    "Match",
    "ALL_LEXICONS",
    "CELESTIAL",
    "ZODIAC",
    "PHENOMENA",
    "CALENDARS",
    "EMPIRES",
    "RELIGIONS",
    "SYMBOLS",
    "SACRED_NUMBERS",
    "PROPHECY_MARKERS",
    "DATE_PATTERNS",
    "find_entities",
    "find_sacred_numbers",
    "find_prophecy_markers",
    "find_date_expressions",
]
