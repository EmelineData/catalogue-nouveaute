from __future__ import annotations

import hashlib
from io import BytesIO
from time import sleep

import pandas as pd
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from pdf_generator import build_catalogue_pdf


BNF_COVER_URL = "https://openapi.bnf.fr/couverture/image/image/recupererImage"


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


def placeholder_cover() -> bytes:
    """Create a neutral cover used when the BnF has no image."""
    image = Image.new("RGB", (600, 900), "#F2EFE9")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (45, 45, 555, 855),
        radius=24,
        outline="#5C6B73",
        width=7,
    )
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 46)
        text_font = ImageFont.truetype("DejaVuSans.ttf", 34)
    except OSError:
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()

    draw.text(
        (300, 355),
        "NOUVEAUTÉ",
        fill="#244B5A",
        font=title_font,
        anchor="mm",
    )
    draw.multiline_text(
        (300, 475),
        "Couverture\nnon disponible",
        fill="#5C6B73",
        font=text_font,
        anchor="mm",
        align="center",
        spacing=14,
    )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@st.cache_data(ttl=86_400, show_spinner=False)
def fetch_bnf_cover(isbn: str) -> tuple[bytes | None, str]:
    """Retrieve a front cover from the BnF API using an ISBN."""
    try:
        response = requests.get(
            BNF_COVER_URL,
            params={
                "ISBN": isbn,
                "couverture": 1,
                "taille": "originale",
                "largeur": 300,
                "hauteur": 450,
            },
            headers={
                "User-Agent": "Catalogue-nouveautes-bibliotheque/1.0"
            },
            timeout=25,
        )
    except requests.RequestException as exc:
        return None, f"Erreur réseau : {exc}"

    content_type = response.headers.get("Content-Type", "").lower()
    if response.status_code == 200 and content_type.startswith("image/"):
        try:
            Image.open(BytesIO(response.content)).verify()
        except Exception:
            return None, "Réponse reçue, mais image illisible"
        return response.content, "Couverture trouvée"

    # La BnF indique qu'une réponse 500 signifie actuellement le plus souvent
    # que la notice ne contient pas de couverture.
    if response.status_code == 500:
        return None, "Couverture non disponible à la BnF"

    return None, f"Réponse BnF inattendue ({response.status_code})"


st.title("📚 Créateur de catalogue de nouveautés de la médiathèque")
st.caption("Étape 1 : importer le fichier (excel) et choisir les données bibliographiques correspondantes")

with st.expander("Confidentialité des données", expanded=False):
    st.write(
        "ATTENTION ! Veuillez fournir un fichier ne contenant que les colonnes bibliographiques utiles. "
        "Ne sélectionnez jamais une colonne contenant le nom d'un emprunteur ou "
        "une autre donnée personnelle. Sachez que le fichier fournit "
        "est uniquement traité en mémoire pendant la session et n'est pas enregistré."
    )

uploaded_file = st.file_uploader(
    "Déposer le fichier Excel",
    type=["xls", "xlsx"],
    accept_multiple_files=False,
    help="Formats acceptés : anciens fichiers .xls et fichiers .xlsx.",
)

if uploaded_file is None:
    st.info("Pour commencer, déposez un fichier Excel svp")
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
    "Vérifiez les propositions automatiques. Seules les colonnes choisies seront "
    "conservées pour construire le catalogue des nouveautés"
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
        "Attention, une même colonne a été associée à plusieurs informations : "
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
    "Vous pouvez maintenant rechercher les couvertures via l'API de la BnF."
)

st.divider()
st.subheader("Lancer la rechercher des couvertures via la BnF")
st.write(
    "Remarque : seuls les ISBN sont envoyés au service Couvertures de la Bibliothèque "
    "nationale de France. Le fichier Excel complet n'est pas transmis."
)

dataset_key = hashlib.sha256(
    raw_excel + sheet_name.encode("utf-8") + isbn_column.encode("utf-8")
).hexdigest()

if st.session_state.get("cover_dataset_key") != dataset_key:
    st.session_state.pop("cover_results", None)
    st.session_state.pop("generated_pdf", None)
    st.session_state["cover_dataset_key"] = dataset_key

if st.button(
    "🔎 Rechercher les couvertures",
    type="primary",
    disabled=valid_isbn_count == 0,
):
    valid_rows = catalogue.loc[
        catalogue["isbn_valide"], ["isbn", "isbn_nettoye"]
    ].drop_duplicates(subset="isbn_nettoye")

    results: dict[str, dict[str, bytes | str | None]] = {}
    progress = st.progress(0, text="Préparation de la recherche...")
    total = len(valid_rows)

    for position, row in enumerate(valid_rows.itertuples(index=False), start=1):
        progress.progress(
            position / total,
            text=f"Recherche {position}/{total} — ISBN {row.isbn_nettoye}",
        )
        image_bytes, status = fetch_bnf_cover(str(row.isbn))
        results[str(row.isbn_nettoye)] = {
            "image": image_bytes,
            "statut": status,
        }
        sleep(0.15)

    progress.empty()
    st.session_state["cover_results"] = results

cover_results = st.session_state.get("cover_results")

