from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Catalogue de nouveautés",
    page_icon="📚",
    layout="wide",
)


FIELD_SUGGESTIONS = {
    "ISBN": ["isbn", "ean", "isbn13", "isbn_13"],
    "Titre": ["titre_pr", "titre", "title"],
    "Nom de l'auteur": ["nom_aut1", "nom_auteur", "auteur", "author"],
    "Prénom de l'auteur": ["pnom_au1", "prenom_auteur", "prenom"],
    "Année": ["annee_ed", "annee", "year"],
    "Genre": ["genre", "categorie", "category"],
    "Cote": ["cote", "call_number"],
}


def excel_engine(filename: str) -> str:
    """Return the pandas engine matching the uploaded Excel format."""
    return "xlrd" if filename.lower().endswith(".xls") else "openpyxl"


def suggested_index(columns: list[str], suggestions: list[str], optional: bool) -> int:
    """Find the best default index for a column mapping select box."""
    normalized = {str(column).strip().lower(): i for i, column in enumerate(columns)}
    for suggestion in suggestions:
        if suggestion.lower() in normalized:
            return normalized[suggestion.lower()] + (1 if optional else 0)
    return 0


def column_selector(
    label: str,
    columns: list[str],
    suggestions: list[str],
    *,
    optional: bool = False,
) -> str | None:
    """Display a mapping selector and return the chosen source column."""
    options = ["— Ne pas utiliser —", *columns] if optional else columns
    index = suggested_index(columns, suggestions, optional)
    selection = st.selectbox(label, options=options, index=index)
    return None if selection == "— Ne pas utiliser —" else selection


def clean_text(series: pd.Series) -> pd.Series:
    """Normalize Excel text values without converting identifiers to numbers."""
    return (
        series.astype("string")
        .str.strip()
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    )


st.title("📚 Créateur de catalogue de nouveautés")
st.caption("Étape 1 : importer le fichier et choisir les données bibliographiques")

with st.expander("Confidentialité des données", expanded=False):
    st.write(
        "L'application ne doit conserver que les colonnes bibliographiques utiles. "
        "Ne sélectionnez jamais une colonne contenant le nom d'un emprunteur ou "
        "une autre donnée personnelle. Dans cette première version, le fichier "
        "est uniquement traité en mémoire pendant la session."
    )

uploaded_file = st.file_uploader(
    "Déposer le fichier Excel",
    type=["xls", "xlsx"],
    accept_multiple_files=False,
    help="Formats acceptés : anciens fichiers .xls et fichiers .xlsx.",
)

if uploaded_file is None:
    st.info("Dépose un fichier Excel pour commencer.")
    st.stop()

try:
    raw_excel = uploaded_file.getvalue()
    engine = excel_engine(uploaded_file.name)
    workbook = pd.ExcelFile(BytesIO(raw_excel), engine=engine)
except Exception as exc:
    st.error(f"Impossible d'ouvrir le classeur : {exc}")
    st.stop()

sheet_name = st.selectbox("Feuille à utiliser", options=workbook.sheet_names)

try:
    source = pd.read_excel(
        BytesIO(raw_excel),
        sheet_name=sheet_name,
        engine=engine,
        dtype=str,
    )
except Exception as exc:
    st.error(f"Impossible de lire la feuille sélectionnée : {exc}")
    st.stop()

source.columns = [str(column).strip() for column in source.columns]
columns = list(source.columns)

if not columns:
    st.error("La feuille sélectionnée ne contient aucune colonne.")
    st.stop()

metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("Lignes détectées", len(source))
metric_2.metric("Colonnes détectées", len(columns))
metric_3.metric("Feuille", sheet_name)

st.subheader("Associer les colonnes")
st.write(
    "Vérifie les propositions automatiques. Seules les colonnes choisies seront "
    "conservées pour construire le catalogue."
)

left, right = st.columns(2)

with left:
    isbn_column = column_selector(
        "Colonne ISBN *",
        columns,
        FIELD_SUGGESTIONS["ISBN"],
    )
    title_column = column_selector(
        "Colonne titre *",
        columns,
        FIELD_SUGGESTIONS["Titre"],
    )
    author_last_name_column = column_selector(
        "Nom de l'auteur",
        columns,
        FIELD_SUGGESTIONS["Nom de l'auteur"],
        optional=True,
    )
    author_first_name_column = column_selector(
        "Prénom de l'auteur",
        columns,
        FIELD_SUGGESTIONS["Prénom de l'auteur"],
        optional=True,
    )

with right:
    year_column = column_selector(
        "Année d'édition",
        columns,
        FIELD_SUGGESTIONS["Année"],
        optional=True,
    )
    genre_column = column_selector(
        "Genre",
        columns,
        FIELD_SUGGESTIONS["Genre"],
        optional=True,
    )
    shelfmark_column = column_selector(
        "Cote",
        columns,
        FIELD_SUGGESTIONS["Cote"],
        optional=True,
    )

mapping = {
    "isbn": isbn_column,
    "titre": title_column,
    "nom_auteur": author_last_name_column,
    "prenom_auteur": author_first_name_column,
    "annee": year_column,
    "genre": genre_column,
    "cote": shelfmark_column,
}

selected_columns = [column for column in mapping.values() if column is not None]
duplicates = sorted({column for column in selected_columns if selected_columns.count(column) > 1})

if duplicates:
    st.warning(
        "Une même colonne a été associée à plusieurs informations : "
        + ", ".join(duplicates)
    )
    st.stop()

catalogue = pd.DataFrame(index=source.index)
for target_name, source_name in mapping.items():
    if source_name is not None:
        catalogue[target_name] = clean_text(source[source_name])

catalogue["isbn_nettoye"] = (
    catalogue["isbn"]
    .fillna("")
    .str.replace(r"[^0-9Xx]", "", regex=True)
    .replace("", pd.NA)
)
catalogue["isbn_valide"] = catalogue["isbn_nettoye"].str.len().isin([10, 13])

st.subheader("Contrôle avant génération")

valid_isbn_count = int(catalogue["isbn_valide"].sum())
missing_or_invalid_count = int((~catalogue["isbn_valide"]).sum())

control_1, control_2 = st.columns(2)
control_1.metric("ISBN exploitables", valid_isbn_count)
control_2.metric("ISBN absents ou invalides", missing_or_invalid_count)

st.dataframe(catalogue.head(20), use_container_width=True, hide_index=True)

st.success(
    "Le fichier est correctement lu et les colonnes utiles sont isolées. "
    "La prochaine étape ajoutera la récupération des couvertures BnF."
)

