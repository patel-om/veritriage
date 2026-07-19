"""Built-in Knowledge Packs.

Importing this package registers every built-in pack. A new pack is a new
module here (or anywhere) whose factory carries ``@register_pack``; no
reasoning code, matcher code, or report code changes.
"""

from veritriage.knowledge.packs import axi, coverage, reset, uvm  # noqa: F401
