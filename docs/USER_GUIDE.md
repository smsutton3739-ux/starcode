# User guide

Starcode analyses ancient texts, historical documents, astronomical references and
traditional prophecies. This guide covers how to use it — and, more importantly, how to
read what it gives back.

---

## Getting an analysis

1. Go to the homepage.
2. Paste your text into the box.
3. Press **ANALYZE**.

That is the whole flow. No account, no settings, no configuration.

You can also **paste a link** (the page is fetched and its text extracted) or **drag a
file** onto the box — PDF, Word document, plain text, or a photograph or scan of a
manuscript, which is put through OCR automatically.

Analysis usually takes under a minute. The progress panel names each stage as it runs, so
you can see what is happening rather than watching a spinner.

### Without an account

Analyses run without signing in. The catch is worth understanding before you rely on it:
an anonymous analysis is reachable only through a token stored **in your browser**. If you
clear your browser storage, or open the link on another device, it becomes unreachable.
There is no server-side recovery, because there is no account to tie it to.

If you want an analysis to survive that, sign in before running it, or export it.

---

## Reading a report

This is the part that matters.

### Every statement is labelled

Each finding carries a badge saying what kind of statement it is. The badge is not
decoration — it is the single most important thing on the page.

| Badge | What it means | Can you rely on it? |
| --- | --- | --- |
| ❝ **Source text** | Quoted verbatim from what you submitted | Yes — it is your own text |
| ✓ **Verified history** | Attested in the historical record, with a citation | Largely — check the citation |
| ∑ **Calculation** | Computed by the astronomy or calendar engine | Yes, within its stated accuracy |
| ❡ **Text analysis** | An observation about the text itself | Usually |
| ☽ **Tradition holds** | What a religious or cultural tradition has held | As a report of that tradition, yes. As a fact about the world, no |
| § **Scholars argue** | A position argued in academic literature | As a report of scholarship, yes |
| ? **AI hypothesis** | The model's own conjecture | **No.** A suggestion to evaluate |
| — **Unresolved** | Genuinely undetermined | It is telling you nobody knows |

The first three are **evidence**. Everything else is commentary, however reasonable it
sounds. Anything marked "not evidence" says so on the card.

### The evidence-only filter

At the top of every report there is an **Evidence only** button. It hides everything that
is not a quotation, a calculation, or cited history.

This is the fastest way to see what an analysis actually establishes. If turning it on
empties most of the report, that is a real and useful finding: the text supports very
little that can be checked, and the rest is interpretation. For symbolic and prophetic
material this is common and not a defect.

### Confidence

Every finding shows a confidence percentage and a band. Two things to keep in mind:

**Confidence is about the claim, not the topic.** A traditional interpretation at 80%
means "this tradition very likely does hold this reading", not "this reading is 80%
likely to be correct".

**AI hypotheses are capped.** No hypothesis can exceed 55%, however confident the model
sounds. This is a policy limit, not a measurement.

The *Confidence Ratings* section leads with a written rationale rather than a number,
because a bare percentage invites treating interpretation as measurement. Read that
paragraph before the figure.

### "Why this, and how sure?"

Every finding has this link. It opens the reasoning, what the confidence rests on, which
engine and algorithm produced it (for calculations), and the sources.

Use it whenever a finding matters to you. Provenance is the difference between a claim
you can check and one you cannot.

### Unverified citations

Some references are marked **unverified — check before citing**. These came from the
language model rather than the curated corpus.

Take this seriously. Language models invent references that look completely real —
plausible authors, plausible journals, plausible years, for works that do not exist.
Anything so marked must be confirmed before you rely on it.

Citations *not* so marked come from the platform's curated corpus and can be traced.

### Sections that say they are empty

A section reading *"This section requires a language model"* or *"No astronomical
references were detected"* is doing its job. It is telling you the platform found nothing
rather than filling the space with something that looks like a finding.

If a stage failed outright, the executive summary names it.

---

## Dates and calendars

Ancient dates are where confident-sounding tools go most badly wrong, so a few things are
worth knowing.

**A year is often a span, not a day.** "587 BC" is a Julian year, which straddles two
Gregorian ones. Starcode reports `26 December 588 BCE – 25 December 587 BCE`, because
that is the honest answer.

**BCE years use astronomical numbering internally.** Year 0 is 1 BCE, year −1 is 2 BCE.
Displayed dates are converted back to BCE/CE, but if you use the API directly this
matters.

