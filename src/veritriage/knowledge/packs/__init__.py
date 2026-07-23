"""Built-in Knowledge Packs.

Importing this package registers every built-in pack. A new pack is a new
module here (or anywhere) whose factory carries ``@register_pack``; no
reasoning code, matcher code, or report code changes.
"""

from veritriage.knowledge.packs import (  # noqa: F401
    ahb,
    apb,
    axi,
    cdc,
    chi,
    coherency,
    coverage,
    pcie,
    reset,
    riscv,
    sva,
    tilelink,
    uvm,
)
