This folder holds the two data files the site reads, `journals.json` and
`coverage.json`. They are not in this repository. `journals.json` is the
hand-curated journal list that `crossref_refresh.py` surveys, and
`coverage.json` is the table it generates from that list. See the coverage
table section of the top-level README for how they fit together. Without
`coverage.json` the site still renders, with a note in place of the table.