**Some dates cannot be converted, and the report says why.** A regnal year ("the third
year of Belshazzar") needs a fixed accession date, and ancient accessions are frequently
disputed by years. A bare duration ("2300 days") has no anchor. A day and month with no
year cannot be placed. In each case the report names the specific obstacle instead of
inventing a date.

**Lunar calendars carry an inherent wobble.** The Hebrew and Islamic conversions use the
arithmetic calendars. Religious practice used — and for Islam still uses — observed
crescent sighting, which routinely differs by a day or two and varies by country. Every
such conversion says so.

**The Maya Long Count depends on a correlation constant.** Starcode uses the standard
GMT 584283 and reports the 584285 alternative alongside it; they differ by two days. You
can change this in advanced settings.

---

## Astronomy

The astronomy is computed, not looked up, from published algorithms. It reproduces the
Eclipse of Thales (28 May 585 BCE) and the Assyrian Bur-Sagale eclipse (15 June 763 BCE)
on the correct day, and modern eclipse geometry to about 0.0005.

### What it will not tell you

**Whether an eclipse was visible from a particular city.** It establishes that an eclipse
occurred, when, and of what type. Placing its shadow track requires knowing the Earth's
rotation to within seconds, and for ancient dates that is uncertain by tens of minutes —
which moves the track by tens of degrees of longitude. Any tool that shows you a precise
ancient eclipse path over a named city is claiming more than the physics supports.

**An exact day for a slow conjunction.** Jupiter and Saturn approach each other so
gradually that a small position error becomes about two weeks of date uncertainty. Each
conjunction reports that figure.

### Signs and constellations are different things

The report always shows both, and they will usually disagree.

- A **zodiac sign** is one of twelve equal 30° divisions measured from the spring equinox.
- A **zodiac constellation** is an unequal region of sky, and the ecliptic passes through
  thirteen of them, including Ophiuchus.

Because of precession the two have drifted about a full sign apart since they were
defined in antiquity. Conflating them is the commonest astronomical error in popular
writing about ancient texts, which is why Starcode never picks one for you.

### When it declines to correlate

If your text uses eclipse imagery but gives no date, the report will say a specific
eclipse cannot be proposed. That is deliberate. Over a few centuries there are thousands
of eclipses; a match found by searching for one near an arbitrary date is a coincidence,
not a finding.

Where a text *does* give a date, the report lists the eclipses of that year as
calculations, and offers the correlation separately as a hypothesis at low confidence.

---

## Working with scanned documents

Upload a photograph or scan and it goes through OCR automatically.

The result is always flagged as OCR, with an average confidence figure. Read that figure:
below about 70% the transcription likely contains substantial errors, and **every
conclusion drawn from it inherits that uncertainty**.

OCR of historical manuscripts fails in predictable ways — similar letterforms are
confused, diacritics and abbreviation marks are dropped, marginalia get interleaved with
the main text. Treat the transcription as a draft and verify anything the analysis turns
on against the original.

For better results: scan at higher resolution, keep the page flat and evenly lit, and
crop out surrounding material. For non-Latin scripts the server needs the matching
Tesseract language pack installed.

---

## Saving, sharing and exporting

**An account** keeps your analyses, lets you favourite and tag them, organise them into
collections, and search across everything you have run.

**Share links** give read access to one analysis. The link is shown once; it is stored
only as a hash and cannot be recovered, so if you lose it, revoke and make a new one.
Links can expire and can be revoked at any time.

**Exports** come in five formats:

| Format | Best for |
| --- | --- |
| **PDF** | Reading and printing; claim types are colour-coded |
| **DOCX** | Editing in Word, quoting into another document |
| **CSV** | Filtering and sorting; one row per claim, with the type as a column |
| **Markdown** | Notes, wikis, version control |
| **JSON** | Programmatic use; includes the full claim-type vocabulary |

Every format preserves the labelling. An exported PDF marks its hypotheses as hypotheses.

---

## The astronomy and calendar tools

**Explore** gives you the engines directly, without submitting a text:

- **Sky map** — where the Sun, Moon and naked-eye planets were on any date from 3000 BCE
  to 3000 CE, with both sign and constellation, retrograde markers, and moon phase.
- **Calendar converter** — one date across all twelve systems, with each system's caveats.
- **Eclipse finder** — every solar and lunar eclipse in a range, with type, magnitude and
  uncertainty.

---

## Advanced settings

Hidden by default, and genuinely optional — the defaults produce a full analysis. Worth
opening if you want to:

- **Widen the astronomical search window.** A wider window finds more events and makes any
  match *weaker* evidence, because coincidences become easy. The setting says so.
- **Change the Maya correlation constant.**
- **Choose an output language.**
- **Set the detail level** — brief, standard or exhaustive.

---

## What Starcode will not do

- **It will not tell you what a prophecy means.** It reports what traditions have held and
  what scholars argue, attributed, and leaves the judgement to you.
- **It will not predict the future.** Prophetic material is described and interpretations
  attributed; a prediction is never presented as a fact about what will happen.
- **It will not settle a religious question.** It describes traditions accurately, without
  endorsement and without mockery.
- **It will not pretend to know a date it cannot establish.**

If you want a tool that confidently tells you which ancient text predicted which modern
event, this is not it — and the reason is that no honest tool can.

---

## Getting good results

**Paste enough context.** A single line gives the engine little to work with. A paragraph
or a full chapter works far better.

**Include the dates the text gives.** Regnal years, era dates, month names — these are
what the calendar and astronomy engines have to work with.

**Keep the original if you can.** The platform detects language and script and can
translate, but analysis of an original is stronger than analysis of a translation of a
translation.

**Check the "Evidence only" view early.** It tells you immediately how much of the
analysis rests on something checkable.

**Follow the citations.** Especially the unverified ones.
