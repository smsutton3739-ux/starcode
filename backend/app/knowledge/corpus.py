"""The curated seed corpus.

Scope, stated plainly: this is a **demonstration corpus** of a few dozen sources and
passages, chosen because they are (a) genuinely astronomical or prophetic, (b) frequently
submitted to a tool like this one, and (c) out of copyright or quoted at fair-use length
from public-domain translations. It is not a substitute for a licensed scholarly database.

Everything here is citable. Translations are public domain and credited. Dating ranges are
the ranges scholarship actually gives, with the disagreement recorded in `dating_note`
rather than smoothed into a single confident number — because the disagreement is
frequently the most important thing to tell a user.

`scripts/import_dataset.py` loads additional datasets in this same shape.
"""

from __future__ import annotations

from typing import Any

PUBLIC_DOMAIN_KJV = "King James Version (1611), public domain"
PUBLIC_DOMAIN_JPS = "Jewish Publication Society (1917), public domain"

# --------------------------------------------------------------------------------------
# Historical sources
# --------------------------------------------------------------------------------------

HISTORICAL_SOURCES: list[dict[str, Any]] = [
    {
        "slug": "book-of-daniel",
        "title": "Book of Daniel",
        "alternate_titles": ["Sefer Daniyyel", "Δανιήλ"],
        "tradition": "hebrew_bible",
        "language": "Hebrew and Aramaic",
        "script": "Hebrew",
        "composition_earliest_year": -600,
        "composition_latest_year": -164,
        "dating_note": (
            "The dating of Daniel is one of the sharpest divides in biblical scholarship. "
            "The book presents itself as set in the 6th century BCE Babylonian exile. The "
            "dominant critical position dates its final form to c. 167–164 BCE, during the "
            "Maccabean crisis, largely because chapter 11 tracks Hellenistic history in "
            "detail up to Antiochus IV and then diverges. Traditional Jewish and Christian "
            "readings, and a minority of scholars, maintain a 6th-century composition. A "
            "platform user should be told which assumption a given interpretation depends on, "
            "because almost every prophetic reading of Daniel rests on one or the other."
        ),
        "region": "Babylon / Judea",
        "description": "Apocalyptic and court-tale material with extensive symbolic chronology.",
        "canonical_citation": "Daniel, in the Hebrew Bible (Ketuvim) and Christian Old Testament.",
        "reliability": "contested_dating",
        "is_primary_source": True,
        "license": "Public domain (KJV/JPS translations)",
    },
    {
        "slug": "book-of-revelation",
        "title": "Revelation of John (Apocalypse)",
        "alternate_titles": ["Ἀποκάλυψις Ἰωάννου", "Apocalypse of John"],
        "tradition": "new_testament",
        "language": "Koine Greek",
        "script": "Greek",
        "composition_earliest_year": 68,
        "composition_latest_year": 96,
        "dating_note": (
            "Two datings compete. The 'late' date (c. 95–96 CE, under Domitian) rests on "
            "Irenaeus, Against Heresies 5.30.3, and is the majority view. The 'early' date "
            "(c. 68–70 CE, under Nero or just after) rests on internal evidence some read as "
            "presupposing a standing Temple. The choice materially changes which historical "
            "events a preterist reading can appeal to."
        ),
        "region": "Asia Minor (Patmos / Ephesus)",
        "description": "Christian apocalyptic text dense with astronomical and numerical imagery.",
        "canonical_citation": "Revelation, in the Christian New Testament.",
        "reliability": "contested_dating",
        "is_primary_source": True,
        "license": "Public domain (KJV translation)",
    },
    {
        "slug": "book-of-joel",
        "title": "Book of Joel",
        "tradition": "hebrew_bible",
        "language": "Hebrew",
        "script": "Hebrew",
        "composition_earliest_year": -800,
        "composition_latest_year": -400,
        "dating_note": (
            "Joel contains no regnal formula, so it cannot be dated internally. Proposals "
            "range across four centuries; a post-exilic date (5th–4th c. BCE) is most common "
            "today. Any claim that Joel 'predicted' a specific later event has to reckon with "
            "the fact that the text's own date is unfixed."
        ),
        "region": "Judah",
        "description": "Prophetic text containing the celestial-portent language quoted in Acts 2.",
        "canonical_citation": "Joel, in the Hebrew Bible (Nevi'im).",
        "reliability": "contested_dating",
        "is_primary_source": True,
        "license": "Public domain (KJV/JPS translations)",
    },
    {
        "slug": "enuma-anu-enlil",
        "title": "Enūma Anu Enlil",
        "tradition": "mesopotamian",
        "language": "Akkadian",
        "script": "Cuneiform",
        "composition_earliest_year": -1600,
        "composition_latest_year": -700,
        "dating_note": (
            "A compilation of roughly 70 tablets of celestial omens, assembled over "
            "centuries; the surviving recension is Neo-Assyrian (7th c. BCE) but incorporates "
            "much older material. Individual omens cannot usually be dated."
        ),
        "region": "Mesopotamia",
        "description": (
            "The principal Mesopotamian celestial omen series. Its structure is 'if X in the "
            "sky, then Y on earth' — omens read as warnings to be averted, not fixed fates."
        ),
        "canonical_citation": "Enūma Anu Enlil, Neo-Assyrian recension, British Museum collection.",
        "reliability": "scholarly_consensus",
        "is_primary_source": True,
        "license": "Text public domain; modern translations under copyright — quote sparingly",
    },
    {
        "slug": "babylonian-astronomical-diaries",
        "title": "Babylonian Astronomical Diaries",
        "tradition": "mesopotamian",
        "language": "Akkadian",
        "script": "Cuneiform",
        "composition_earliest_year": -652,
        "composition_latest_year": -61,
        "dating_note": (
            "The longest continuous series of scientific observations in human history, "
            "roughly 652 BCE to 61 BCE. Individual tablets are dated by regnal year and are "
            "usually precisely fixable, which makes them the backbone of ancient chronology."
        ),
        "region": "Babylon",
        "description": (
            "Night-by-night records of lunar and planetary positions, eclipses, weather, "
            "river levels and commodity prices."
        ),
        "canonical_citation": (
            "Sachs, A. J. & Hunger, H., Astronomical Diaries and Related Texts from "
            "Babylonia, vols. I–VI (Österreichische Akademie der Wissenschaften, 1988–2006)."
        ),
        "reliability": "high_primary",
        "is_primary_source": True,
        "license": "Publication under copyright; catalogue metadata freely citable",
    },
    {
        "slug": "ptolemy-almagest",
        "title": "Almagest (Mathēmatikē Syntaxis)",
        "tradition": "greek",
        "language": "Koine Greek",
        "script": "Greek",
        "composition_earliest_year": 145,
        "composition_latest_year": 150,
        "dating_note": "Composed in Alexandria around 150 CE.",
        "region": "Roman Egypt",
        "description": (
            "Ptolemy's geocentric synthesis, including a star catalogue and a list of "
            "eclipse observations reaching back to the 8th century BCE — the bridge by which "
            "Babylonian records entered Greek and later European astronomy."
        ),
        "canonical_citation": "Ptolemy, Almagest; trans. G. J. Toomer (Duckworth, 1984).",
        "reliability": "high_primary",
        "is_primary_source": True,
        "license": "Greek text public domain",
    },
    {
        "slug": "dresden-codex",
        "title": "Dresden Codex",
        "tradition": "mayan",
        "language": "Yucatec Maya",
        "script": "Maya hieroglyphic",
        "composition_earliest_year": 1000,
        "composition_latest_year": 1400,
        "dating_note": (
            "The surviving manuscript is generally dated to the 11th–14th centuries CE, but "
            "it copies substantially older material; the Venus table's structure is Classic "
            "period in origin."
        ),
        "region": "Yucatán",
        "description": (
            "One of four surviving Maya codices. Contains the Venus table, eclipse tables and "
            "ritual almanacs — some of the most accurate pre-telescopic astronomy anywhere."
        ),
        "canonical_citation": (
            "Codex Dresdensis, Sächsische Landesbibliothek Dresden, Mscr.Dresd.R.310."
        ),
        "reliability": "high_primary",
        "is_primary_source": True,
        "license": "Facsimile public domain",
    },
    {
        "slug": "surya-siddhanta",
        "title": "Sūrya Siddhānta",
        "tradition": "hindu",
        "language": "Sanskrit",
        "script": "Devanagari",
        "composition_earliest_year": 400,
        "composition_latest_year": 1000,
        "dating_note": (
            "The received text dates to roughly the 4th–5th c. CE with later recensions; the "
            "text itself claims vastly greater antiquity. The claimed and the attested dates "
            "should never be conflated."
        ),
        "region": "India",
        "description": (
            "Foundational Sanskrit astronomical treatise: planetary mean motions, eclipse "
            "prediction, and the yuga cycle framework."
        ),
        "canonical_citation": "Sūrya Siddhānta; trans. E. Burgess (1860), public domain.",
        "reliability": "scholarly_consensus",
        "is_primary_source": True,
        "license": "Burgess translation public domain",
    },
    {
        "slug": "shiji-tianguan-shu",
        "title": "Shiji, 'Treatise on the Celestial Offices' (Tianguan shu)",
        "tradition": "chinese",
        "language": "Classical Chinese",
        "script": "Han characters",
        "composition_earliest_year": -109,
        "composition_latest_year": -91,
        "dating_note": "Compiled by Sima Qian c. 109–91 BCE.",
        "region": "Han China",
        "description": (
            "Systematic account of Chinese celestial divisions and portent interpretation, "
            "and the model for the astronomical treatises of every later dynastic history — "
            "the reason Chinese records of comets and guest stars are so continuous."
        ),
        "canonical_citation": "Sima Qian, Shiji, ch. 27.",
        "reliability": "high_primary",
        "is_primary_source": True,
        "license": "Chinese text public domain",
    },
    {
        "slug": "josephus-jewish-war",
        "title": "The Jewish War",
        "tradition": "roman",
        "language": "Koine Greek",
        "script": "Greek",
        "composition_earliest_year": 75,
        "composition_latest_year": 79,
        "dating_note": "Written c. 75–79 CE, shortly after the events described.",
        "region": "Judea / Rome",
        "description": (
            "Josephus' account of the Jewish revolt and the destruction of the Second Temple "
            "in 70 CE, including reports of celestial portents preceding the war."
        ),
        "canonical_citation": "Josephus, The Jewish War; trans. W. Whiston (1737), public domain.",
        "reliability": "high_primary_with_bias",
        "is_primary_source": True,
        "license": "Whiston translation public domain",
    },
    {
        "slug": "nostradamus-les-propheties",
        "title": "Les Prophéties",
        "tradition": "early_modern",
        "language": "Middle French",
        "script": "Latin",
        "composition_earliest_year": 1555,
        "composition_latest_year": 1568,
        "dating_note": (
            "First edition 1555; expanded editions to 1568. The publication history is "
            "genuinely messy, and some quatrains circulating today appear in no 16th-century "
            "edition — provenance should be checked before any quatrain is interpreted."
        ),
        "region": "France",
        "description": (
            "Quatrains in deliberately obscure, syntactically ambiguous French. Their "
            "vagueness is a compositional feature, which is precisely why retrospective "
            "matching to events is so easy and so weak as evidence."
        ),
        "canonical_citation": "Nostradamus, Les Prophéties (Lyon, 1555 and later editions).",
        "reliability": "interpretive_source",
        "is_primary_source": True,
        "license": "Public domain",
    },
    {
        "slug": "sibylline-oracles",
        "title": "Sibylline Oracles",
        "tradition": "greek",
        "language": "Koine Greek",
        "script": "Greek",
        "composition_earliest_year": -150,
        "composition_latest_year": 700,
        "dating_note": (
            "A composite collection assembled over some 800 years by Jewish, Christian and "
            "pagan hands. Individual books differ in date by centuries, so 'the Sibylline "
            "Oracles say...' is almost always too coarse a statement to be useful."
        ),
        "region": "Mediterranean",
        "description": "Hexameter prophecy collections, heavy with cosmic and eschatological imagery.",
        "canonical_citation": "Sibylline Oracles; trans. M. S. Terry (1899), public domain.",
        "reliability": "composite_uncertain",
        "is_primary_source": True,
        "license": "Terry translation public domain",
    },
    {
        "slug": "antikythera-mechanism",
        "title": "Antikythera Mechanism",
        "tradition": "greek",
        "language": "Koine Greek",
        "script": "Greek",
        "composition_earliest_year": -205,
        "composition_latest_year": -60,
        "dating_note": (
            "Dating proposals span roughly 205–60 BCE, based variously on the shipwreck "
            "context, letter forms, and the eclipse-prediction dial's Saros cycle alignment."
        ),
        "region": "Greek world",
        "description": (
            "A geared bronze device computing lunisolar calendar positions, eclipse cycles "
            "and planetary phenomena. Hard evidence that mechanised astronomical prediction "
            "existed in antiquity."
        ),
        "canonical_citation": (
            "Freeth, T. et al., 'Decoding the ancient Greek astronomical calculator known as "
            "the Antikythera Mechanism', Nature 444 (2006), 587–591."
        ),
        "reliability": "high_primary",
        "is_primary_source": True,
        "license": "Metadata freely citable",
    },
    {
        "slug": "venus-tablet-ammisaduqa",
        "title": "Venus Tablet of Ammisaduqa (Enūma Anu Enlil Tablet 63)",
        "tradition": "mesopotamian",
        "language": "Akkadian",
        "script": "Cuneiform",
        "composition_earliest_year": -1700,
        "composition_latest_year": -1600,
        "dating_note": (
            "Records 21 years of Venus risings and settings under Ammisaduqa of Babylon. "
            "Because Venus phenomena repeat, the observations fit several possible absolute "
            "dates, producing the 'high', 'middle', 'low' and 'ultra-low' Mesopotamian "
            "chronologies — which differ by up to 150 years. This single tablet is why the "
            "absolute chronology of the ancient Near East remains unsettled."
        ),
        "region": "Babylon",
        "description": "The oldest substantial planetary observation record known.",
        "canonical_citation": (
            "Reiner, E. & Pingree, D., The Venus Tablet of Ammiṣaduqa (Undena, 1975)."
        ),
        "reliability": "high_primary_contested_dating",
        "is_primary_source": True,
        "license": "Metadata freely citable",
    },
]


