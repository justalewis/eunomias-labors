# Eunomia's Labors

A four-page site offering DOI registration and Crossref reference backfilling to
rhetoric and composition journals. Sister site to [Pinakes](https://pinakes.xyz).

Server-rendered Flask, no JavaScript framework, no build step. The one moving
part is the coverage table, which reads `data/coverage.json` — refreshed nightly
from the Crossref API — so the argument on the landing page keeps itself current
as journals deposit.

## Run it

```bash
pip install -r requirements.txt
python crossref_refresh.py     # builds data/coverage.json (~80 API calls, 1 min)
python app.py                  # http://127.0.0.1:5000
```

Fonts and images are committed, so a checkout runs as-is. Regenerate them only
when the family list or the asset list changes:

```bash
python tools/fetch_fonts.py    # 23 woff2 faces -> static/fonts/ + static/fonts.css
python tools/fetch_images.py   # AVIF + WebP -> static/img/ + manifest.json
```

The site renders without `coverage.json`; the table is replaced by a note telling
you to run the refresh.

## Pages

| Route | What it does |
|---|---|
| `/` | The gap, the live evidence table, the two services, the cost, the ask |
| `/how` | Seven process stages, the questions boards ask, and the method behind the numbers |
| `/eunomia-and-pinakes` | The disclosure of interest, and why it's the argument rather than a caveat |
| `/start` | Contact form that doubles as intake triage |

## The coverage table

The table carries two metrics, because the site offers two services. **DOI
records** is the minting half: how much of a journal's published output is
registered at all. **Reference lists** is the backfill half: how many of those
records carry their works cited. A journal can be at 100% on the first and 0% on
the second, and eight of them here are.

`data/journals.json` is the input: a hand-curated list of 49 journals, each with
a name, publisher, ISSN, an optional `status`, and an `indexed_articles` count.

- `"status": "done"` highlights the row as work already completed.
- `"status": "queued"` is a note to yourself; it doesn't render.
- `"issn": null` means the journal has no Crossref presence at all — it shows 0
  DOI records against however many articles it has published, which is the point
  rather than a gap in the data.
- `"indexed_articles"` is the denominator for the DOI percentage: the article
  count [pinakes.xyz/coverage](https://pinakes.xyz/coverage) has for that
  journal, which is the closest available stand-in for what it has actually
  published. `null` where Pinakes doesn't index it, and the column shows a count
  with no percentage.

**Read the DOI percentage with its caveat.** Where Pinakes draws its own records
from Crossref, the two counts come from one pipeline and agree by construction,
so 100% there means "nothing missing that Crossref knows about" rather than an
independent check. It earns its keep on the journals Pinakes indexes some other
way: *Peitho* is at 33%, *Rhetorica* at 60%, and the eleven venues with no
Crossref presence at all are at 0%.

`crossref_refresh.py` asks Crossref two questions per journal:

```
api.crossref.org/works?filter=issn:XXXX-XXXX&rows=0
api.crossref.org/works?filter=issn:XXXX-XXXX,has-references:true&rows=0
```

and reads `total-results` off each. Rows sort **best-first**, because the landing
page says the four backfilled journals "sit at the top of that table" and they
have to actually be there. Journals with no Crossref presence at all sort last.
To put the worst first instead, flip both comparisons in the sort key at
`crossref_refresh.py` — the prose above the table would then need to change too.

Every number was independently re-derived before launch by a second method that
never touches the `has-references` filter: paging all ~56,000 registered records
across the 37 journals with an ISSN and counting from the `references-count`
field on each. Both methods agree on all 37, with no exceptions.

**If a journal returns zero registered records, the refresh aborts** rather than
publishing a zero. In practice that always means the ISSN is wrong, not that the
journal vanished — two of the original 49 were wrong on the first run. The
previous `coverage.json` is left in place, because a table that's a day stale
beats a table that's wrong.

To add a journal: add it to `journals.json` and re-run the refresh.

## The form

On success it stores the row, emails Justin, and sends the submitter the
acknowledgement the copy specifies. All three are independent: a mail failure
never costs a submission, and never produces a 500 after the row has committed.

Two rate-limit ceilings per client per hour, because they guard different things:

- **30 attempts** — stops a flood.
- **5 accepted** — stops spam.

An editor who mistypes their email four times isn't locked out by their own
typos, which a single combined ceiling would have done. Clients are keyed by
IPv6 /64 rather than by exact address: a routed /64 is the standard VPS
allocation, so keying on the full address would hand an attacker 2^64 free
buckets and switch the limiter off entirely.

The honeypot is an off-screen `eu_confirm` field — deliberately not named
`website`, which a password manager or form-fill profile can recognise and fill
in for a real person. A tripped honeypot is logged, so a false positive is
recoverable rather than invisible.

## Accessibility

Audited against WCAG 2.2 AA before launch, five independent passes plus an
adjudication. What that changed:

- **Printing `/how` with JavaScript blocked produced eight questions and zero
  answers.** The accordion was opened only by `faq.js` on `beforeprint`. The
  print block now opens every answer in CSS, so a board gets a complete handout
  from any browser in any configuration. It also un-caps the coverage table
  (which otherwise printed nine of forty-nine rows, clipped with no signal),
  repeats the table header on every page, prints link addresses, and keeps
  answers from splitting across a page break.
- **The "these are the six I did" highlight was carried by colour alone.** The
  rule set `font-weight: 600` on a `th`, which the UA already renders at 700 —
  so the marked rows were *lighter* than the rest and the intended non-colour cue
  ran backwards, leaving a 1.26:1 tint. They now carry an inset accent bar, and a
  `▸` character marker in print, where backgrounds are dropped.
- Contrast: `--muted`, `--muted-2` and `--rule-strong` were all raised. The last
  one draws every form-field border and sat at 1.5:1, half the 3:1 that WCAG
  1.4.11 requires for a control boundary.
- Form errors now take focus. A `role="alert"` region that is already in the
  HTML at parse time is not announced by any screen reader, so a blind user
  submitting an invalid form got a page that seemed not to have changed.
- Each FAQ answer has a stable id, so a board member can be sent to
  `/how#ethics` rather than "scroll down and click the seventh triangle."
- `main` is focusable, so the skip link moves the AT cursor and not just the
  scroll position.

## Design — the Alexandrian suite

This site no longer uses the Lewis Design System. The visual grammar is the
critical apparatus Aristophanes of Byzantium and Aristarchus used in the margins
at Alexandria, because those marks are the historical ancestors of the citation
apparatus this site exists to repair.

- **The paragraphos** — a short stroke in the *left margin* closing a passage —
  is the section divider. It hangs in the gutter rather than running full width,
  which is what it actually did in a book roll.
- **The diple** marks the process steps and, in the coverage table, the rows that
  are your work. It is a mark rather than a background tint, so it survives a
  printout with background graphics off and never depends on colour alone.
- **The coronis** closes each page.
- **The obelos** (`.obelized`) is a content state rather than an ornament: when
  Crossref changes a schema, superseded guidance is kept in place at reduced
  contrast with a dated note instead of being deleted. Zenodotus's obelos meant
  *this is in the manuscript but I judge it doesn't belong* — the line stayed,
  the judgement went beside it.

**Palette** (`static/tokens.css`) is sampled from Attic red-figure: fired black
gloss `#1C1A17`, reserved terracotta `#A8462C`, dilute glaze `#6A5F4E`, papyrus
`#F5EFE1`. Dark mode is not a theme hack — a red-figure vase is already a
dark-ground design, so inverting gloss and clay is black-figure.

Terracotta stays under 5% of any painted area, and there is deliberately **no
second warm hue** — no gold, no olive, no laurel green. That restraint is the
whole trick. Faience blue `#4A6670` does exactly one job: it marks *absence*.
A journal with no DOIs at all reads blue; nothing that is merely low reads blue.

**Type**, all OFL and self-hosted:

| Face | Role | Why this one |
|---|---|---|
| GFS Didot | display | Greek Font Society, full polytonic Greek, so Εὐνομία and Πίνακες set properly rather than transliterated |
| Literata | body | Built for long reading, Greek subset, warmer than the usual grotesque |
| EB Garamond italic | captions, wordmark | One line at a time. It was tried on the ledes and pulled — beautiful as a standfirst, punishing at ninety words |
| Atkinson Hyperlegible | interface, data | Commissioned by the Braille Institute for low-vision readers. On a site arguing that scholarly infrastructure should be legible, the interface face may as well make the argument too |

Nothing loads from a third party. `tools/fetch_fonts.py` pulls Google's
already-subset woff2 files and writes `static/fonts.css` with local paths, which
is why the CSP is `style-src 'self'; font-src 'self'` with no external host.
The papyrus grain is an SVG turbulence filter in a data URI: ~700 bytes, no
request, scales to any viewport.

**Images** come from `tools/fetch_images.py`, catalogued in
`static/img/manifest.json`. Every asset is CC0 or public domain; ShareAlike is
excluded on purpose, because it is viral in exactly the direction a design system
runs. Public-domain *object* and public-domain *photograph* are different things
— a faithful reproduction of a flat work generates no new copyright, but a
photograph of a three-dimensional object does, which rules out most of the
tempting vase images on Commons. Generate the credits page from the manifest
rather than keeping a list by hand, and re-verify it annually.

**Weight:** a first English page load is about 412 KB — 287 KB latin fonts,
88 KB hero image, 33 KB CSS, 4 KB JS. Greek faces load only when Greek appears,
and everything is immutable-cached for a year after the first visit.

> **Still worth fixing on Pinakes:** its Content-Security-Policy sets `style-src
> 'self' 'unsafe-inline' fonts.googleapis.com`, which omits
> `justalewis.github.io` — so its design tokens are refused on every page load
> and the site renders on its inline fallback, which is why the type comes out as
> Georgia instead of Cormorant Garamond. The GoatCounter beacon is blocked by the
> same policy. This site avoids the class of problem entirely by serving
> everything from its own origin.

## Deploy

```bash
fly launch --no-deploy --name eunomias-labors     # once; keeps the committed fly.toml
fly volumes create eunomia_data --size 1 --region sea
fly secrets set SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=...                 SMTP_FROM=jlewis2@olympic.edu NOTIFY_TO=jlewis2@olympic.edu
fly deploy
fly open
```

Fly builds the image remotely, so Docker isn't needed locally. You're already
authenticated as `justalewis1@gmail.com`.

Submissions and the generated `coverage.json` both live on the mounted volume at
`/data`, so a deploy doesn't discard them and the refresh writes where the app
reads. `journals.json` stays in the image, so adding a journal is a normal
commit-and-deploy.

The refresh has to run **on the machine holding the volume**. `fly machine run`
starts a separate machine, and a Fly volume attaches to only one machine at a
time, so that machine's write would be silently discarded:

```bash
fly ssh console -C "python /app/crossref_refresh.py"
```

Confirm it actually ran after the first deploy — the failure mode it replaces
was completely silent, with the caption still promising "pulled live" over a
table frozen at deploy time.

### Mail

Sent through **Resend**, which offers plain SMTP, so the app code is provider-
agnostic. Everything except the API key is already set as a Fly secret.

Gmail was tried first and abandoned: app passwords require hunting down a page
Google no longer reliably links from the 2-Step Verification screen, and a
personal Gmail relaying server mail is fragile in a way this doesn't need to be.

The one remaining value is `SMTP_PASSWORD`, a Resend API key. Set it at
<https://fly.io/apps/eunomias-labors/secrets>, then run `fly secrets deploy` —
the dashboard stages a secret but does **not** restart the machine, which is a
genuinely easy hour to lose.

While the sending domain is unverified, Resend restricts you to sending *from*
`onboarding@resend.dev` and *to* the address the account was registered with. If
the account is registered as `jlewis2@olympic.edu`, notifications work with no
DNS at all; the acknowledgement to the submitter will fail until the domain is
verified, which is logged and costs nothing else. To lift both limits, verify
`eunomiaslabors.xyz` in Resend, add the three DNS records it gives you at
Namecheap, and change `SMTP_FROM` to `forms@eunomiaslabors.xyz`.

Without any of this the form still works: submissions store to SQLite and nothing
is lost. See `.env.example` for the variable names.

To put a domain on it:

```bash
fly certs add eunomiaslabors.xyz
fly certs show eunomiaslabors.xyz      # prints the A/AAAA records to set
```

## License

GPL-3.0. See `LICENSE`.
