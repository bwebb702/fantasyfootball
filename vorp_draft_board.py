#claude 20260831
import re
import pandas as pd

FILE_2025 = r"C:\Brian\Python Projects\FantasyFootball\data\sportsref_2025.csv"
FILE_2024 = r"C:\Brian\Python Projects\FantasyFootball\data\sportsref_2024.csv"
FILE_2023 = r"C:\Brian\Python Projects\FantasyFootball\data\sportsref_2023.csv"
ADP_FILE = r"C:\Brian\Python Projects\FantasyFootball\data\adp.csv"
OUTPUT_FILE = "fantasy_draft_rankings.html"

# ============================================================
# LEAGUE SETTINGS
# ============================================================
#
# 12-team league: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX
# Baseline methodology: QB13, RB25, WR25, TE13 (FLEX not separately
# allocated). VORP = Player PPG - Replacement Player PPG.
#
BASELINES = {"QB": 13, "RB": 25, "WR": 25, "TE": 13}

# Minimum games played to be eligible to SET the replacement-level PPG.
# Without this, a player with 1-2 games and a fluke big game can sort
# to the top of the PPG-descending list and get picked as the
# "replacement" player, dragging every other player's VORP with it.
# Low-game players still appear in the final table with their real
# stats -- this floor only affects who is used to determine the
# baseline rank.
MIN_GAMES_FOR_BASELINE = 8

# Final table size, keeping the highest 2025 VORP players.
MAX_PLAYERS = 300

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


# ============================================================
# NAME NORMALIZATION (for matching across files)
# ============================================================
#
# "Kenneth Walker III" / "Kenneth Walker" and "Odell Beckham Jr." /
# "Odell Beckham" should be treated as the same player. This strips
# punctuation and generational suffixes to build a matching key.
# The original display name is kept separately -- this key is only
# used to join rows.
#
def normalize_name(name):
    name = re.sub(r"[.'`]", "", str(name).lower())
    name = re.sub(r"-", " ", name)
    tokens = [t for t in name.split() if t not in SUFFIXES]
    return " ".join(tokens)


