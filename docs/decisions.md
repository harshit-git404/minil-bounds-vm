# Architectural and Engineering Decisions Log

This document records architectural, design, and engineering decisions made during the implementation and evaluation of `minil-bounds-vm`.

---

## Decision 1: Tracking Canonical Bounds Trap Sites
- **Context**: When code transformations like loop-guard hoisting duplicate loops, PC addresses of array accesses can change between baseline (R) and transformed (H) modes.
- **Decision**: In addition to opcode-level reporting, every array access site in MiniL source retains a compile-time static `site_id`. Bounds check errors report PC, array name, and `site_id` (encoded in instruction operand `b` where unused, or mapped via symbol table). This ensures canonical comparison across modes during differential testing.

## Decision 2: Static Analysis Interval Domain Assumptions
- **Context**: Standard interval abstract interpretation assumes ideal integers or explicit bit-width wrapping.
- **Decision**: MiniL assumes no 64-bit integer wraparound in program index expressions, consistent with Section III-D and VI of the paper design. The interval domain uses `[-inf, +inf]` over mathematical integers, truncating integer division, and C99 remainder bounds `x % N in [-(|N|-1), |N|-1]`.
