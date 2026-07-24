"""Built-in Knowledge Packs.

Importing this package registers every built-in pack. A new pack is a new
module here (or anywhere) whose factory carries ``@register_pack``; no
reasoning code, matcher code, or report code changes.
"""

from veritriage.knowledge.packs import (  # noqa: F401
    ace,
    ahb,
    apb,
    axi,
    axi_stream,
    cdc,
    chi,
    coherency,
    coverage,
    cxl,
    noc,
    pcie,
    reset,
    riscv,
    riscv_atomics,
    riscv_debug,
    riscv_interrupts,
    riscv_memory_model,
    riscv_pmp,
    riscv_vector,
    sva,
    tilelink,
    ucie,
    uvm,
)
