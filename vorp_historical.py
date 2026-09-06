import pandas as pd

# .print-button {{
#
#     background-color: #15803d;
#
# }}
#
#
# .print-button:hover {{
#
#     background-color: #166534;
#
# }}

# ============================================================
# 1. FILE LOCATIONS
# ============================================================

file_2025 = r"C:\Users\savet\Desktop\sportsref_2025.csv"
file_2024 = r"C:\Users\savet\Desktop\sportsref_2024.csv"
file_2023 = r"C:\Users\savet\Desktop\sportsref_2023.csv"

output_file = "fantasy_draft_rankings.html"


# ============================================================
# 2. LOAD AND CLEAN A SEASON
# ============================================================

def load_season(file_path, year):

    df = pd.read_csv(file_path)

    # Rename FantPos to Pos if necessary
    if "FantPos" in df.columns and "Pos" not in df.columns:
        df = df.rename(columns={"FantPos": "Pos"})

    required_columns = ["Player", "Pos", "PPR", "G"]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{file_path} is missing required columns: {missing}"
        )

    # Remove players without required information
    df = df.dropna(subset=["Player", "Pos"])

    # Convert numeric fields
    df["PPR"] = pd.to_numeric(
        df["PPR"],
        errors="coerce"
    )

    df["G"] = pd.to_numeric(
        df["G"],
        errors="coerce"
    )

    df = df.dropna(subset=["PPR", "G"])

    # Only players who actually played
    df = df[df["G"] > 0].copy()

    # Standardize positions
    df["Pos"] = df["Pos"].str.upper()

    # Only offensive fantasy positions
    df = df[
        df["Pos"].isin(["QB", "RB", "WR", "TE"])
    ].copy()

    # ========================================================
    # PPR POINTS PER GAME
    # ========================================================

    df["PPG"] = df["PPR"] / df["G"]

    df["Season"] = year

    return df


# ============================================================
# 3. DETERMINE REPLACEMENT LEVELS
# ============================================================

def calculate_replacement_levels(df):

    # 12-team league:
    #
    # 1 QB
    # 2 RB
    # 2 WR
    # 1 TE
    # 1 FLEX
    #
    # Therefore:
    # 12 QB starters
    # 24 RB starters
    # 24 WR starters
    # 12 TE starters
    # 12 FLEX starters

    required_starters = {
        "QB": 12,
        "RB": 24,
        "WR": 24,
        "TE": 12
    }

    position_players = {}

    # Sort each position by PPG
    for pos in ["QB", "RB", "WR", "TE"]:

        position_players[pos] = (
            df[df["Pos"] == pos]
            .sort_values(
                "PPG",
                ascending=False
            )
            .reset_index(drop=True)
        )

    # ========================================================
    # DETERMINE FLEX PLAYERS
    # ========================================================

    flex_candidates = []

    for pos in ["RB", "WR", "TE"]:

        players = position_players[pos]

        starter_count = required_starters[pos]

        # Players remaining after normal starters
        remaining = players.iloc[starter_count:].copy()

        remaining["Flex_Position"] = pos

        flex_candidates.append(remaining)

    if flex_candidates:

        flex_pool = pd.concat(
            flex_candidates,
            ignore_index=True
        )

    else:

        flex_pool = pd.DataFrame()

    # Highest-scoring 12 remaining RB/WR/TE players
    flex_players = (
        flex_pool
        .sort_values(
            "PPG",
            ascending=False
        )
        .head(12)
    )

    # Number of FLEX spots taken by each position
    flex_counts = (
        flex_players["Flex_Position"]
        .value_counts()
        .to_dict()
    )

    for pos in ["RB", "WR", "TE"]:
        flex_counts.setdefault(pos, 0)

    # ========================================================
    # REPLACEMENT LEVEL
    # ========================================================

    replacement_levels = {}

    # QB13 is replacement
    qb_rank = 12 + 1

    if len(position_players["QB"]) >= qb_rank:

        replacement_levels["QB"] = (
            position_players["QB"]
            .iloc[qb_rank - 1]["PPG"]
        )

    elif len(position_players["QB"]) > 0:

        replacement_levels["QB"] = (
            position_players["QB"]
            .iloc[-1]["PPG"]
        )

    else:

        replacement_levels["QB"] = 0

    # RB / WR / TE
    for pos in ["RB", "WR", "TE"]:

        # Number of players expected to be used
        # at this position before replacement.
        players_used = (
            required_starters[pos]
            + flex_counts[pos]
        )

        # Next player is replacement.
        replacement_rank = players_used + 1

        players = position_players[pos]

        if len(players) >= replacement_rank:

            replacement_levels[pos] = (
                players
                .iloc[replacement_rank - 1]["PPG"]
            )

        elif len(players) > 0:

            replacement_levels[pos] = (
                players.iloc[-1]["PPG"]
            )

        else:

            replacement_levels[pos] = 0

    return replacement_levels, flex_counts


