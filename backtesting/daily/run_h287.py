# H287: Janus-Q-style event type annotation for PEAD entry filter
# Source: arXiv:2602.19919 (Janus-Q)
# Design: classify H174 8-K text into event types using GPT-4o-mini
# Entry only when event type has mean IS CAR > 5%
# IS: 2018-2022, OOS: 2023-2025
# Gate: OOS WR > 81.8% (H174 baseline), n >= 15
#
# Event types (from Janus-Q taxonomy):
# 1. EarningsBeat        - EPS beat + positive surprise
# 2. EarningsMiss        - EPS miss
# 3. GuidanceRaise       - Forward guidance raised
# 4. GuidanceCut         - Forward guidance lowered
# 5. GuidanceInline      - No change to guidance
# 6. MarginExpansion     - Operating margin improvement noted
# 7. RevenueAcceleration - Revenue growth rate accelerating
# 8. Restructuring       - Cost cuts, layoffs, restructuring charges
# 9. MA                  - M&A announcement
# 10. Other              - None of the above
#
# TODO: implement classification using OpenAI API ($OPENAI_API_KEY)
# TODO: compute IS CAR per event type from cached H174 events
# TODO: OOS gate: enter only for event types with mean IS CAR > 5%
print('H287 scaffold - to be implemented')
