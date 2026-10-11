"""Schema provider: PHP model public-property reader.

Extracts the field NAMES a PHP response model puts on the wire — the source
of truth for an endpoint's SHAPE (values live in the fixture instead).

Convention this provider depends on: the model file declares its wire shape
through PUBLIC instance properties — the shape `json_encode($model)` emits.
That covers every real spelling: typed (`public string $id;`), readonly
(`public readonly int $ttl;`), legacy untyped (`public $title;` — common in
PHP 7-era libraries and in jikan's model classes), and promoted constructor
properties (`__construct(public string $id, …)`), which the object carries
and json_encode emits like any other public property.

`protected` and `private` properties are NOT on the wire and are not
counted — the leading keyword is required by the pattern, so a private
dependency (`private Jikan $client;`) never reads as a response field.
`static` properties are class state, not instance state, and are excluded
by the same shape: in `public static array $cache;` the regex tries to read
`static` as the property's type, fails to find the `$name` after it, and
moves on — no keyword blacklist needed, the grammar does the filtering.

A model that maps fields through `toArray()` or a serializer instead of
public properties is a DIFFERENT convention; registering it under this
provider would report every real field as absent (loudly, as drift on every
contract — not silently). Write that provider (`php_toarray.py`) rather
than widening this one to guess between conventions.

Comment-stripping is imported from the php language adapter rather than
re-implemented: comment syntax is one fact about PHP, and two copies of it
would drift apart. The provider seam and the adapter seam stay independent
— mock_api/config.json picks the provider, adapters.lang picks the
adapter, and neither setting requires the other.
"""
from __future__ import annotations

import re
from pathlib import Path

from backend_suite.adapters.php import blank_comments

# A public instance property, in any of its real spellings — see the module
# docstring for why `static` and the missing-`$` forms fall out naturally.
# First-appearance order is preserved by findall, matching the dart
# provider's contract.
PUBLIC_PROPERTY_RE = re.compile(
    r"\bpublic\s+(?:readonly\s+)?(?:[\w\\|?&]+\s+)?\$(\w+)")


def read_fields(model_file: Path) -> list[str]:
    """Field names as declared anywhere in `model_file`, in first-appearance
    order."""
    text = blank_comments(model_file.read_text())
    seen: list[str] = []
    for field in PUBLIC_PROPERTY_RE.findall(text):
        if field not in seen:
            seen.append(field)
    return seen