# ============================================================
# 4. CALCULATE SINGLE-SEASON VORP
# ============================================================

def calculate_season_vorp(df, year):

    replacement_levels, flex_counts = (
        calculate_replacement_levels(df)
    )

    df = df.copy()

    # Replacement PPG for player's position
    df["Replacement_PPG"] = (
        df["Pos"].map(replacement_levels)
    )

    # ========================================================
    # VORP PER GAME
    # ========================================================

    df["VORP_PPG"] = (
        df["PPG"]
        - df["Replacement_PPG"]
    )

    # ========================================================
    # ACTUAL SEASON VORP
    # ========================================================
    #
    # IMPORTANT:
    #
    # This uses the player's actual number of games.
    #
    # Season VORP =
    #
    # (Player PPG - Replacement PPG) * Games Played
    #
    # There is NO /17 and NO separate availability factor.
    #
    # ========================================================

    df["Season_VORP"] = (
        df["VORP_PPG"]
        * df["G"]
    )

    # Keep replacement level for reference
    df["Season_Replacement_PPG"] = (
        df["Replacement_PPG"]
    )

    return (
        df,
        replacement_levels,
        flex_counts
    )


# ============================================================
# 5. LOAD ALL THREE SEASONS
# ============================================================

df_2025 = load_season(
    file_2025,
    2025
)

df_2024 = load_season(
    file_2024,
    2024
)

df_2023 = load_season(
    file_2023,
    2023
)


# ============================================================
# 6. CALCULATE EACH SEASON
# ============================================================

df_2025, replacements_2025, flex_2025 = (
    calculate_season_vorp(
        df_2025,
        2025
    )
)

df_2024, replacements_2024, flex_2024 = (
    calculate_season_vorp(
        df_2024,
        2024
    )
)

df_2023, replacements_2023, flex_2023 = (
    calculate_season_vorp(
        df_2023,
        2023
    )
)


# ============================================================
# 7. DISPLAY REPLACEMENT LEVELS
# ============================================================




# ============================================================
# 9. PREPARE SEASON DATA
# ============================================================

def prepare_season_dataframe(df, year):

    columns = [
        "Player",
        "Pos",
        "G",
        "PPR",
        "PPG",
        "VORP_PPG",
        "Season_VORP",
        "Season_Replacement_PPG"
    ]

    columns = [
        col for col in columns
        if col in df.columns
    ]

    result = df[columns].copy()

    rename_map = {
        "G": f"G_{year}",
        "PPR": f"PPR_{year}",
        "PPG": f"PPG_{year}",
        "VORP_PPG": f"VORP_PPG_{year}",
        "Season_VORP": f"VORP_{year}",
        "Season_Replacement_PPG":
            f"Replacement_{year}"
    }

    result = result.rename(
        columns=rename_map
    )

    return result


df25 = prepare_season_dataframe(
    df_2025,
    2025
)

df24 = prepare_season_dataframe(
    df_2024,
    2024
)

df23 = prepare_season_dataframe(
    df_2023,
    2023
)


# ============================================================
# 10. MERGE THREE SEASONS
# ============================================================

all_players = pd.merge(
    df25,
    df24,
    on="Player",
    how="outer",
    suffixes=("", "_2024")
)

all_players = pd.merge(
    all_players,
    df23,
    on="Player",
    how="outer",
    suffixes=("", "_2023")
)


# ============================================================
# 11. STANDARDIZE POSITION
# ============================================================

if "Pos_2024" in all_players.columns:

    all_players["Pos"] = (
        all_players["Pos"]
        .combine_first(
            all_players["Pos_2024"]
        )
    )

if "Pos_2023" in all_players.columns:

    all_players["Pos"] = (
        all_players["Pos"]
        .combine_first(
            all_players["Pos_2023"]
        )
    )