if cover_results:
    catalogue["statut_couverture"] = catalogue["isbn_nettoye"].map(
        lambda isbn: (
            cover_results.get(str(isbn), {}).get("statut")
            if pd.notna(isbn)
            else "ISBN absent ou invalide"
        )
    )

    found_count = sum(
        result["image"] is not None for result in cover_results.values()
    )
    not_found_count = len(cover_results) - found_count

    cover_1, cover_2, cover_3 = st.columns(3)
    cover_1.metric("Couvertures trouvées", found_count)
    cover_2.metric("Non disponibles", not_found_count)
    cover_3.metric("ISBN non exploitables", missing_or_invalid_count)

    with st.expander("Voir le détail des résultats", expanded=False):
        st.dataframe(
            catalogue[
                ["titre", "isbn", "isbn_nettoye", "statut_couverture"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Aperçu des couvertures")
    preview_columns = st.columns(4)
    fallback = placeholder_cover()

    for preview_position, row in enumerate(
        catalogue.head(12).itertuples(index=False)
    ):
        isbn_clean = getattr(row, "isbn_nettoye", None)
        result = (
            cover_results.get(str(isbn_clean), {})
            if pd.notna(isbn_clean)
            else {}
        )
        image = result.get("image") or fallback
        with preview_columns[preview_position % 4]:
            st.image(image, use_container_width=True)
            st.markdown(f"**{getattr(row, 'titre', 'Titre non renseigné')}**")
            if hasattr(row, "nom_auteur") and pd.notna(row.nom_auteur):
                author = " ".join(
                    value
                    for value in [
                        getattr(row, "prenom_auteur", None),
                        getattr(row, "nom_auteur", None),
                    ]
                    if pd.notna(value)
                )
                st.caption(author)

    st.info(
        "Les couvertures ont été récupérées. Vous pouvez maintenant paramétrer et "
        "générer le catalogue des nouveautés au format PDF."
    )

    st.divider()
    st.subheader("Créer le catalogue PDF")

    document_title = st.text_input(
        "Titre du catalogue",
        value="Les nouveautés de la bibliothèque",
        max_chars=120,
    )

    settings_left, settings_right = st.columns(2)

    with settings_left:
        books_per_page = st.segmented_control(
            "Nombre d'ouvrages par page",
            options=[2, 4, 6],
            default=4,
            selection_mode="single",
        )

    available_fields: list[str] = []
    if "nom_auteur" in catalogue.columns or "prenom_auteur" in catalogue.columns:
        available_fields.append("Auteur")
    if "annee" in catalogue.columns:
        available_fields.append("Année")
    if "genre" in catalogue.columns:
        available_fields.append("Genre")
    if "cote" in catalogue.columns:
        available_fields.append("Cote")
    available_fields.append("ISBN")

    default_fields = [
        field
        for field in ["Auteur", "Année", "Genre", "Cote"]
        if field in available_fields
    ]

    with settings_right:
        selected_fields = st.multiselect(
            "Informations à afficher sous le titre",
            options=available_fields,
            default=default_fields,
        )

    with st.expander("🎨 Personnaliser la mise en page", expanded=False):
        style_left, style_middle, style_right = st.columns(3)

        with style_left:
            header_color = st.color_picker(
                "Couleur du bandeau",
                value="#244B5A",
            )
            header_text_color = st.color_picker(
                "Couleur du titre",
                value="#FFFFFF",
            )

        with style_middle:
            font_family = st.selectbox(
                "Police du PDF",
                options=["Helvetica", "Times", "Courier"],
                index=0,
            )
            header_font_size = st.slider(
                "Taille du titre du catalogue",
                min_value=12,
                max_value=22,
                value=16,
            )

        with style_right:
            body_font_size = st.slider(
                "Taille du texte des notices",
                min_value=7.0,
                max_value=11.0,
                value=8.8,
                step=0.2,
            )
            show_card_borders = st.checkbox(
                "Afficher les bordures",
                value=True,
            )

    estimated_pages = (
        (len(catalogue) + books_per_page - 1) // books_per_page
        if books_per_page
        else 0
    )
    st.caption(
        f"Le catalogue contiendra environ {estimated_pages} page(s) pour "
        f"{len(catalogue)} ouvrage(s). Le titre du livre est toujours affiché."
    )

    pdf_configuration = {
        "dataset": dataset_key,
        "title": document_title,
        "books_per_page": books_per_page,
        "fields": selected_fields,
        "header_color": header_color,
        "header_text_color": header_text_color,
        "font_family": font_family,
        "header_font_size": header_font_size,
        "body_font_size": body_font_size,
        "show_card_borders": show_card_borders,
    }

    if st.button(
        "📄 Générer le catalogue PDF",
        type="primary",
        disabled=not document_title.strip() or books_per_page is None,
    ):
        with st.spinner("Génération du catalogue en cours..."):
            try:
                pdf_bytes = build_catalogue_pdf(
                    catalogue=catalogue,
                    cover_results=cover_results,
                    fallback_cover=fallback,
                    document_title=document_title.strip(),
                    books_per_page=int(books_per_page),
                    selected_fields=selected_fields,
                    header_color=header_color,
                    header_text_color=header_text_color,
                    font_family=font_family,
                    header_font_size=header_font_size,
                    body_font_size=body_font_size,
                    show_card_borders=show_card_borders,
                )
            except Exception as exc:
                st.error(f"Impossible de générer le PDF : {exc}")
            else:
                st.session_state["generated_pdf"] = {
                    "bytes": pdf_bytes,
                    "configuration": pdf_configuration,
                }
                st.success("Le catalogue PDF est prêt.")

    generated_pdf = st.session_state.get("generated_pdf")
    if generated_pdf:
        if generated_pdf["configuration"] == pdf_configuration:
            st.download_button(
                "⬇️ Télécharger le catalogue PDF",
                data=generated_pdf["bytes"],
                file_name="catalogue_nouveautes.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
        else:
            st.warning(
                "Les paramètres ont changé depuis la dernière génération. "
                "Clique à nouveau sur « Générer le catalogue PDF »."
            )