# --------------------------------------------------------------------------------------
# Passages
# --------------------------------------------------------------------------------------

SOURCE_PASSAGES: list[dict[str, Any]] = [
    {
        "source_slug": "book-of-joel",
        "reference_label": "Joel 2:30–31",
        "translation": (
            "And I will shew wonders in the heavens and in the earth, blood, and fire, and "
            "pillars of smoke. The sun shall be turned into darkness, and the moon into "
            "blood, before the great and terrible day of the LORD come."
        ),
        "translation_credit": PUBLIC_DOMAIN_KJV,
        "themes": ["celestial portent", "day of the Lord", "eschatology", "sun", "moon"],
        "astronomical_content": True,
        "prophetic_content": True,
        "notes": (
            "The most frequently submitted 'blood moon' passage. Three readings are all "
            "well attested and should be distinguished rather than merged: (1) conventional "
            "prophetic idiom for cosmic upheaval, used similarly in Isaiah 13:10 and "
            "Ezekiel 32:7; (2) description of the reddening of sun and moon by dust, smoke "
            "or volcanic aerosol, which is a real and common atmospheric effect; (3) a lunar "
            "eclipse, during which the Moon does turn coppery-red. Nothing in the text "
            "selects between them, and the eclipse reading in particular is a modern "
            "interpretive overlay, not something the passage states."
        ),
    },
    {
        "source_slug": "book-of-daniel",
        "reference_label": "Daniel 9:24–26",
        "translation": (
            "Seventy weeks are determined upon thy people and upon thy holy city, to finish "
            "the transgression, and to make an end of sins... Know therefore and understand, "
            "that from the going forth of the commandment to restore and to build Jerusalem "
            "unto the Messiah the Prince shall be seven weeks, and threescore and two weeks."
        ),
        "translation_credit": PUBLIC_DOMAIN_KJV,
        "themes": ["seventy weeks", "sacred number", "chronology", "messianic"],
        "astronomical_content": False,
        "prophetic_content": True,
        "notes": (
            "The 'seventy weeks' passage generates more date calculations than any other "
            "text in the corpus. Every such calculation depends on four choices the text "
            "does not make for you: which decree counts as 'the going forth of the "
            "commandment' (there are at least four candidates in Ezra and Nehemiah, spanning "
            "457–444 BCE); whether a 'week' is seven years; whether years are 360-day or "
            "solar; and whether the periods run consecutively. Different defensible choices "
            "yield answers decades apart. A tool should show the arithmetic and its "
            "assumptions, never a single date presented as the answer."
        ),
    },
    {
        "source_slug": "book-of-daniel",
        "reference_label": "Daniel 8:14",
        "translation": (
            "And he said unto me, Unto two thousand and three hundred days; then shall the "
            "sanctuary be cleansed."
        ),
        "translation_credit": PUBLIC_DOMAIN_KJV,
        "themes": ["2300 days", "sacred number", "sanctuary"],
        "astronomical_content": False,
        "prophetic_content": True,
        "notes": (
            "The Hebrew reads 'evenings-mornings', which may denote 2,300 days or 1,150 "
            "days (2,300 sacrifices at two per day). The ambiguity is in the source text "
            "itself and is not resolvable by translation. The historicist 'day-year' "
            "reading treating these as 2,300 years underlies several 19th-century "
            "prophetic movements; it is an interpretive framework, not a feature of the text."
        ),
    },
    {
        "source_slug": "book-of-revelation",
        "reference_label": "Revelation 6:12–13",
        "translation": (
            "And I beheld when he had opened the sixth seal, and, lo, there was a great "
            "earthquake; and the sun became black as sackcloth of hair, and the moon became "
            "as blood; And the stars of heaven fell unto the earth, even as a fig tree "
            "casteth her untimely figs, when she is shaken of a mighty wind."
        ),
        "translation_credit": PUBLIC_DOMAIN_KJV,
        "themes": ["sixth seal", "eclipse imagery", "meteor", "celestial portent"],
        "astronomical_content": True,
        "prophetic_content": True,
        "notes": (
            "The falling-stars simile is a reasonable description of an intense meteor storm, "
            "and the 1833 Leonid storm was widely read this way at the time. That an image "
            "matches an observable phenomenon does not establish that the text predicted a "
            "particular occurrence of it — the imagery is also standard in earlier Jewish "
            "apocalyptic (Isaiah 34:4)."
        ),
    },
    {
        "source_slug": "book-of-revelation",
        "reference_label": "Revelation 12:1–2",
        "translation": (
            "And there appeared a great wonder in heaven; a woman clothed with the sun, and "
            "the moon under her feet, and upon her head a crown of twelve stars: And she "
            "being with child cried, travailing in birth, and pained to be delivered."
        ),
        "translation_credit": PUBLIC_DOMAIN_KJV,
        "themes": ["zodiac", "twelve stars", "Virgo", "sun", "moon"],
        "astronomical_content": True,
        "prophetic_content": True,
        "notes": (
            "Widely mapped onto the constellation Virgo with the Sun in Virgo and the Moon "
            "at her feet — a configuration that recurs, by the geometry involved, roughly "
            "once a year and can be found in many years with minor variations. The "
            "arrangement is astronomically checkable; the identification of the woman with "
            "Virgo is a scholarly and traditional reading, and claims that a specific "
            "modern date uniquely fulfils it generally fail because the configuration is not "
            "in fact rare. The astronomy agent will compute the configuration; whether it "
            "means anything is a separate question the platform does not answer."
        ),
    },
    {
        "source_slug": "book-of-revelation",
        "reference_label": "Revelation 13:18",
        "translation": (
            "Here is wisdom. Let him that hath understanding count the number of the beast: "
            "for it is the number of a man; and his number is Six hundred threescore and six."
        ),
        "translation_credit": PUBLIC_DOMAIN_KJV,
        "themes": ["sacred number", "666", "gematria"],
        "astronomical_content": False,
        "prophetic_content": True,
        "notes": (
            "Papyrus 115 and Codex Ephraemi read 616, not 666. Both numbers work as gematria "
            "for 'Nero Caesar' — 666 from the Hebrew transliteration of the Greek form, 616 "
            "from the Latin form — which is the most commonly held scholarly explanation. "
            "Any analysis of this verse that does not mention the 616 variant is incomplete."
        ),
    },
    {
        "source_slug": "josephus-jewish-war",
        "reference_label": "Jewish War 6.288–290",
        "translation": (
            "Thus there was a star resembling a sword, which stood over the city, and a "
            "comet, that continued a whole year. ... a certain prodigious and incredible "
            "phenomenon appeared; I suppose the account of it would seem to be a fable, were "
            "it not related by those that saw it."
        ),
        "translation_credit": "William Whiston (1737), public domain",
        "themes": ["comet", "portent", "Jerusalem", "siege"],
        "astronomical_content": True,
        "prophetic_content": False,
        "notes": (
            "Frequently identified with the 66 CE apparition of Halley's Comet, whose "
            "computed perihelion (25 January 66 CE) does fall in the right window. Note what "
            "each part of that is: the apparition is a computed astronomical fact; the "
            "identification with Josephus' 'star resembling a sword' is an inference. "
            "Josephus names no comet, and he is writing polemically about portents that "
            "foreshadowed a catastrophe he had already witnessed."
        ),
    },
    {
        "source_slug": "dresden-codex",
        "reference_label": "Dresden Codex, Venus Table (pp. 24, 46–50)",
        "translation": (
            "[Tabular content: a 584-day Venus cycle over 65 cycles, with correction "
            "mechanisms and associated deity and omen glyphs.]"
        ),
        "translation_credit": "Structural description after Lounsbury and Aveni",
        "themes": ["Venus", "584-day cycle", "calendar correction", "omen"],
        "astronomical_content": True,
        "prophetic_content": True,
        "notes": (
            "The table tracks the Venus synodic period as 584 days against a true mean of "
            "583.92, and includes an explicit correction scheme to absorb the drift. This is "
            "empirical astronomy of a high order. It is also inseparable from omen-taking: "
            "the same table assigns malign influence to Venus' heliacal rising. Treating the "
            "astronomy as sophisticated and the divination as naive imposes a modern "
            "distinction the Maya did not make."
        ),
    },
    {
        "source_slug": "enuma-anu-enlil",
        "reference_label": "Enūma Anu Enlil, lunar eclipse omens (Tablets 15–22)",
        "translation": (
            "If an eclipse occurs on the fourteenth day of Simanu and the god in his eclipse "
            "becomes dark on the east side and clears on the west side: the king of Akkad "
            "will die."
        ),
        "translation_credit": "Representative rendering after Rochberg",
        "themes": ["eclipse", "omen", "kingship", "substitute king"],
        "astronomical_content": True,
        "prophetic_content": True,
        "notes": (
            "Mesopotamian eclipse omens were conditional warnings, not fixed predictions — "
            "which is why the substitute-king ritual existed: a stand-in occupied the throne "
            "for the danger period and was disposed of afterwards. This is direct evidence "
            "that the culture producing these texts understood omens as avertable. Reading "
            "them as deterministic prophecy misrepresents the tradition that wrote them."
        ),
    },
    {
        "source_slug": "surya-siddhanta",
        "reference_label": "Sūrya Siddhānta 1.11–12 (yuga cycle)",
        "translation": (
            "Twelve thousand of these divine years are denominated a Chaturyuga; of ten "
            "thousand times four hundred and thirty-two solar years is composed that "
            "Chaturyuga, with its dawn and twilight."
        ),
        "translation_credit": "Ebenezer Burgess (1860), public domain",
        "themes": ["yuga", "cosmic cycle", "sacred number", "4320000"],
        "astronomical_content": True,
        "prophetic_content": False,
        "notes": (
            "The 4,320,000-year Mahayuga is a computational framework: it is the interval "
            "over which the text's planetary mean motions return to a common origin, which "
            "makes the arithmetic tractable. Reading these figures as a claim about the "
            "physical age of the universe, in either direction, misunderstands their function "
            "within the text."
        ),
    },
    {
        "source_slug": "nostradamus-les-propheties",
        "reference_label": "Century I, Quatrain 1",
        "translation": (
            "Sitting alone at night in secret study; it is placed on the brass tripod. A "
            "slight flame comes out of the solitude and makes successful that which should "
            "not be believed in vain."
        ),
        "translation_credit": "Public domain translation",
        "themes": ["divination", "method", "tripod"],
        "astronomical_content": False,
        "prophetic_content": True,
        "notes": (
            "The opening quatrain describes a divinatory method rather than an event. Useful "
            "as a control case: it demonstrates how much of the corpus is procedural or "
            "atmospheric rather than predictive, which retrospective readings tend to obscure."
        ),
    },
    {
        "source_slug": "babylonian-astronomical-diaries",
        "reference_label": "Diary for 331 BCE (Battle of Gaugamela)",
        "translation": (
            "[Month VI, day 13:] There was a lunar eclipse; it was total, with the west wind "
            "blowing. ... [Month VI, day 24:] the king of the world [Darius] ... his troops "
            "deserted him."
        ),
        "translation_credit": "Summary after Sachs & Hunger, Diaries vol. I",
        "themes": ["eclipse", "Gaugamela", "Alexander", "Darius III"],
        "astronomical_content": True,
        "prophetic_content": False,
        "notes": (
            "The total lunar eclipse of 20 September 331 BCE, eleven days before Gaugamela, "
            "is independently computable and is one of the firmest anchors in ancient "
            "chronology: an astronomical calculation and a dated cuneiform record agreeing "
            "exactly. This is the standard against which vaguer 'prophetic' correlations "
            "should be measured."
        ),
    },
    {
        "source_slug": "ptolemy-almagest",
        "reference_label": "Almagest IV.6 (Babylonian eclipse observations)",
        "translation": (
            "[Ptolemy cites lunar eclipses observed at Babylon in the first and second years "
            "of Mardokempad, dated by the era of Nabonassar.]"
        ),
        "translation_credit": "After Toomer's translation",
        "themes": ["eclipse", "Nabonassar", "chronology"],
        "astronomical_content": True,
        "prophetic_content": False,
        "notes": (
            "Ptolemy's citation of eclipses of 721–720 BCE preserved Babylonian data that "
            "would otherwise be lost, and pins the Era of Nabonassar to an absolute date. "
            "This is the chain by which most ancient Near Eastern chronology is anchored."
        ),
    },
    {
        "source_slug": "shiji-tianguan-shu",
        "reference_label": "Shiji 27 (on comets and portents)",
        "translation": (
            "When a broom star appears, it signifies the sweeping away of the old and the "
            "establishment of the new."
        ),
        "translation_credit": "Representative rendering",
        "themes": ["comet", "portent", "dynastic change"],
        "astronomical_content": True,
        "prophetic_content": True,
        "notes": (
            "Chinese 'broom star' (huixing) records are the single most valuable historical "
            "comet dataset, because portent-watching was an official state function and "
            "records were kept continuously for two millennia. The interpretive frame — "
            "comets signalling dynastic change — is what motivated the record-keeping, and "
            "also what makes the records occasionally suspect near political transitions."
        ),
    },
    {
        "source_slug": "venus-tablet-ammisaduqa",
        "reference_label": "Venus Tablet, Year 1 observations",
        "translation": (
            "In month XI, 15th day, Venus disappeared in the west; three days it remained "
            "away, and on the 18th day of month XI Venus became visible in the east."
        ),
        "translation_credit": "After Reiner & Pingree",
        "themes": ["Venus", "heliacal rising", "chronology"],
        "astronomical_content": True,
        "prophetic_content": False,
        "notes": (
            "The observations are precise; the problem is that Venus phenomena recur on an "
            "8-year cycle, so the pattern fits multiple absolute dates. This is a clean "
            "example of good data underdetermining a conclusion — the resulting high, middle "
            "and low chronologies differ by up to 150 years and the question is still open."
        ),
    },
    {
        "source_slug": "sibylline-oracles",
        "reference_label": "Sibylline Oracles III.796–806",
        "translation": (
            "And I will tell thee a very manifest sign, that thou mayest know when the end "
            "of all things shall be on earth. When swords are seen at night in starry heaven "
            "toward evening and toward morn..."
        ),
        "translation_credit": "Milton S. Terry (1899), public domain",
        "themes": ["celestial sign", "eschatology", "sword in sky"],
        "astronomical_content": True,
        "prophetic_content": True,
        "notes": (
            "'Swords in the sky' is a widespread ancient description; candidate referents "
            "include comets, aurorae and atmospheric optical effects. Book III is generally "
            "dated to the 2nd–1st century BCE, i.e. much earlier than the collection as a "
            "whole, which matters if the passage is being matched to a later event."
        ),
    },
    {
        "source_slug": "antikythera-mechanism",
        "reference_label": "Saros dial inscription",
        "translation": (
            "[Glyph sequence on the lower back dial encoding predicted solar and lunar "
            "eclipses across the 223-month Saros cycle, with hour and direction indications.]"
        ),
        "translation_credit": "After Freeth et al.",
        "themes": ["Saros", "eclipse prediction", "gearing"],
        "astronomical_content": True,
        "prophetic_content": False,
        "notes": (
            "Hard evidence that mechanical eclipse prediction existed by the late Hellenistic "
            "period, and that Babylonian period-relations had been absorbed into Greek "
            "practice. When a text of this era refers to a foreseen eclipse, foreseeing one "
            "was demonstrably within reach."
        ),
    },
]


