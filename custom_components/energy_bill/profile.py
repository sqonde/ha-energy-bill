"""Monthly shares of annual household electricity consumption."""

# BDEW "Standardlastprofile Strom", H25 table 2025, dynamised over 2026–2035.
# Weekends use SA/FT; public holidays are ignored because they vary by state.
# Reproduce with scripts/h25_month_shares.py and the original workbook.
H25 = (
    0.100996,
    0.088761,
    0.088096,
    0.081474,
    0.077009,
    0.071414,
    0.074360,
    0.073475,
    0.073205,
    0.083567,
    0.088217,
    0.099424,
)
