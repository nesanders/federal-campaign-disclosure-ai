"""U.S. Census Bureau population estimates, used only to scale this
project's small state-level AI-vendor-spend sample up to a national
order-of-magnitude projection (see build_projection.py). Vintage 2024
estimates, as of July 1, 2024 -- the most recent vintage available when
this file was written (Sep 2026); update when a newer vintage ships.

Source: U.S. Census Bureau, "New 2024 Population Estimates Show Nation's
Population Grew by About 1% to 340.1 Million Since 2023" (Dec 2024) and
the Vintage 2024 national/state population estimates press kit:
https://www.census.gov/newsroom/press-kits/2024/national-state-population-estimates.html
"""

# Population as of July 1, 2024, for the states this project's pipeline
# currently covers -- not all 50 states.
STATE_POPULATION_2024 = {
    "ma": 7_136_171,
    "wa": 7_958_180,
    "co": 5_957_493,
    "ca": 39_431_263,
}

# All 50 states + DC, July 1, 2024.
US_TOTAL_POPULATION_2024 = 340_110_988