# --------------------------------------------------------------------------------------
# Calendar systems (metadata rows; the conversion logic lives in app.calendars)
# --------------------------------------------------------------------------------------


def calendar_system_rows() -> list[dict[str, Any]]:
    from app.calendars.service import CALENDARS

    rows = []
    for spec in CALENDARS.values():
        rows.append(
            {
                "key": spec.key,
                "name": spec.name,
                "culture": spec.culture,
                "calendar_kind": spec.kind,
                "epoch_description": spec.epoch_description,
                "months_per_year": len(spec.month_names) or None,
                "supports_conversion": spec.to_rd is not None,
                "conversion_caveats": spec.caveat,
                "active_from_year": spec.active_from_year,
                "active_to_year": spec.active_to_year,
                "references": spec.references,
            }
        )
    return rows


# --------------------------------------------------------------------------------------
# Astronomical events recorded in historical documents
# --------------------------------------------------------------------------------------

RECORDED_ASTRONOMICAL_EVENTS: list[dict[str, Any]] = [
    {
        "event_type": "solar_eclipse",
        "designation": "Bur-Sagale eclipse",
        "label": "Total solar eclipse of 15 June 763 BCE (Julian)",
        "year": -762,
        "month": 6,
        "day": 15,
        "calendar_used": "julian_proleptic",
        "is_computed": False,
        "description": (
            "Recorded in the Assyrian Eponym Canon as occurring in the month of Simanu. "
            "Anchors Assyrian chronology absolutely and independently verifies the eponym "
            "list. The platform's own engine reproduces this date from first principles."
        ),
        "source_slug": "babylonian-astronomical-diaries",
        "visibility_regions": ["Assyria", "Anatolia"],
    },
    {
        "event_type": "solar_eclipse",
        "designation": "Eclipse of Thales",
        "label": "Total solar eclipse of 28 May 585 BCE (Julian)",
        "year": -584,
        "month": 5,
        "day": 28,
        "calendar_used": "julian_proleptic",
        "is_computed": False,
        "description": (
            "Herodotus (Histories 1.74) reports that an eclipse halted a battle between the "
            "Lydians and the Medes, and that Thales had predicted it. The eclipse is real and "
            "datable; whether Thales genuinely predicted it is doubted by most historians of "
            "science, since the Saros cycle does not by itself yield local solar visibility."
        ),
        "source_slug": None,
        "visibility_regions": ["Anatolia", "Mediterranean"],
    },
    {
        "event_type": "lunar_eclipse",
        "designation": "Gaugamela eclipse",
        "label": "Total lunar eclipse of 20 September 331 BCE (Julian)",
        "year": -330,
        "month": 9,
        "day": 20,
        "calendar_used": "julian_proleptic",
        "is_computed": False,
        "description": (
            "Recorded in the Babylonian Astronomical Diaries eleven days before the Battle "
            "of Gaugamela. One of the strongest links between a computed eclipse and a dated "
            "historical record."
        ),
        "source_slug": "babylonian-astronomical-diaries",
        "visibility_regions": ["Mesopotamia"],
    },
    {
        "event_type": "supernova",
        "designation": "SN 1054",
        "label": "Guest star of 1054 CE (Crab Nebula progenitor)",
        "year": 1054,
        "month": 7,
        "day": 4,
        "calendar_used": "julian_proleptic",
        "is_computed": False,
        "description": (
            "Song dynasty records describe a star visible in daylight for 23 days and at "
            "night for nearly two years. Its remnant is the Crab Nebula. Conspicuously absent "
            "from European records — a useful caution about arguments from silence."
        ),
        "source_slug": "shiji-tianguan-shu",
        "visibility_regions": ["China", "Japan", "Arab world", "North America"],
    },
    {
        "event_type": "planetary_conjunction",
        "designation": "Triple conjunction of 7 BCE",
        "label": "Jupiter–Saturn triple conjunction in Pisces, 7 BCE",
        "year": -6,
        "month": 5,
        "day": 29,
        "calendar_used": "julian_proleptic",
        "is_computed": True,
        "description": (
            "Jupiter and Saturn passed within about 1° three times during 7 BCE. Kepler "
            "proposed this as the Star of Bethlehem in 1614 and the idea remains popular. "
            "Two cautions: the pair never merged into a single object (they stayed roughly "
            "two lunar diameters apart), and triple conjunctions of these planets recur "
            "roughly every 800 years, so the event is notable but not unique."
        ),
        "source_slug": None,
        "visibility_regions": ["Global"],
    },
    {
        "event_type": "comet",
        "designation": "1P/66 B1",
        "label": "Halley's Comet apparition of 66 CE",
        "year": 66,
        "month": 1,
        "day": 25,
        "calendar_used": "julian_proleptic",
        "is_computed": True,
        "description": (
            "Computed perihelion 25 January 66 CE. Often linked to Josephus' 'star "
            "resembling a sword' over Jerusalem; the apparition is calculated fact, the "
            "identification is inference."
        ),
        "source_slug": "josephus-jewish-war",
        "visibility_regions": ["Global"],
    },
]


