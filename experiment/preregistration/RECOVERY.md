# Preregistration recovery note

The directory `experiment/` was already ignored by the local Git configuration.

Therefore the intended preregistration commit/tag did not contain
`experiment/preregistration/select_instances.py` or PROTOCOL.md.

This was discovered only after the audit and the single predefined sample draw.

The sampling procedure is NOT rerun.

Evidence:
- preregistration rules were already timestamped in canonical `shafed/obsidian`;
- SHA-256 during audit:
  24f195ef51764906ef6d6900e0807e24cd89f21ed6b1a3851eba45093f482b7e
- SHA-256 during sample draw:
  24f195ef51764906ef6d6900e0807e24cd89f21ed6b1a3851eba45093f482b7e
- audit selected step1 / primary split;
- first feasible seed was 118.

The sample produced by seed 118 is frozen and must not be redrawn.
