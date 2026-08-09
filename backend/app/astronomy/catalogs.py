"""Static astronomical catalogues: meteor showers, historically recorded comets,
constellations and zodiac boundaries.

Each entry carries its own provenance. The comet table in particular mixes *computed*
returns (Halley's apparitions are backwards-integrated and well established) with
*recorded observations* (Chinese, Babylonian and European chronicles). Both are useful
and they are not the same kind of statement, so the `evidence` field distinguishes them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

IMO_REFERENCE = "International Meteor Organization, Working List of Visual Meteor Showers"
KRONK_REFERENCE = "Kronk, G. W., Cometography: A Catalog of Comets, vols. I–VI (CUP, 1999–2017)"
YEOMANS_REFERENCE = (
    "Yeomans, D. K. & Kiang, T., 'The long-term motion of comet Halley', "
    "Monthly Notices of the Royal Astronomical Society 197 (1981), 633–646"
)


@dataclass(frozen=True, slots=True)
class MeteorShower:
    key: str
    name: str
    peak_month: int
    peak_day: int
    active_start: tuple[int, int]
    active_end: tuple[int, int]
    zhr: int
    parent_body: str | None
    radiant_constellation: str
    note: str

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "peak": f"{self.peak_day} {_MONTHS[self.peak_month - 1]}",
            "peak_month": self.peak_month,
            "peak_day": self.peak_day,
            "active_period": (
                f"{self.active_start[1]} {_MONTHS[self.active_start[0] - 1]} – "
                f"{self.active_end[1]} {_MONTHS[self.active_end[0] - 1]}"
            ),
            "zenithal_hourly_rate": self.zhr,
            "parent_body": self.parent_body,
            "radiant_constellation": self.radiant_constellation,
            "note": self.note,
            "source": IMO_REFERENCE,
        }


_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

METEOR_SHOWERS: list[MeteorShower] = [
    MeteorShower("qua", "Quadrantids", 1, 3, (12, 28), (1, 12), 110, "(196256) 2003 EH1",
                 "Boötes", "Sharp peak, only a few hours wide."),
    MeteorShower("lyr", "Lyrids", 4, 22, (4, 14), (4, 30), 18, "C/1861 G1 Thatcher", "Lyra",
                 "The oldest recorded shower: Chinese records of 687 BCE describe stars "
                 "falling like rain, generally identified with this stream."),
    MeteorShower("eta", "Eta Aquariids", 5, 6, (4, 19), (5, 28), 50, "1P/Halley", "Aquarius",
                 "Debris from Halley's Comet; favours the southern hemisphere."),
    MeteorShower("cap", "Alpha Capricornids", 7, 30, (7, 3), (8, 15), 5, "169P/NEAT",
                 "Capricornus", "Low rate but noted for bright fireballs."),
    MeteorShower("sda", "Southern Delta Aquariids", 7, 30, (7, 12), (8, 23), 25,
                 "96P/Machholz", "Aquarius", "Broad maximum."),
    MeteorShower("per", "Perseids", 8, 12, (7, 17), (8, 24), 100, "109P/Swift–Tuttle",
                 "Perseus", "Recorded in Chinese annals from 36 CE; called the 'Tears of "
                 "Saint Lawrence' in medieval Europe for their proximity to his feast day."),
    MeteorShower("dra", "Draconids", 10, 8, (10, 6), (10, 10), 10, "21P/Giacobini–Zinner",
                 "Draco", "Highly variable; produced storms in 1933 and 1946."),
    MeteorShower("ori", "Orionids", 10, 21, (10, 2), (11, 7), 20, "1P/Halley", "Orion",
                 "The second stream fed by Halley's Comet."),
    MeteorShower("tau", "Taurids", 11, 5, (9, 10), (11, 20), 5, "2P/Encke", "Taurus",
                 "Slow, bright fireballs over a long window."),
    MeteorShower("leo", "Leonids", 11, 17, (11, 6), (11, 30), 15, "55P/Tempel–Tuttle", "Leo",
                 "Storms roughly every 33 years. The 1833 storm over North America is among "
                 "the most widely documented celestial events in history and was read by "
                 "many contemporaries as apocalyptic."),
    MeteorShower("gem", "Geminids", 12, 14, (12, 4), (12, 20), 150, "(3200) Phaethon",
                 "Gemini", "Now the strongest annual shower; only recognised in the 1860s, "
                 "so it is absent from earlier records."),
    MeteorShower("urs", "Ursids", 12, 22, (12, 17), (12, 26), 10, "8P/Tuttle", "Ursa Minor",
                 "Minor shower near the December solstice."),
]


@dataclass(frozen=True, slots=True)
class CometRecord:
    designation: str
    name: str
    year: int
    """Astronomical year numbering."""
    perihelion_note: str
    evidence: str
    """'computed_return', 'historical_record', or 'both'."""
    records: list[str] = field(default_factory=list)
    source: str = KRONK_REFERENCE

    def to_dict(self) -> dict:
        era = f"{self.year} CE" if self.year > 0 else f"{1 - self.year} BCE"
        return {
            "designation": self.designation,
            "name": self.name,
            "year": self.year,
            "year_label": era,
            "perihelion_note": self.perihelion_note,
            "evidence": self.evidence,
            "records": self.records,
            "source": self.source,
        }


#: Halley apparitions are the backwards integration of Yeomans & Kiang, cross-checked
#: against Chinese and European records. Other entries are notable recorded comets.
COMET_APPARITIONS: list[CometRecord] = [
    CometRecord("1P/-239 K1", "Halley's Comet", -239, "Perihelion 25 May 240 BCE",
                "both", ["Shiji (Records of the Grand Historian), Chinese observation"],
                YEOMANS_REFERENCE),
    CometRecord("1P/-163 U1", "Halley's Comet", -163, "Perihelion 12 November 164 BCE",
                "both", ["Babylonian astronomical diaries BM 41462"], YEOMANS_REFERENCE),
    CometRecord("1P/-86 Q1", "Halley's Comet", -86, "Perihelion 6 August 87 BCE", "both",
                ["Babylonian tablet BM 41628", "Chinese records, Han shu"], YEOMANS_REFERENCE),
    CometRecord("1P/-11 Q1", "Halley's Comet", -11, "Perihelion 10 October 12 BCE", "both",
                ["Chinese records", "Cassius Dio, Roman History 54.29 — a comet before the "
                 "death of Agrippa"], YEOMANS_REFERENCE),
    CometRecord("1P/66 B1", "Halley's Comet", 66, "Perihelion 25 January 66 CE", "both",
                ["Josephus, The Jewish War 6.289 — 'a star resembling a sword' over "
                 "Jerusalem; the identification with Halley is a scholarly inference, "
                 "not something Josephus states"], YEOMANS_REFERENCE),
    CometRecord("1P/141 F1", "Halley's Comet", 141, "Perihelion 22 March 141 CE",
                "computed_return", [], YEOMANS_REFERENCE),
    CometRecord("1P/218 H1", "Halley's Comet", 218, "Perihelion 17 May 218 CE", "both",
                ["Chinese records; Roman sources note a comet before the fall of Macrinus"],
                YEOMANS_REFERENCE),
    CometRecord("1P/295 J1", "Halley's Comet", 295, "Perihelion 20 April 295 CE", "both",
                ["Chinese records"], YEOMANS_REFERENCE),
    CometRecord("1P/374 E1", "Halley's Comet", 374, "Perihelion 16 February 374 CE", "both",
                ["Chinese records"], YEOMANS_REFERENCE),
    CometRecord("1P/451 L1", "Halley's Comet", 451, "Perihelion 28 June 451 CE", "both",
                ["European chronicles associate it with the Battle of the Catalaunian Plains"],
                YEOMANS_REFERENCE),
    CometRecord("1P/530 Q1", "Halley's Comet", 530, "Perihelion 27 September 530 CE", "both",
                ["Chinese and Byzantine records"], YEOMANS_REFERENCE),
    CometRecord("1P/607 H1", "Halley's Comet", 607, "Perihelion 15 March 607 CE", "both",
                ["Chinese records"], YEOMANS_REFERENCE),
    CometRecord("1P/684 R1", "Halley's Comet", 684, "Perihelion 2 October 684 CE", "both",
                ["Depicted in the Nuremberg Chronicle (1493), retrospectively"],
                YEOMANS_REFERENCE),
    CometRecord("1P/760 K1", "Halley's Comet", 760, "Perihelion 20 May 760 CE",
                "computed_return", [], YEOMANS_REFERENCE),
    CometRecord("1P/837 F1", "Halley's Comet", 837, "Perihelion 28 February 837 CE", "both",
                ["Approached to about 0.03 au — the closest recorded Halley apparition"],
                YEOMANS_REFERENCE),
    CometRecord("1P/912 J1", "Halley's Comet", 912, "Perihelion 18 July 912 CE", "both",
                ["Chinese, Japanese and European records"], YEOMANS_REFERENCE),
    CometRecord("1P/989 N1", "Halley's Comet", 989, "Perihelion 5 September 989 CE", "both",
                ["Chinese and Japanese records"], YEOMANS_REFERENCE),
    CometRecord("1P/1066 G1", "Halley's Comet", 1066, "Perihelion 20 March 1066", "both",
                ["Anglo-Saxon Chronicle", "Depicted in the Bayeux Tapestry"],
                YEOMANS_REFERENCE),
    CometRecord("1P/1145 G1", "Halley's Comet", 1145, "Perihelion 18 April 1145", "both",
                ["Eadwine Psalter drawing"], YEOMANS_REFERENCE),
    CometRecord("1P/1222 R1", "Halley's Comet", 1222, "Perihelion 28 September 1222", "both",
                ["Japanese, Chinese and Korean records"], YEOMANS_REFERENCE),
    CometRecord("1P/1301 R1", "Halley's Comet", 1301, "Perihelion 25 October 1301", "both",
                ["Widely held to be Giotto's model for the Star of Bethlehem in the "
                 "Adoration of the Magi (Scrovegni Chapel)"], YEOMANS_REFERENCE),
    CometRecord("1P/1378 S1", "Halley's Comet", 1378, "Perihelion 10 November 1378", "both",
                ["Chinese and Korean records"], YEOMANS_REFERENCE),
    CometRecord("1P/1456 K1", "Halley's Comet", 1456, "Perihelion 9 June 1456", "both",
                ["Observed during the Ottoman siege of Belgrade",
                 "Observed by Paolo dal Pozzo Toscanelli"], YEOMANS_REFERENCE),
    CometRecord("1P/1531 P1", "Halley's Comet", 1531, "Perihelion 26 August 1531", "both",
                ["Observed by Peter Apian"], YEOMANS_REFERENCE),
    CometRecord("1P/1607 S1", "Halley's Comet", 1607, "Perihelion 27 October 1607", "both",
                ["Observed by Johannes Kepler"], YEOMANS_REFERENCE),
    CometRecord("1P/1682 Q1", "Halley's Comet", 1682, "Perihelion 15 September 1682", "both",
                ["Observed by Edmond Halley, who predicted its return"], YEOMANS_REFERENCE),
    CometRecord("1P/1758 Y1", "Halley's Comet", 1759, "Perihelion 13 March 1759", "both",
                ["First predicted return of a comet"], YEOMANS_REFERENCE),
    CometRecord("1P/1835 P1", "Halley's Comet", 1835, "Perihelion 16 November 1835", "both",
                [], YEOMANS_REFERENCE),
    CometRecord("1P/1909 R1", "Halley's Comet", 1910, "Perihelion 20 April 1910", "both",
                ["Earth passed through the tail on 19 May 1910"], YEOMANS_REFERENCE),
    CometRecord("1P/1982 U1", "Halley's Comet", 1986, "Perihelion 9 February 1986", "both",
                ["Giotto spacecraft encounter"], YEOMANS_REFERENCE),
    CometRecord("C/-43 K1", "Caesar's Comet (Sidus Iulium)", -43,
                "Appeared July 44 BCE during the games honouring the murdered Caesar",
                "historical_record",
                ["Pliny, Natural History 2.93–94", "Suetonius, Julius 88",
                 "Chinese records of a comet in the same period"]),
    CometRecord("C/1P-adjacent 837", "Great Comet of 837", 837,
                "Approached to about 0.03 au, one of the closest recorded",
                "historical_record", ["Chinese records", "Astronomer's Life of Louis the Pious"]),
    CometRecord("C/1577 V1", "Great Comet of 1577", 1577,
                "Tycho Brahe's parallax measurements placed it beyond the Moon",
                "both", ["Tycho Brahe, De mundi aetherei recentioribus phaenomenis (1588)"]),
    CometRecord("C/1811 F1", "Great Comet of 1811", 1811,
                "Visible to the naked eye for about 260 days", "both",
                ["Widely noted in European and American sources"]),
    CometRecord("C/1843 D1", "Great March Comet of 1843", 1843,
                "A Kreutz sungrazer with an exceptionally long tail", "both",
                ["Widely observed; contributed to Millerite expectations in the USA"]),
    CometRecord("C/1858 L1", "Comet Donati", 1858, "One of the most photographed of its era",
                "both", []),
]

# Historical supernovae attested in contemporary records.
HISTORICAL_SUPERNOVAE = [
    {"designation": "SN 185", "year": 185, "constellation": "Circinus/Centaurus",
     "record": "Book of Later Han — a 'guest star' visible about eight months",
     "modern_remnant": "RCW 86", "evidence": "historical_record"},
    {"designation": "SN 386", "year": 386, "constellation": "Sagittarius",
     "record": "Book of Jin", "modern_remnant": "G11.2-0.3 (debated)",
     "evidence": "historical_record"},
    {"designation": "SN 1006", "year": 1006, "constellation": "Lupus",
     "record": "Recorded in Chinese, Japanese, Arabic (Ali ibn Ridwan) and European sources; "
               "the brightest stellar event in recorded history",
     "modern_remnant": "SNR 1006", "evidence": "both"},
    {"designation": "SN 1054", "year": 1054, "constellation": "Taurus",
     "record": "Song dynasty records describe a guest star visible in daylight for 23 days",
     "modern_remnant": "Crab Nebula (M1)", "evidence": "both"},
    {"designation": "SN 1181", "year": 1181, "constellation": "Cassiopeia",
     "record": "Chinese and Japanese records", "modern_remnant": "Pa 30 (proposed)",
     "evidence": "historical_record"},
    {"designation": "SN 1572", "year": 1572, "constellation": "Cassiopeia",
     "record": "Tycho Brahe, De nova stella — evidence against the immutability of the heavens",
     "modern_remnant": "Tycho's SNR", "evidence": "both"},
    {"designation": "SN 1604", "year": 1604, "constellation": "Ophiuchus",
     "record": "Johannes Kepler, De stella nova", "modern_remnant": "Kepler's SNR",
     "evidence": "both"},
]

#: The 12 zodiac *signs* are 30° each from the vernal point. The 13 zodiac
#: *constellations* are unequal IAU sky regions. Conflating them is the most common
#: astronomical error in popular writing about ancient texts, so both are exposed.
ZODIAC_SIGN_BOUNDARIES = [(index * 30, (index + 1) * 30) for index in range(12)]

#: Approximate IAU constellation boundaries along the ecliptic, in degrees of ecliptic
#: longitude of date. Ophiuchus is included because the ecliptic genuinely passes through it.
ECLIPTIC_CONSTELLATIONS = [
    (28.7, 53.5, "Aries"), (53.5, 90.4, "Taurus"), (90.4, 118.0, "Gemini"),
    (118.0, 138.0, "Cancer"), (138.0, 174.0, "Leo"), (174.0, 218.0, "Virgo"),
    (218.0, 241.0, "Libra"), (241.0, 248.0, "Scorpius"), (248.0, 266.0, "Ophiuchus"),
    (266.0, 300.0, "Sagittarius"), (300.0, 327.7, "Capricornus"), (327.7, 351.6, "Aquarius"),
    (351.6, 388.7, "Pisces"),
]


def ecliptic_constellation(longitude: float) -> str:
    """The IAU constellation the ecliptic longitude falls in (not the astrological sign)."""
    value = longitude % 360.0
    for start, end, name in ECLIPTIC_CONSTELLATIONS:
        if start <= value < end or (end > 360 and value < end - 360):
            return name
    return "Pisces"


def showers_active_on(month: int, day: int) -> list[dict]:
    """Which showers were active on a given calendar date, peak first."""

    def in_window(shower: MeteorShower) -> bool:
        start, end = shower.active_start, shower.active_end
        target = (month, day)
        if start <= end:
            return start <= target <= end
        return target >= start or target <= end  # window wraps the new year

    active = [s for s in METEOR_SHOWERS if in_window(s)]
    active.sort(key=lambda s: (abs(s.peak_month - month) * 31 + abs(s.peak_day - day)))
    return [s.to_dict() for s in active]


def comets_near_year(year: int, window: int = 3) -> list[dict]:
    return [c.to_dict() for c in COMET_APPARITIONS if abs(c.year - year) <= window]


def supernovae_near_year(year: int, window: int = 3) -> list[dict]:
    return [s for s in HISTORICAL_SUPERNOVAE if abs(int(s["year"]) - year) <= window]


__all__ = [
    "MeteorShower",
    "CometRecord",
    "METEOR_SHOWERS",
    "COMET_APPARITIONS",
    "HISTORICAL_SUPERNOVAE",
    "ZODIAC_SIGN_BOUNDARIES",
    "ECLIPTIC_CONSTELLATIONS",
    "ecliptic_constellation",
    "showers_active_on",
    "comets_near_year",
    "supernovae_near_year",
    "IMO_REFERENCE",
    "KRONK_REFERENCE",
    "YEOMANS_REFERENCE",
]
