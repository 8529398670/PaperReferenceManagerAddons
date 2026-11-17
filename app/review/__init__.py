"""The review screener: each paper on a list (or with picked figures) is
screened against three inclusion criteria and has its architecture,
acquisition and preprocessing details pulled out of its text, one paper at a
time as the content queue reaches it.

  rules.py      the screener's rules as data (config/review.yaml, overridden
                by the owner's edits in the database), validated and compiled
  screen.py     the screening and extraction, reading only the rules
  service.py    the rules in use, the overrides, the dataset consensus, and
                the per-paper result as the screens read it
"""