# ============================================================
# 12. WEIGHTED THREE-YEAR VORP
# ============================================================
#
# 2025 = 50%
# 2024 = 25%
# 2023 = 25%
#
# This is based on ACTUAL SEASON VORP.
#
# Season VORP already incorporates Games Played:
#
#     (PPG - Replacement PPG) * G
#
# ============================================================

all_players["Weighted_VORP"] = (
    all_players["VORP_2025"].fillna(0) * 0.50
    + all_players["VORP_2024"].fillna(0) * 0.25
    + all_players["VORP_2023"].fillna(0) * 0.25
)


# ============================================================
# 13. WEIGHTED PPG
# ============================================================
#
# This is useful as a secondary reference.
#
# It is NOT used to calculate Draft Value.
#
# ============================================================

all_players["Weighted_PPG"] = (
    all_players["PPG_2025"].fillna(0) * 0.50
    + all_players["PPG_2024"].fillna(0) * 0.25
    + all_players["PPG_2023"].fillna(0) * 0.25
)


# ============================================================
# 14. RANK PLAYERS
# ============================================================

ranked_df = (
    all_players
    .sort_values(
        "Weighted_VORP",
        ascending=False
    )
    .reset_index(drop=True)
)

ranked_df["Draft_Rank"] = (
    ranked_df.index + 1
)


# ============================================================
# 15. ROUND NUMBERS
# ============================================================

number_columns = [
    "PPG_2025",
    "PPG_2024",
    "PPG_2023",
    "VORP_PPG_2025",
    "VORP_PPG_2024",
    "VORP_PPG_2023",
    "VORP_2025",
    "VORP_2024",
    "VORP_2023",
    "Weighted_PPG",
    "Weighted_VORP"
]

for col in number_columns:

    if col in ranked_df.columns:

        ranked_df[col] = (
            ranked_df[col]
            .round(2)
        )


# ============================================================
# 16. OUTPUT COLUMNS
# ============================================================

output_cols = [
    "Draft_Rank",
    "Player",
    "Tm",
    "Pos",

    "G_2025",
    "PPR_2025",
    "PPG_2025",
    "VORP_PPG_2025",
    "VORP_2025",

    "G_2024",
    "PPR_2024",
    "PPG_2024",
    "VORP_PPG_2024",
    "VORP_2024",

    "G_2023",
    "PPR_2023",
    "PPG_2023",
    "VORP_PPG_2023",
    "VORP_2023",

    "Weighted_PPG",
    "Weighted_VORP"
]

output_cols = [
    col
    for col in output_cols
    if col in ranked_df.columns
]

final_output = ranked_df[
    output_cols
]


# ============================================================
# 17. HTML TABLE
# ============================================================

html_table = final_output.to_html(
    index=False,
    classes=(
        "table table-striped "
        "table-hover table-bordered"
    )
)


# ============================================================
# 18. HTML PAGE
# ============================================================

html_content = f"""
<!DOCTYPE html>

<html>

<head>

    <title>
        Fantasy Football VORP Draft Board
    </title>

    <link
        rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css"
    >

    <style>

        body {{
            padding: 20px;
            background-color: #f8f9fa;
        }}

        h2 {{
            margin-bottom: 10px;
            color: #333;
        }}

        table {{
            background-color: #fff;
            font-size: 13px;
        }}

        th {{
            white-space: nowrap;
        }}

        td {{
            white-space: nowrap;
        }}

        .description {{
            margin-bottom: 20px;
        }}

    </style>

</head>

<body>

    <div class="container-fluid">

        <h2>
            12-Team Fantasy Football VORP Draft Rankings
        </h2>

        <p class="description text-muted">

            PPR scoring |
            12 teams |
            1 QB |
            2 RB |
            2 WR |
            1 TE |
            1 FLEX

            <br><br>

            <strong>
                VORP weighting:
            </strong>

            2025 = 50% |
            2024 = 25% |
            2023 = 25%

            <br>

            VORP is calculated using the player's
            actual games played in each season.

            <br>

            Season VORP =
            (Player PPG - Replacement PPG)
            × Games Played.

            <br>

            No separate availability adjustment is applied.

        </p>

        {html_table}

    </div>

</body>

</html>
"""


# ============================================================
# 19. SAVE HTML
# ============================================================

with open(
    output_file,
    "w",
    encoding="utf-8"
) as f:

    f.write(html_content)


# ============================================================
# 20. DISPLAY TOP 25
# ============================================================


print(
    f"\nSuccess! Draft rankings exported to "
    f"'{output_file}'."
)