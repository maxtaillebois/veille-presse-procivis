"""
Veille Presse Procivis — Application Streamlit
================================================
Interface de consultation et sélection des articles de veille presse.
Lit les données depuis Google Sheets (alimenté par N8N) et permet
d'envoyer un récapitulatif par mail via un webhook N8N.
"""

import json
from datetime import datetime, timedelta

import gspread
import pandas as pd
import requests
import streamlit as st
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SPREADSHEET_ID = st.secrets.get("SPREADSHEET_ID", "")
SHEET_NAME = "Veille Procivis"

N8N_WEBHOOK_URL = st.secrets.get("N8N_WEBHOOK_URL", "")

DEFAULT_DEST_EMAIL = st.secrets.get("DEFAULT_DEST_EMAIL", "")
DEFAULT_DEST_NOM = st.secrets.get("DEFAULT_DEST_NOM", "")

MOTS_CLES = ["Procivis", "Immo de France", "Maisons d'en France", "Yannick Borde"]

# Couleurs de la charte Procivis (sept. 2025)
VERT_PROCIVIS = "#97C33D"      # Pantone 376 — couleur institutionnelle
VERT_FONCE = "#7AA52E"         # Vert assombri pour hover/dégradés
VERT_CLAIR = "#EFF6E0"         # Vert 20% — fonds légers
GRIS_PROCIVIS = "#515459"      # Pantone 432 — texte et logo
GRIS_CLAIR = "#F7F8FA"         # Fond de page
GRIS_TEXTE = "#515459"         # Texte courant
VERT_FLUO = "#B6FF58"          # Couleur additionnelle réseaux sociaux
# Couleurs métiers
ROSE_BAILLEUR = "#FF3E65"
BLEU_PROMOTEUR = "#005CCE"
CYAN_AMENAGEUR = "#61D2D1"
CYAN_CONSTRUCTEUR = "#00ACFF"
JAUNE_SERVICES = "#FFC400"


# ---------------------------------------------------------------------------
# CSS personnalisé
# ---------------------------------------------------------------------------