# ============================================================
# LOAD AND CLEAN CSV
# ============================================================
def process_csv(file_path):
    df = pd.read_csv(file_path)

    if "FantPos" in df.columns and "Pos" not in df.columns:
        df = df.rename(columns={"FantPos": "Pos"})

    required = ["Player", "Pos", "PPR", "G"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{file_path} is missing required columns: {missing}")

    df = df.dropna(subset=required).copy()
    df["Player"] = df["Player"].astype(str).str.rstrip("+").str.rstrip("*").str.strip()
    df["Pos"] = df["Pos"].astype(str).str.upper().str.strip()
    df["PPR"] = pd.to_numeric(df["PPR"], errors="coerce")
    df["G"] = pd.to_numeric(df["G"], errors="coerce")

    df = df.dropna(subset=["PPR", "G"])
    df = df[df["G"] > 0].copy()
    df = df[df["Pos"].isin(["QB", "RB", "WR", "TE"])].copy()

    df["PPG"] = df["PPR"] / df["G"]
    df["Name_Key"] = df["Player"].apply(normalize_name)

    return df


# ============================================================
# LOAD AND CLEAN ADP CSV
# ============================================================
#
# This file has 2 title/blank rows before the real header, so
# skiprows=2. Everything is read as string so a pick number like
# "1.10" doesn't get silently turned into 1.1 by float parsing.
#
# Name column looks like "James Cook III BUF (7)" -- team code and
# bye week must be stripped to match the season stat files. Order is
# always [Name] [Suffix?] [TEAM] (bye), so removing the trailing
# "(...)" and then the trailing all-caps token is safe even when a
# generational suffix (II/III/IV) is present, since the suffix sits
# before the team code, not after it.
#
def process_adp(file_path):
    df = pd.read_csv(file_path, skiprows=2, dtype=str)

    required = ["Name", "POS.RK", "PICK NUM."]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{file_path} is missing required columns: {missing}")

    df = df.dropna(subset=required).copy()

    def clean_name(name):
        name = re.sub(r"\s*\([^)]*\)\s*$", "", str(name)).strip()
        name = re.sub(r"\s+[A-Z]{2,4}$", "", name).strip()
        return name

    df["Player"] = df["Name"].apply(clean_name)
    df["Name_Key"] = df["Player"].apply(normalize_name)

    # POS.RK combines position + position rank, e.g. "RB12". Pos is
    # just the leading letters, used to join against the stat files.
    df["Pos_Display"] = df["POS.RK"].str.strip()
    df["Pos"] = df["Pos_Display"].str.extract(r"^([A-Z]+)")[0]

    df["ADP"] = df["PICK NUM."].str.strip()
    df["ADP_Sort"] = pd.to_numeric(df["ADP"], errors="coerce")

    df = df.dropna(subset=["ADP_Sort"])
    df = df[df["Pos"].isin(["QB", "RB", "WR", "TE"])].copy()

    # Keep the best (lowest) ADP if a player appears more than once.
    df = df.sort_values("ADP_Sort").drop_duplicates(subset=["Name_Key", "Pos"], keep="first")

    return df[["Name_Key", "Player", "Pos", "Pos_Display", "ADP", "ADP_Sort"]].reset_index(drop=True)


# ============================================================
# FIND REPLACEMENT LEVEL AND CALCULATE VORP
# ============================================================
def find_baseline(df, baselines, prefix=""):
    vorp_dfs = []

    for pos, baseline_rank in baselines.items():
        pos_df = df[df["Pos"] == pos].sort_values("PPG", ascending=False).reset_index(drop=True)
        if pos_df.empty:
            continue

        # Only players meeting MIN_GAMES_FOR_BASELINE are eligible to BE
        # the replacement player, so a small-sample fluke can't distort
        # the baseline. Fall back to the full pool if nobody qualifies.
        qualified = pos_df[pos_df["G"] >= MIN_GAMES_FOR_BASELINE].reset_index(drop=True)
        if qualified.empty:
            qualified = pos_df

        if len(qualified) >= baseline_rank:
            replacement_ppg = qualified.iloc[baseline_rank - 1]["PPG"]
        else:
            replacement_ppg = qualified.iloc[-1]["PPG"]

        pos_df[f"{prefix}Baseline_PPG"] = round(replacement_ppg, 2)
        pos_df[f"{prefix}VORP"] = (pos_df["PPG"] - replacement_ppg).round(2)
        pos_df[f"{prefix}PPG"] = pos_df["PPG"].round(2)

        vorp_dfs.append(pos_df)

    return pd.concat(vorp_dfs, ignore_index=True) if vorp_dfs else pd.DataFrame()


def coalesce_player_columns(df):
    """After a merge, prefer Player_x (left side) and fall back to
    Player_y (right side) so we always keep a real display name."""
    df["Player"] = df["Player_x"].fillna(df["Player_y"])
    return df.drop(columns=["Player_x", "Player_y"])


# ============================================================
# LOAD DATA
# ============================================================
df_2025 = process_csv(FILE_2025)
df_2024 = process_csv(FILE_2024)
df_2023 = process_csv(FILE_2023)
adp_df = process_adp(ADP_FILE)

# ============================================================
# CURRENT SEASON VORP
# ============================================================
current_vorp = find_baseline(df_2025, BASELINES, prefix="Current_")

current_output = current_vorp[
    ["Name_Key", "Player", "Pos", "G", "PPR", "Current_PPG", "Current_Baseline_PPG", "Current_VORP"]
].rename(columns={"G": "Current_G", "PPR": "Current_PPR"})

# ============================================================
# COMBINE THREE SEASONS
# ============================================================
#
# Total PPR and total games are summed across the three seasons, so
# Historical PPG = (PPR25+PPR24+PPR23) / (G25+G24+G23), using actual
# games played.
#
df_hist = pd.concat([df_2025, df_2024, df_2023], ignore_index=True)
df_hist = df_hist.groupby(["Name_Key", "Player", "Pos"], as_index=False).agg(G=("G", "sum"), PPR=("PPR", "sum"))
df_hist["PPG"] = df_hist["PPR"] / df_hist["G"]

historical_vorp = find_baseline(df_hist, BASELINES, prefix="Historical_")

historical_output = historical_vorp[
    ["Name_Key", "Pos", "G", "PPR", "Historical_PPG", "Historical_Baseline_PPG", "Historical_VORP"]
].rename(columns={"G": "Historical_G", "PPR": "Historical_PPR"})

# ============================================================
# MERGE CURRENT + HISTORICAL + ADP
# ============================================================
#
# Matching key is Name_Key + Pos (handles Jr./Sr./II-V suffix
# mismatches between files). indicator=True on the ADP merge tells us
# which rows only exist in the ADP file (i.e. rookies with no stats).
#
ranked_df = pd.merge(current_output, historical_output, on=["Name_Key", "Pos"], how="outer")

ranked_df = pd.merge(ranked_df, adp_df, on=["Name_Key", "Pos"], how="outer", indicator=True)
ranked_df = coalesce_player_columns(ranked_df)
ranked_df["Is_New_Player"] = ranked_df["_merge"] == "right_only"
ranked_df = ranked_df.drop(columns=["_merge"])

# ============================================================
# DROP PLAYERS WITH NO 2025 DATA, UNLESS THEY'RE IN THE ADP FILE
# ============================================================
ranked_df = ranked_df[ranked_df["Current_G"].notna() | ranked_df["Is_New_Player"]].reset_index(drop=True)

# ============================================================
# POSITION DISPLAY (e.g. "RB1") VS. POSITION KEY (e.g. "RB")
# ============================================================
#
# The table should show combined position + position rank from the
# ADP file's POS.RK column. Pos_Key is kept separately (not shown)
# since the JS position-filter checkboxes still need to match on the
# plain "RB"/"WR"/"QB"/"TE" code, not "RB1".
#
ranked_df["Pos_Key"] = ranked_df["Pos"]
ranked_df["Pos"] = ranked_df["Pos_Display"].fillna(ranked_df["Pos_Key"])

# ============================================================
# NUMERIC COLUMNS
# ============================================================
numeric_columns = [
    "ADP_Sort", "Current_G", "Current_PPR", "Current_PPG", "Current_Baseline_PPG", "Current_VORP",
    "Historical_G", "Historical_PPR", "Historical_PPG", "Historical_Baseline_PPG", "Historical_VORP",
]
for column in numeric_columns:
    if column in ranked_df.columns:
        ranked_df[column] = pd.to_numeric(ranked_df[column], errors="coerce").round(2)

# ============================================================
# CAP AT MAX_PLAYERS BY 2025 VORP, THEN SORT FOR DISPLAY BY ADP
# ============================================================
#
# Players with no Current_VORP (ADP-only rookies) have nothing to rank
# by, so they're kept separately and appended rather than competing
# for the VORP-based cutoff.
#
has_vorp = ranked_df[ranked_df["Current_VORP"].notna()].sort_values("Current_VORP", ascending=False)
rookies_only = ranked_df[ranked_df["Current_VORP"].isna()]

ranked_df = pd.concat([has_vorp.head(MAX_PLAYERS), rookies_only], ignore_index=True)
ranked_df = ranked_df.sort_values("ADP_Sort", ascending=True, na_position="last").reset_index(drop=True)
ranked_df["Draft_Rank"] = ranked_df.index + 1

# ============================================================
# OUTPUT COLUMNS
# ============================================================
output_cols = [
    "Draft_Rank", "Player", "Pos", "ADP",
    "Current_G", "Current_PPR", "Current_PPG", "Current_Baseline_PPG", "Current_VORP",
    "Historical_G", "Historical_PPG", "Historical_Baseline_PPG", "Historical_VORP",
]

# Is_New_Player and Pos_Key ride along so the HTML step can color rookie
# rows and filter by plain position, then both get dropped before the
# table is rendered (neither is a display column).
final_output = ranked_df[
    [c for c in output_cols if c in ranked_df.columns] + ["Is_New_Player", "Pos_Key"]
].copy()

final_output = final_output.rename(columns={
    "Draft_Rank": "Rank",
    "Current_G": "2025 GP", "Current_PPR": "2025 PPR", "Current_PPG": "2025 PPG",
    "Current_Baseline_PPG": "2025 Replacement PPG", "Current_VORP": "2025 VORP",
    "Historical_G": "3-Year GP", "Historical_PPG": "3-Year PPG",
    "Historical_Baseline_PPG": "3-Year Replacement PPG", "Historical_VORP": "3-Year VORP",
})

# ============================================================
# HTML TABLE
# ============================================================
is_new_flags = final_output["Is_New_Player"].fillna(False).tolist()
pos_keys = final_output["Pos_Key"].fillna("").tolist()
final_output = final_output.drop(columns=["Is_New_Player", "Pos_Key"])

html_table = final_output.to_html(index=False, classes="table", table_id="draftTable", na_rep="", justify="left")

# ============================================================
# HIGHLIGHT NEW (ADP-ONLY) PLAYERS IN FIREBRICK RED, TAG POSITION
# ============================================================
#
# Firebrick: players present in the ADP file with no matching current
# or historical stats (e.g. rookies).
#
# data-pos: the plain position code (e.g. "RB"), used by the JS
# position-filter checkboxes since the visible Pos column now shows
# the combined "RB1"-style value from POS.RK instead.
#
# Everything else about the table's CSS/JS is untouched -- this only
# adds attributes to the specific <tr> elements.
#
table_head, tbody_rest = html_table.split("<tbody>", 1)
tbody_content, table_tail = tbody_rest.split("</tbody>", 1)
row_chunks = re.findall(r"<tr>.*?</tr>", tbody_content, flags=re.S)

if len(row_chunks) == len(is_new_flags) == len(pos_keys):
    styled_rows = []
    for chunk, is_new, pos_key in zip(row_chunks, is_new_flags, pos_keys):
        attrs = f'data-pos="{pos_key}"'
        if is_new:
            attrs += ' style="color: firebrick;"'
        styled_rows.append(chunk.replace("<tr>", f"<tr {attrs}>", 1))
    html_table = table_head + "<tbody>" + "".join(styled_rows) + "</tbody>" + table_tail

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
   PICKED RANK (click the rank number)
   ======================================================== */

#draftTable tbody tr.rank-picked {{

    background-color: #0f3d1f !important;

    color: #8fffa8 !important;

}}


#draftTable tbody tr.rank-picked td {{

    color: #8fffa8 !important;

}}


#draftTable tbody tr.rank-picked:hover {{

    background-color: #0f3d1f !important;

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


.rank-number {{

    cursor: pointer;

    font-weight: bold;

}}


.rank-number:hover {{

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
                row.dataset.pos;


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
// ROW CLICK ACTIONS
// ========================================================
//
// Clicking the player's name toggles the entire row.
//
// Drafted:
//   - Dark gray
//   - Gray text
//   - Strikethrough
//
// Clicking the rank number toggles the row green (picked).
//
// Clicking again restores the row.
//
// ========================================================

document
    .querySelectorAll(
        "#draftTable tbody tr"
    )
    .forEach(
        function(row) {{

            const rankCell =
                row.children[0];

            const playerCell =
                row.children[1];


            rankCell.classList.add(
                "rank-number"
            );

            playerCell.classList.add(
                "player-name"
            );


            rankCell.addEventListener(
                "click",
                function() {{

                    row.classList.toggle(
                        "rank-picked"
                    );

                }}
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
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Success! Draft rankings exported to '{OUTPUT_FILE}'.")