DATASETS: list[dict[str, Any]] = [
    {
        "key": "starcode-seed-sources",
        "name": "Starcode seed source corpus",
        "description": (
            "Curated historical sources and passages spanning Near Eastern, Mediterranean, "
            "South Asian, East Asian and Mesoamerican traditions. A demonstration corpus, "
            "not a comprehensive scholarly database."
        ),
        "provider": "Starcode",
        "license": "Public-domain translations; metadata CC0",
        "version": "1.0.0",
    },
    {
        "key": "starcode-recorded-events",
        "name": "Historically recorded astronomical events",
        "description": "Celestial events attested in dated historical documents.",
        "provider": "Starcode",
        "license": "CC0 metadata",
        "version": "1.0.0",
    },
    {
        "key": "starcode-calendars",
        "name": "Calendar system registry",
        "description": "Metadata for the 12 calendar systems the conversion engine supports.",
        "provider": "Starcode",
        "license": "CC0",
        "version": "1.0.0",
    },
    {
        "key": "imo-meteor-showers",
        "name": "IMO visual meteor shower working list",
        "description": "Annual meteor shower peaks, activity windows and parent bodies.",
        "provider": "International Meteor Organization",
        "license": "Cited under fair use; consult IMO for redistribution",
        "version": "2024",
    },
    {
        "key": "halley-apparitions",
        "name": "Halley's Comet apparition table",
        "description": "Computed perihelion passages 240 BCE – 1986 CE with historical records.",
        "provider": "Yeomans & Kiang (1981)",
        "license": "Cited",
        "version": "1.0.0",
    },
]


__all__ = [
    "HISTORICAL_SOURCES",
    "SOURCE_PASSAGES",
    "RECORDED_ASTRONOMICAL_EVENTS",
    "DATASETS",
    "calendar_system_rows",
]
