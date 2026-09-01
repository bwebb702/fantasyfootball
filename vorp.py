#chatgpt

import pandas as pd

FILE_2025 = r"C:\Brian\Python Projects\FantasyFootball\data\sportsref_2025.csv"
FILE_2024 = r"C:\Brian\Python Projects\FantasyFootball\data\sportsref_2024.csv"
FILE_2023 = r"C:\Brian\Python Projects\FantasyFootball\data\sportsref_2023.csv"

OUTPUT_FILE = "fantasy_draft_rankings.html"


# ============================================================
# LEAGUE SETTINGS
# ============================================================

# 12-team league:
#
# 1 QB
# 2 RB
# 2 WR
# 1 TE
# 1 FLEX
#
# Current baseline methodology:
#
# QB = QB12
# RB = RB24
# WR = WR24
# TE = TE12
#
# VORP is calculated as:
#
# Player PPG - Replacement Player PPG
#
# The FLEX is not separately allocated in this version.
#
BASELINES = {
    "QB": 13,
    "RB": 25,
    "WR": 25,
    "TE": 13
}


# ============================================================
# LOAD AND CLEAN CSV
# ============================================================

def process_csv(file_path):

    df = pd.read_csv(file_path)

    # Sports Reference sometimes uses FantPos
    if "FantPos" in df.columns and "Pos" not in df.columns:
        df = df.rename(columns={"FantPos": "Pos"})

    # Required columns
    required_columns = [
        "Player",
        "Pos",
        "PPR",
        "G"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"{file_path} is missing required columns: "
            f"{missing_columns}"
        )

    # Remove rows missing required information
    df = df.dropna(
        subset=[
            "Player",
            "Pos",
            "PPR",
            "G"
        ]
    ).copy()

    # Clean player names
    df["Player"] = (
        df["Player"]
        .astype(str)
        .str.rstrip("+")
        .str.rstrip("*")
        .str.strip()
    )

    # Convert numeric fields
    df["PPR"] = pd.to_numeric(
        df["PPR"],
        errors="coerce"
    )

    df["G"] = pd.to_numeric(
        df["G"],
        errors="coerce"
    )

    # Remove invalid rows
    df = df.dropna(
        subset=[
            "PPR",
            "G"
        ]
    )

    # Only players who actually played
    df = df[df["G"] > 0].copy()

    # Standardize positions
    df["Pos"] = (
        df["Pos"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    # Only fantasy football positions
    df = df[
        df["Pos"].isin(
            [
                "QB",
                "RB",
                "WR",
                "TE"
            ]
        )
    ].copy()

    # ========================================================
    # ACTUAL PPG
    # ========================================================

    df["PPG"] = (
        df["PPR"] /
        df["G"]
    )

    return df


# ============================================================
# FIND REPLACEMENT LEVEL AND CALCULATE VORP
# ============================================================

def find_baseline(
    df,
    baselines,
    prefix=""
):

    vorp_dfs = []

    for pos, baseline_rank in baselines.items():

        # ----------------------------------------------------
        # Filter to position
        # ----------------------------------------------------

        pos_df = df[
            df["Pos"] == pos
        ].copy()

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Because this is VORP PER GAME, replacement level
        # must also be determined using PPG.
        # ----------------------------------------------------

        pos_df = (
            pos_df
            .sort_values(
                by="PPG",
                ascending=False
            )
            .reset_index(drop=True)
        )

        # ----------------------------------------------------
        # Find replacement player
        # ----------------------------------------------------

        if len(pos_df) >= baseline_rank:

            replacement_player = (
                pos_df.iloc[
                    baseline_rank - 1
                ]
            )

            replacement_ppg = (
                replacement_player["PPG"]
            )

        elif len(pos_df) > 0:

            replacement_ppg = (
                pos_df.iloc[-1]["PPG"]
            )

        else:

            replacement_ppg = 0

        # ----------------------------------------------------
        # Store replacement PPG
        # ----------------------------------------------------

        pos_df[
            f"{prefix}Baseline_PPG"
        ] = round(
            replacement_ppg,
            2
        )

        # ----------------------------------------------------
        # VORP PER GAME
        #
        # VORP = Player PPG - Replacement PPG
        # ----------------------------------------------------

        pos_df[
            f"{prefix}VORP"
        ] = (
            pos_df["PPG"]
            - replacement_ppg
        ).round(2)

        # ----------------------------------------------------
        # PPG
        # ----------------------------------------------------

        pos_df[
            f"{prefix}PPG"
        ] = (
            pos_df["PPG"]
            .round(2)
        )

        vorp_dfs.append(pos_df)

    if vorp_dfs:

        return pd.concat(
            vorp_dfs,
            ignore_index=True
        )

    return pd.DataFrame()


# ============================================================
# LOAD THREE SEASONS
# ============================================================

df_2025 = process_csv(
    FILE_2025
)

df_2024 = process_csv(
    FILE_2024
)

df_2023 = process_csv(
    FILE_2023
)


# ============================================================
# CURRENT SEASON VORP
# ============================================================

current_vorp = find_baseline(
    df_2025,
    BASELINES,
    prefix="Current_"
)


# ============================================================
# COMBINE THREE SEASONS
# ============================================================
#
# Total PPR is added across the three seasons.
#
# Total games are added across the three seasons.
#
# Historical PPG is therefore:
#
#     PPR25 + PPR24 + PPR23
#     ---------------------
#       G25 + G24 + G23
#
# This uses actual games played.
#
# ============================================================

df_hist = pd.concat(
    [
        df_2025,
        df_2024,
        df_2023
    ],
    ignore_index=True
)


# Combine players
df_hist = (
    df_hist
    .groupby(
        [
            "Player",
            "Pos"
        ],
        as_index=False
    )
    .agg(
        G=("G", "sum"),
        PPR=("PPR", "sum")
    )
)


# ============================================================
# THREE-YEAR PPG
# ============================================================

df_hist["PPG"] = (
    df_hist["PPR"] /
    df_hist["G"]
)


# ============================================================
# HISTORICAL VORP
# ============================================================

historical_vorp = find_baseline(
    df_hist,
    BASELINES,
    prefix="Historical_"
)


# ============================================================
# PREPARE CURRENT DATA
# ============================================================

current_output = current_vorp[
    [
        "Player",
        "Pos",
        "G",
        "PPR",
        "Current_PPG",
        "Current_Baseline_PPG",
        "Current_VORP"
    ]
].copy()


current_output = current_output.rename(
    columns={
        "G": "Current_G",
        "PPR": "Current_PPR"
    }
)


# ============================================================
# PREPARE HISTORICAL DATA
# ============================================================

historical_output = historical_vorp[
    [
        "Player",
        "Pos",
        "G",
        "PPR",
        "Historical_PPG",
        "Historical_Baseline_PPG",
        "Historical_VORP"
    ]
].copy()


historical_output = historical_output.rename(
    columns={
        "G": "Historical_G",
        "PPR": "Historical_PPR"
    }
)


# ============================================================
# MERGE CURRENT AND HISTORICAL VORP
# ============================================================

ranked_df = pd.merge(
    current_output,
    historical_output,
    on=[
        "Player",
        "Pos"
    ],
    how="outer"
)


# ============================================================
# NUMERIC COLUMNS
# ============================================================

numeric_columns = [
    "Current_G",
    "Current_PPR",
    "Current_PPG",
    "Current_Baseline_PPG",
    "Current_VORP",

    "Historical_G",
    "Historical_PPR",
    "Historical_PPG",
    "Historical_Baseline_PPG",
    "Historical_VORP"
]


for column in numeric_columns:

    if column in ranked_df.columns:

        ranked_df[column] = pd.to_numeric(
            ranked_df[column],
            errors="coerce"
        )


# ============================================================
# ROUND NUMERIC VALUES
# ============================================================

for column in numeric_columns:

    if column in ranked_df.columns:

        ranked_df[column] = (
            ranked_df[column]
            .round(2)
        )


# ============================================================
# INITIAL OVERALL RANK
# ============================================================

ranked_df = (
    ranked_df
    .sort_values(
        by="Current_VORP",
        ascending=False,
        na_position="last"
    )
    .reset_index(drop=True)
)


ranked_df["Draft_Rank"] = (
    ranked_df.index + 1
)


# ============================================================
# OUTPUT COLUMNS
# ============================================================

output_cols = [

    "Draft_Rank",

    "Player",
    "Pos",

    "Current_G",
    "Current_PPR",
    "Current_PPG",
    "Current_Baseline_PPG",
    "Current_VORP",

    "Historical_G",
    "Historical_PPR",
    "Historical_PPG",
    "Historical_Baseline_PPG",
    "Historical_VORP"
]


final_output = ranked_df[
    [
        column
        for column in output_cols
        if column in ranked_df.columns
    ]
].copy()


# ============================================================
# DISPLAY COLUMN NAMES
# ============================================================

final_output = final_output.rename(
    columns={

        "Draft_Rank":
            "Rank",

        "Current_G":
            "2025 GP",

        "Current_PPR":
            "2025 PPR",

        "Current_PPG":
            "2025 PPG",

        "Current_Baseline_PPG":
            "2025 Replacement PPG",

        "Current_VORP":
            "2025 VORP",

        "Historical_G":
            "3-Year GP",

        "Historical_PPR":
            "3-Year PPR",

        "Historical_PPG":
            "3-Year PPG",

        "Historical_Baseline_PPG":
            "3-Year Replacement PPG",

        "Historical_VORP":
            "3-Year VORP"
    }
)


# ============================================================
# HTML TABLE
# ============================================================

html_table = final_output.to_html(
    index=False,
    classes="table",
    table_id="draftTable",
    na_rep="",
    justify="left"
)


# ============================================================
# HTML
# ============================================================

html_content = f"""
<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<title>
Fantasy Football VORP Draft Board
</title>


<style>

/* ========================================================
   PAGE
   ======================================================== */

* {{
    box-sizing: border-box;
}}


body {{

    margin: 0;

    padding: 20px;

    background-color: #121212;

    color: #e0e0e0;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

}}


.container {{

    width: 100%;

}}


/* ========================================================
   TITLE
   ======================================================== */

h2 {{

    margin-top: 0;

    margin-bottom: 10px;

    color: #ffffff;

    font-size: 26px;

}}


.description {{

    color: #999999;

    line-height: 1.6;

    margin-bottom: 20px;

}}


.description strong {{

    color: #dddddd;

}}


/* ========================================================
   CONTROL PANEL
   ======================================================== */

.controls {{

    background-color: #1e1e1e;

    border: 1px solid #333333;

    padding: 15px 20px;

    margin-bottom: 20px;

    border-radius: 8px;

    box-shadow:
        0 2px 8px
        rgba(0, 0, 0, 0.4);

}}


.controls strong {{

    color: #ffffff;

    margin-right: 15px;

}}


.position-check {{

    margin-right: 20px;

    color: #dddddd;

    cursor: pointer;

}}


.position-check input {{

    margin-right: 5px;

    cursor: pointer;

}}


.control-button {{

    margin-left: 5px;

    padding: 6px 13px;

    border-radius: 4px;

    border: 1px solid #555555;

    cursor: pointer;

    color: #ffffff;

    font-size: 13px;

}}


.all-button {{

    background-color: #2563eb;

}}


.all-button:hover {{

    background-color: #1d4ed8;

}}


.none-button {{

    background-color: #444444;

}}


.none-button:hover {{

    background-color: #555555;

}}


/* ========================================================
   TABLE
   ======================================================== */

#draftTable {{

    width: 100%;

    border-collapse: collapse;

    background-color: #1b1b1b;

    color: #dddddd;

    border: 1px solid #333333;

    font-size: 13px;

}}


#draftTable thead th {{

    background-color: #252525;

    color: #ffffff;

    border: 1px solid #444444;

    padding: 10px 8px;

    white-space: nowrap;

    cursor: pointer;

    user-select: none;

    position: sticky;

    top: 0;

    z-index: 10;

}}


#draftTable thead th:hover {{

    background-color: #333333;

}}


#draftTable tbody td {{

    border: 1px solid #333333;

    padding: 8px;

    white-space: nowrap;

}}


#draftTable tbody tr {{

    background-color: #1b1b1b;

    transition:
        background-color 0.15s ease,
        color 0.15s ease;

}}


#draftTable tbody tr:hover {{

    background-color: #292929;

}}


/* ========================================================
   DRAFTED PLAYER
   ======================================================== */

#draftTable tbody tr.player-drafted {{

    background-color: #111111 !important;

    color: #666666 !important;

}}


#draftTable tbody tr.player-drafted td {{

    color: #666666 !important;

    text-decoration: line-through;

}}


#draftTable tbody tr.player-drafted:hover {{

    background-color: #111111 !important;

}}


/* ========================================================
   PLAYER NAME
   ======================================================== */

.player-name {{

    cursor: pointer;

    font-weight: bold;

}}


.player-name:hover {{

    color: #ffffff;

}}


/* ========================================================
   SORT ARROW
   ======================================================== */

.sort-arrow {{

    font-size: 10px;

    margin-left: 6px;

    color: #aaaaaa;

}}


/* ========================================================
   CHECKBOXES
   ======================================================== */

input[type="checkbox"] {{

    accent-color: #4f8cff;

}}


/* ========================================================
   POSITION RANK HEADER
   ======================================================== */

#rankHeader {{

    transition:
        color 0.15s ease;

}}


</style>

</head>


<body>


<div class="container">


<h2>
<img src=https://yahoofantasysports-res.cloudinary.com/image/upload/fantasy-logos/459c44b979bfd5347cd412a791fef468fb796aa80a89c53d38ef6ae975e8dfe1.png
width=100 height=100>
National Booty Hunting League VORP Draft Board
</h2>


<p class="description">

PPR scoring |
12 teams |
1 QB |
2 RB |
2 WR |
1 TE |
1 FLEX

<br>

<strong>Current VORP:</strong>
2025 season

&nbsp;&nbsp;|&nbsp;&nbsp;

<strong>Historical VORP:</strong>
Combined 2025 + 2024 + 2023

<br>

VORP =
Player PPG - Replacement Player PPG

<br>

Historical PPG =
Total PPR over three seasons /
Total games over three seasons

</p>


<!-- ======================================================
     POSITION FILTERS
     ====================================================== -->

<div class="controls">

<strong>Position:</strong>


<label class="position-check">

<input
    type="checkbox"
    class="position-filter"
    value="QB"
    checked
>

QB

</label>


<label class="position-check">

<input
    type="checkbox"
    class="position-filter"
    value="RB"
    checked
>

RB

</label>


<label class="position-check">

<input
    type="checkbox"
    class="position-filter"
    value="WR"
    checked
>

WR

</label>


<label class="position-check">

<input
    type="checkbox"
    class="position-filter"
    value="TE"
    checked
>

TE

</label>


<button
    class="control-button all-button"
    onclick="selectAllPositions()"
>

All

</button>


<button
    class="control-button none-button"
    onclick="clearPositions()"
>

None

</button>

</div>


<!-- ======================================================
     TABLE
     ====================================================== -->

{html_table}


</div>


<script>


// ========================================================
// POSITION FILTERING
// ========================================================

function filterTable() {{

    const checkboxes =
        document.querySelectorAll(
            ".position-filter"
        );


    const selectedPositions = [];


    checkboxes.forEach(
        function(checkbox) {{

            if (checkbox.checked) {{

                selectedPositions.push(
                    checkbox.value
                );

            }}

        }}
    );


    const rows =
        document.querySelectorAll(
            "#draftTable tbody tr"
        );


    // ====================================================
    // DETERMINE RANKING MODE
    // ====================================================

    const singlePosition =
        selectedPositions.length === 1
            ? selectedPositions[0]
            : null;


    let positionRank = 0;

    let overallRank = 0;


    // ====================================================
    // FILTER ROWS
    // ====================================================

    rows.forEach(
        function(row) {{

            const position =
                row.children[2]
                    .textContent
                    .trim();


            if (
                selectedPositions.includes(
                    position
                )
            ) {{

                row.style.display = "";

                // ----------------------------------------
                // Single position selected
                // ----------------------------------------

                if (singlePosition) {{

                    positionRank++;

                    row.children[0]
                        .textContent =
                        singlePosition +
                        positionRank;

                }}

            }}
            else {{

                row.style.display = "none";

            }}

        }}
    );


    // ====================================================
    // MULTIPLE POSITIONS
    // ====================================================

    if (!singlePosition) {{

        rows.forEach(
            function(row) {{

                if (
                    row.style.display !==
                    "none"
                ) {{

                    overallRank++;

                    row.children[0]
                        .textContent =
                        overallRank;

                }}

            }}
        );

    }}


    // ====================================================
    // UPDATE RANK HEADER
    // ====================================================

    const rankHeader =
        document.getElementById(
            "rankHeader"
        );


    if (singlePosition) {{

        rankHeader.textContent =
            singlePosition +
            " Rank";

    }}
    else {{

        rankHeader.textContent =
            "Overall Rank";

    }}

}}


// ========================================================
// SELECT ALL
// ========================================================

function selectAllPositions() {{

    document
        .querySelectorAll(
            ".position-filter"
        )
        .forEach(
            function(checkbox) {{

                checkbox.checked = true;

            }}
        );


    filterTable();

}}


// ========================================================
// SELECT NONE
// ========================================================

function clearPositions() {{

    document
        .querySelectorAll(
            ".position-filter"
        )
        .forEach(
            function(checkbox) {{

                checkbox.checked = false;

            }}
        );


    filterTable();

}}


// ========================================================
// POSITION CHECKBOX EVENTS
// ========================================================

document
    .querySelectorAll(
        ".position-filter"
    )
    .forEach(
        function(checkbox) {{

            checkbox.addEventListener(
                "change",
                filterTable
            );

        }}
    );


// ========================================================
// PLAYER CLICK / DRAFT PLAYER
// ========================================================
//
// Clicking the player's name toggles the entire row.
//
// Drafted:
//   - Dark gray
//   - Gray text
//   - Strikethrough
//
// Clicking again restores the player.
//
// ========================================================

document
    .querySelectorAll(
        "#draftTable tbody tr"
    )
    .forEach(
        function(row) {{

            const playerCell =
                row.children[1];


            playerCell.classList.add(
                "player-name"
            );


            playerCell.addEventListener(
                "click",
                function() {{

                    row.classList.toggle(
                        "player-drafted"
                    );

                }}
            );

        }}
    );


// ========================================================
// SORT TABLE
// ========================================================

document
    .querySelectorAll(
        "#draftTable thead th"
    )
    .forEach(
        function(header, columnIndex) {{

            header.addEventListener(
                "click",
                function() {{

                    sortTable(
                        columnIndex,
                        header
                    );

                }}
            );

        }}
    );


function sortTable(
    columnIndex,
    header
) {{

    const table =
        document.getElementById(
            "draftTable"
        );


    const tbody =
        table.querySelector(
            "tbody"
        );


    const rows =
        Array.from(
            tbody.querySelectorAll(
                "tr"
            )
        );


    // ====================================================
    // DETERMINE SORT DIRECTION
    // ====================================================

    const currentDirection =
        header.getAttribute(
            "data-sort-direction"
        );


    const ascending =
        currentDirection !== "asc";


    // ====================================================
    // CLEAR OLD SORT ARROWS
    // ====================================================

    document
        .querySelectorAll(
            "#draftTable thead th"
        )
        .forEach(
            function(th) {{

                th.removeAttribute(
                    "data-sort-direction"
                );


                const oldArrow =
                    th.querySelector(
                        ".sort-arrow"
                    );


                if (oldArrow) {{

                    oldArrow.remove();

                }}

            }}
        );


    // ====================================================
    // SET NEW SORT DIRECTION
    // ====================================================

    header.setAttribute(
        "data-sort-direction",
        ascending
            ? "asc"
            : "desc"
    );


    // ====================================================
    // ADD SORT ARROW
    // ====================================================

    const arrow =
        document.createElement(
            "span"
        );


    arrow.className =
        "sort-arrow";


    arrow.textContent =
        ascending
            ? "▲"
            : "▼";


    header.appendChild(
        arrow
    );


    // ====================================================
    // SORT
    // ====================================================

    rows.sort(
        function(a, b) {{

            let aValue =
                a.children[columnIndex]
                    .textContent
                    .trim();


            let bValue =
                b.children[columnIndex]
                    .textContent
                    .trim();


            // Remove commas
            aValue =
                aValue.replace(
                    /,/g,
                    ""
                );


            bValue =
                bValue.replace(
                    /,/g,
                    ""
                );


            // --------------------------------------------
            // Numeric comparison
            // --------------------------------------------

            const aNumber =
                parseFloat(aValue);


            const bNumber =
                parseFloat(bValue);


            if (
                !isNaN(aNumber) &&
                !isNaN(bNumber)
            ) {{

                return ascending
                    ? aNumber - bNumber
                    : bNumber - aNumber;

            }}


            // --------------------------------------------
            // Text comparison
            // --------------------------------------------

            return ascending
                ? aValue.localeCompare(
                    bValue
                )
                : bValue.localeCompare(
                    aValue
                );

        }}
    );


    // ====================================================
    // REINSERT ROWS
    // ====================================================

    rows.forEach(
        function(row) {{

            tbody.appendChild(
                row
            );

        }}
    );


    // ====================================================
    // RE-CALCULATE DISPLAYED RANK
    // ====================================================

    filterTable();

}}


// ========================================================
// INITIALIZE
// ========================================================

filterTable();


</script>


</body>

</html>
"""


# ============================================================
# WRITE HTML FILE
# ============================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    f.write(
        html_content
    )

print(
    f"Success! Draft rankings "
    f"exported to "
    f"'{OUTPUT_FILE}'."
)