def inject_css():
    st.markdown(f"""
    <style>
        /* ===== GLOBAL ===== */
        .stApp {{
            background-color: {GRIS_CLAIR};
        }}

        /* ===== HEADER HERO ===== */
        .hero {{
            background: linear-gradient(135deg, {VERT_PROCIVIS} 0%, {VERT_FONCE} 100%);
            color: white;
            padding: 2rem 2.5rem;
            border-radius: 16px;
            margin-bottom: 1.5rem;
            box-shadow: 0 4px 20px rgba(151, 195, 61, 0.3);
        }}
        .hero h1 {{
            margin: 0;
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
        }}
        .hero .hero-sub {{
            margin: 0.5rem 0 0 0;
            font-size: 1rem;
            opacity: 0.9;
            font-weight: 300;
        }}

        /* ===== BARRE DE STATS ===== */
        .stats-bar {{
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        .stat-card {{
            background: white;
            border-radius: 12px;
            padding: 1rem 1.5rem;
            flex: 1;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            border-left: 4px solid {VERT_PROCIVIS};
        }}
        .stat-card .stat-number {{
            font-size: 1.8rem;
            font-weight: 700;
            color: {VERT_PROCIVIS};
            line-height: 1;
        }}
        .stat-card .stat-label {{
            font-size: 0.8rem;
            color: {GRIS_PROCIVIS};
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 4px;
            opacity: 0.7;
        }}

        /* ===== CARTE ARTICLE ===== */
        .article-card {{
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 2px 10px rgba(0,0,0,0.06);
            border-left: 4px solid {VERT_PROCIVIS};
            transition: box-shadow 0.2s ease, transform 0.2s ease;
        }}
        .article-card:hover {{
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            transform: translateY(-1px);
        }}
        .article-card.selected {{
            border-left-color: {GRIS_PROCIVIS};
            background: {VERT_CLAIR};
        }}

        .article-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: {GRIS_PROCIVIS};
            margin-bottom: 6px;
            line-height: 1.3;
        }}
        .article-meta {{
            display: flex;
            align-items: center;
            gap: 16px;
            margin-bottom: 10px;
            flex-wrap: wrap;
        }}
        .meta-item {{
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 0.85rem;
            color: #888;
        }}
        .article-resume {{
            font-size: 0.93rem;
            color: {GRIS_TEXTE};
            line-height: 1.6;
            margin-bottom: 10px;
        }}

        /* ===== BADGES MOTS-CLES ===== */
        .kw-badges {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 8px;
        }}
        .kw-badge {{
            background: {VERT_PROCIVIS};
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.78rem;
            font-weight: 500;
            letter-spacing: 0.3px;
        }}
        .kw-badge.gris {{
            background: {GRIS_PROCIVIS};
        }}
        .kw-badge.rose {{
            background: {ROSE_BAILLEUR};
        }}
        .kw-badge.bleu {{
            background: {BLEU_PROMOTEUR};
        }}

        /* ===== CONTEXTE CITATIONS ===== */
        .citation-block {{
            background: {VERT_CLAIR};
            border-radius: 8px;
            padding: 12px 16px;
            margin: 6px 0;
            border-left: 3px solid {VERT_PROCIVIS};
        }}
        .citation-kw {{
            font-weight: 600;
            color: {VERT_FONCE};
            font-size: 0.85rem;
        }}
        .citation-text {{
            font-size: 0.85rem;
            color: {GRIS_TEXTE};
            font-style: italic;
            margin-top: 4px;
        }}

        /* ===== SECTION ENVOI ===== */
        .send-section {{
            background: white;
            border-radius: 16px;
            padding: 2rem;
            margin-top: 2rem;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06);
            border-top: 4px solid {GRIS_PROCIVIS};
        }}
        .send-title {{
            color: {GRIS_PROCIVIS};
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }}

        /* ===== BOUTONS ===== */
        .stButton>button[kind="primary"] {{
            background: linear-gradient(135deg, {VERT_PROCIVIS}, {VERT_FONCE});
            border: none;
            border-radius: 8px;
            font-weight: 600;
            letter-spacing: 0.3px;
            padding: 0.6rem 2rem;
            transition: all 0.2s ease;
        }}
        .stButton>button[kind="primary"]:hover {{
            background: linear-gradient(135deg, {VERT_FONCE}, #5E8A1E);
            box-shadow: 0 4px 12px rgba(151, 195, 61, 0.35);
        }}

        /* ===== CHECKBOX STYLE ===== */
        .stCheckbox label {{
            font-weight: 500;
        }}

        /* ===== HIDE STREAMLIT BRANDING ===== */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        header {{visibility: hidden;}}

        /* ===== SELECTBOX ===== */
        .stSelectbox > div > div {{
            border-radius: 8px;
        }}
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Connexion Google Sheets
# ---------------------------------------------------------------------------

@st.cache_resource
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def load_data() -> pd.DataFrame:
    try:
        client = get_gspread_client()
        sheet = client.open_by_key(SPREADSHEET_ID)
        ws = sheet.worksheet(SHEET_NAME)
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)
    except Exception as e:
        st.error(f"Erreur de chargement Google Sheets : {e}")
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def week_label(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"S{iso.week:02d}-{iso.year}"


def available_weeks(df: pd.DataFrame) -> list[str]:
    if df.empty or "semaine" not in df.columns:
        return []
    weeks = sorted(df["semaine"].dropna().unique(), reverse=True)
    return list(weeks)


def col(row: pd.Series, *keys: str, default: str = "—") -> str:
    for k in keys:
        val = row.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def badge_color(idx: int) -> str:
    colors = ["", "gris", "rose", "bleu"]
    return colors[idx % len(colors)]


def render_article_card(titre, media, date_pub, resume, mots_cles_str, contexte_str, is_selected):
    """Génère le HTML d'une carte article."""
    selected_class = " selected" if is_selected else ""

    # Métadonnées
    meta_html = f"""
    <div class="article-meta">
        <div class="meta-item"><span class="meta-icon">📡</span> {media}</div>
        <div class="meta-item"><span class="meta-icon">📅</span> {date_pub}</div>
    </div>
    """

    # Badges mots-clés
    badges_html = ""
    if mots_cles_str and mots_cles_str not in ("—", ""):
        kw_list = [k.strip() for k in mots_cles_str.split(",") if k.strip()]
        if kw_list:
            badges = "".join(
                f'<span class="kw-badge {badge_color(i)}">{kw}</span>'
                for i, kw in enumerate(kw_list)
            )
            badges_html = f'<div class="kw-badges">{badges}</div>'

    # Citations
    citations_html = ""
    if contexte_str and contexte_str not in ("—", "[]", ""):
        try:
            ctx_data = json.loads(contexte_str)
            if ctx_data:
                blocks = ""
                for item in ctx_data:
                    kw = item.get("mot_cle", "")
                    ctx = item.get("contexte", "")
                    blocks += f"""
                    <div class="citation-block">
                        <div class="citation-kw">{kw}</div>
                        <div class="citation-text">« {ctx} »</div>
                    </div>
                    """
                citations_html = blocks
        except (json.JSONDecodeError, TypeError):
            pass

    return f"""
    <div class="article-card{selected_class}">
        <div class="article-title">{titre}</div>
        {meta_html}
        <div class="article-resume">{resume}</div>
        {badges_html}
    </div>
    """, citations_html


# ---------------------------------------------------------------------------
# Interface principale
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Veille Presse Procivis",
        page_icon="📰",
        layout="wide",
    )

    inject_css()

    # --- Hero Header ---
    st.markdown("""
    <div class="hero">
        <h1>📰 Veille presse hebdomadaire</h1>
        <div class="hero-sub">Articles analysés par IA — sélectionnez, consultez et partagez</div>
    </div>
    """, unsafe_allow_html=True)

    # --- Chargement ---
    with st.spinner("Chargement des données…"):
        df = load_data()

    if df.empty:
        st.info("Aucune donnée dans le Google Sheet pour le moment. Le workflow N8N n'a peut-être pas encore tourné.")
        return

    # Normaliser les noms de colonnes
    col_map = {c: c.lower().strip() for c in df.columns}
    df = df.rename(columns=col_map)

    # --- Filtre semaine + Refresh ---
    weeks = available_weeks(df)
    current = week_label(datetime.now())

    col_filter, col_spacer, col_refresh = st.columns([2, 6, 1.5])
    with col_filter:
        options = weeks if weeks else [current]
        selected_week = st.selectbox(
            "📆 Semaine",
            options=["Toutes"] + options,
            index=0,
        )
    with col_refresh:
        st.write("")
        st.write("")
        if st.button("🔄 Rafraichir", use_container_width=True):
            st.cache_resource.clear()
            st.rerun()

    # --- Filtrage ---
    if selected_week != "Toutes":
        df_filtered = df[df["semaine"] == selected_week].copy()
    else:
        df_filtered = df.copy()

    nb = len(df_filtered)

    # Compter les articles avec mots-clés
    nb_with_kw = 0
    for _, row in df_filtered.iterrows():
        kw = col(row, "mots_cles_trouves", "mots-clés trouvés", default="")
        if kw and kw not in ("—", ""):
            nb_with_kw += 1

    # Médias uniques
    medias = set()
    for _, row in df_filtered.iterrows():
        m = col(row, "media", "média")
        if m != "—":
            medias.add(m)

    # --- Barre de stats ---
    st.markdown(f"""
    <div class="stats-bar">
        <div class="stat-card">
            <div class="stat-number">{nb}</div>
            <div class="stat-label">Article{"s" if nb > 1 else ""}</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{len(medias)}</div>
            <div class="stat-label">Média{"s" if len(medias) > 1 else ""} source{"s" if len(medias) > 1 else ""}</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{nb_with_kw}</div>
            <div class="stat-label">Mention{"s" if nb_with_kw > 1 else ""} Procivis</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if nb == 0:
        st.info("Aucun article pour cette semaine.")
        return

    # --- Sélection globale ---
    select_all = st.checkbox("✅ Tout sélectionner", key="select_all")
    selected_articles = []

    # --- Liste des articles ---
    for idx, row in df_filtered.iterrows():
        media = col(row, "media", "média")
        titre = col(row, "titre")
        date_pub = col(row, "date_publication", "date publication")
        resume = col(row, "resume", "résumé")
        mots_cles = col(row, "mots_cles_trouves", "mots-clés trouvés", default="")
        contexte = col(row, "contexte_citations", "contexte citations", default="")
        drive_id = col(row, "id_fichier_drive", "id fichier drive", default="")

        # Checkbox
        checked = st.checkbox(
            f"Sélectionner : {titre[:60]}",
            value=select_all,
            key=f"art_{idx}",
            label_visibility="collapsed",
        )

        # Carte article HTML
        card_html, citations_html = render_article_card(
            titre, media, date_pub, resume, mots_cles, contexte, checked
        )
        st.markdown(card_html, unsafe_allow_html=True)

        # Citations en expander natif Streamlit (ne peut pas être en pur HTML)
        if citations_html:
            with st.expander("💬 Voir le contexte des citations"):
                st.markdown(citations_html, unsafe_allow_html=True)

        if checked:
            selected_articles.append({
                "media": media,
                "titre": titre,
                "date_publication": date_pub,
                "fichier_drive_id": drive_id,
            })

    # --- Section envoi mail ---
    st.markdown('<div class="send-section">', unsafe_allow_html=True)
    st.markdown('<div class="send-title">✉️ Envoyer la sélection par mail</div>', unsafe_allow_html=True)

    col_dest, col_nom = st.columns(2)
    with col_dest:
        dest_email = st.text_input("Email du destinataire", value=DEFAULT_DEST_EMAIL)
    with col_nom:
        dest_nom = st.text_input("Nom du destinataire", value=DEFAULT_DEST_NOM)

    col_count, col_send = st.columns([3, 1])
    n_sel = len(selected_articles)
    with col_count:
        if n_sel == 0:
            st.warning("Aucun article sélectionné.")
        else:
            st.success(f"🎯 {n_sel} article{'s' if n_sel > 1 else ''} sélectionné{'s' if n_sel > 1 else ''}")

    with col_send:
        disabled = n_sel == 0 or not dest_email
        if st.button("📤 Envoyer", type="primary", use_container_width=True, disabled=disabled):
            payload = {
                "destinataire_email": dest_email,
                "destinataire_nom": dest_nom,
                "semaine": selected_week if selected_week != "Toutes" else current,
                "articles_procivis": selected_articles,
            }
            with st.spinner("Envoi en cours via N8N…"):
                try:
                    resp = requests.post(N8N_WEBHOOK_URL, json=payload, timeout=120)
                    if resp.status_code == 200:
                        result = resp.json()
                        if result.get("status") == "success":
                            st.success("Mail envoyé avec succès !")
                            st.balloons()
                        else:
                            st.error(f"Erreur N8N : {result.get('message', 'Erreur inconnue')}")
                    else:
                        st.error(f"Erreur HTTP {resp.status_code} : {resp.text[:300]}")
                except requests.exceptions.Timeout:
                    st.error("Le webhook N8N n'a pas répondu (timeout 120s).")
                except requests.exceptions.ConnectionError:
                    st.error("Impossible de contacter le webhook N8N. Vérifiez l'URL et que N8N est en ligne.")
                except Exception as e:
                    st.error(f"Erreur inattendue : {e}")

    st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
