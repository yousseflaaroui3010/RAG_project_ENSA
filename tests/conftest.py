"""Test-wide settings.

The interface is French by default (S6, human ruling 2026-09-13). The test
suite written before that asserts the English wording, which is still a
supported language with its own complete catalog, so the whole suite runs
with English as the default interface language. The French and Arabic
catalogs are exercised by tests/unit/test_i18n.py and the language tests in
tests/integration/test_i18n_screens.py, which set the language explicitly
(`?lang=` or the cookie) and so do not depend on this default.

Set before any test module imports `config`, whose settings are cached.
An explicit DEFAULT_UI_LANGUAGE in the environment is respected.
"""

import os

os.environ.setdefault("DEFAULT_UI_LANGUAGE", "en")
