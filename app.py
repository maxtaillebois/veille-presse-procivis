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

# Couleurs de la charte Procivis (palette verts)
VERT_TRES_FONCE = "#303C0A"     # Couleur principale — boutons, hero
VERT_FONCE = "#36580E"          # Dégradé secondaire
VERT_FORET = "#182D00"          # Accent très sombre
VERT_VIF = "#97C11F"            # Vert vif — badges, accents
VERT_OLIVE = "#6E755A"          # Gris-vert — texte secondaire
BEIGE = "#F8F3EC"               # Fond de page
VERT_KAKI = "#6D784B"           # Secondaire — badges alternatifs
VERT_GRIS = "#878C7A"           # Secondaire — méta
VERT_CLAIR = "#CFE986"          # Secondaire — fonds légers, sélection
VERT_CLAIR_PALE = "#EDF5D0"     # Fond très léger pour citations
GRIS_TEXTE = "#303C0A"          # Texte courant = vert très foncé


# ---------------------------------------------------------------------------
# CSS personnalisé
# ---------------------------------------------------------------------------

def inject_css():
    st.markdown(
        f"""<style>
.stApp {{ background-color: {BEIGE}; }}

/* HERO */
.hero {{
  background: linear-gradient(135deg, {VERT_TRES_FONCE} 0%, {VERT_FONCE} 100%);
  color: white; padding: 2rem 2.5rem; border-radius: 16px;
  margin-bottom: 1.5rem; box-shadow: 0 4px 20px rgba(48,60,10,.3);
}}
.hero h1 {{ margin:0; font-size:2rem; font-weight:700; }}
.hero .hero-sub {{ margin:.5rem 0 0; font-size:1rem; opacity:.85; font-weight:300; }}

/* STATS */
.stats-bar {{ display:flex; gap:1rem; margin-bottom:1.5rem; }}
.stat-card {{
  background:white; border-radius:12px; padding:1rem 1.5rem; flex:1;
  box-shadow:0 2px 8px rgba(0,0,0,.06); border-left:4px solid {VERT_FONCE};
}}
.stat-card .stat-number {{ font-size:1.8rem; font-weight:700; color:{VERT_FONCE}; line-height:1; }}
.stat-card .stat-label {{ font-size:.8rem; color:{VERT_OLIVE}; text-transform:uppercase; letter-spacing:.5px; margin-top:4px; }}

/* ARTICLE CARD */
.article-card {{
  background:white; border-radius:12px; padding:1.5rem; margin-bottom:.5rem;
  box-shadow:0 2px 10px rgba(0,0,0,.06); border-left:4px solid {VERT_FONCE};
  transition: box-shadow .2s, transform .2s;
}}
.article-card:hover {{ box-shadow:0 4px 20px rgba(0,0,0,.1); transform:translateY(-1px); }}
.article-card.selected {{ border-left-color:{VERT_VIF}; background:#F4F9E4; }}
.article-title {{ font-size:1.1rem; font-weight:600; color:{VERT_TRES_FONCE}; margin-bottom:6px; line-height:1.3; }}
.article-meta {{ display:flex; align-items:center; gap:16px; margin-bottom:10px; flex-wrap:wrap; }}
.meta-item {{ display:flex; align-items:center; gap:5px; font-size:.85rem; color:{VERT_GRIS}; }}
.article-resume {{ font-size:.93rem; color:{GRIS_TEXTE}; line-height:1.6; margin-bottom:10px; }}
.section-label {{ font-size:.75rem; text-transform:uppercase; letter-spacing:.5px; color:{VERT_OLIVE}; font-weight:600; margin-bottom:4px; margin-top:12px; }}

/* BADGES */
.kw-badges {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:8px; }}
.kw-badge {{
  background:{VERT_FONCE}; color:white; padding:4px 12px;
  border-radius:20px; font-size:.78rem; font-weight:500; letter-spacing:.3px;
}}
.kw-badge.gris {{ background:{VERT_KAKI}; }}
.kw-badge.rose {{ background:{VERT_OLIVE}; }}
.kw-badge.bleu {{ background:{VERT_TRES_FONCE}; }}

/* CITATIONS dans la carte */
.citation-block {{
  background:{VERT_CLAIR_PALE}; border-radius:8px; padding:12px 16px;
  margin:6px 0; border-left:3px solid {VERT_VIF};
}}
.citation-kw {{ font-weight:600; color:{VERT_FONCE}; font-size:.85rem; }}
.citation-text {{ font-size:.85rem; color:{GRIS_TEXTE}; font-style:italic; margin-top:4px; }}
.citations-wrapper {{ margin-top:12px; }}

/* SEND TITLE */
.send-title {{ color:{VERT_TRES_FONCE}; font-size:1.3rem; font-weight:600; margin-bottom:1rem; }}

/* INPUT LABELS — toujours lisibles */
.stTextInput label {{
  color: {VERT_TRES_FONCE} !important;
  font-weight: 500 !important;
  opacity: 1 !important;
}}
.stTextInput label p {{
  color: {VERT_TRES_FONCE} !important;
  opacity: 1 !important;
}}
.stSelectbox label, .stSelectbox label p {{
  color: {VERT_TRES_FONCE} !important;
  opacity: 1 !important;
}}

/* BUTTONS */
.stButton>button[kind="primary"] {{
  background:linear-gradient(135deg,{VERT_TRES_FONCE},{VERT_FONCE}) !important;
  color:white !important;
  border:none; border-radius:8px; font-weight:600; padding:.6rem 2rem;
}}
.stButton>button[kind="primary"]:hover {{
  background:linear-gradient(135deg,{VERT_FORET},{VERT_TRES_FONCE}) !important;
  box-shadow:0 4px 12px rgba(48,60,10,.35);
}}

/* CHECKBOX — vert foncé Procivis, label toujours lisible */
.stCheckbox label {{
  font-weight: 500 !important;
  color: {VERT_TRES_FONCE} !important;
  opacity: 1 !important;
}}
.stCheckbox label span {{
  color: {VERT_TRES_FONCE} !important;
  opacity: 1 !important;
}}
.stCheckbox label p {{
  color: {VERT_TRES_FONCE} !important;
  opacity: 1 !important;
}}
/* Boîte de la checkbox */
.stCheckbox [data-testid="stCheckbox"] > div:first-child {{
  border-color: {VERT_FONCE} !important;
}}
.stCheckbox svg {{
  fill: {VERT_FONCE} !important;
  color: {VERT_FONCE} !important;
}}
/* Versions récentes Streamlit */
[data-testid="stCheckbox"] label div[role="checkbox"] {{
  border-color: {VERT_FONCE} !important;
}}
[data-testid="stCheckbox"] label div[role="checkbox"][aria-checked="true"] {{
  background-color: {VERT_FONCE} !important;
  border-color: {VERT_FONCE} !important;
}}

/* Compteur sélection — style unifié */
.selection-count {{
  background: {VERT_CLAIR_PALE}; border-left: 4px solid {VERT_FONCE};
  padding: 12px 16px; border-radius: 8px; font-size: .95rem;
  color: {VERT_TRES_FONCE}; font-weight: 500;
}}
.selection-count.empty {{
  background: {BEIGE}; border-left-color: {VERT_GRIS}; color: {VERT_OLIVE};
}}

/* REORDER BUTTONS */
.reorder-btn {{
  display:inline-flex; align-items:center; justify-content:center;
  width:32px; height:32px; border-radius:8px;
  border:1.5px solid {VERT_FONCE}; background:white;
  color:{VERT_FONCE}; font-size:1rem; cursor:pointer;
  transition: all .15s;
}}
.reorder-btn:hover {{ background:{VERT_CLAIR_PALE}; }}
.reorder-btn.disabled {{ opacity:.25; cursor:default; border-color:{VERT_GRIS}; color:{VERT_GRIS}; }}
.order-number {{
  display:inline-flex; align-items:center; justify-content:center;
  width:28px; height:28px; border-radius:50%;
  background:{VERT_FONCE}; color:white;
  font-size:.85rem; font-weight:700;
}}

/* HIDE BRANDING */
#MainMenu {{visibility:hidden;}}
footer {{visibility:hidden;}}
header {{visibility:hidden;}}
</style>""",
        unsafe_allow_html=True,
    )


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


def col(row: pd.Series, *keys: str, default: str = "\u2014") -> str:
    for k in keys:
        val = row.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def badge_color(idx: int) -> str:
    colors = ["", "gris", "rose", "bleu"]
    return colors[idx % len(colors)]


def build_card_html(titre, media, date_pub, resume, mots_cles_str, contexte_str, is_selected):
    """Construit le HTML complet d'une carte article (avec citations intégrées)."""
    sel = " selected" if is_selected else ""

    # Badges mots-clés
    badges = ""
    if mots_cles_str and mots_cles_str not in ("\u2014", ""):
        kw_list = [k.strip() for k in mots_cles_str.split(",") if k.strip()]
        if kw_list:
            spans = "".join(
                f'<span class="kw-badge {badge_color(i)}">{kw}</span>'
                for i, kw in enumerate(kw_list)
            )
            badges = f'<div class="kw-badges">{spans}</div>'

    # Citations intégrées dans la carte
    citations = ""
    if contexte_str and contexte_str not in ("\u2014", "[]", ""):
        try:
            ctx_data = json.loads(contexte_str)
            if ctx_data:
                blocks = ""
                for item in ctx_data:
                    kw = item.get("mot_cle", "")
                    ctx = item.get("contexte", "")
                    blocks += (
                        f'<div class="citation-block">'
                        f'<div class="citation-kw">{kw}</div>'
                        f'<div class="citation-text">\u00ab\u00a0{ctx}\u00a0\u00bb</div>'
                        f'</div>'
                    )
                citations = f'<div class="citations-wrapper"><div class="section-label">Contexte de citation</div>{blocks}</div>'
        except (json.JSONDecodeError, TypeError):
            pass

    html = (
        f'<div class="article-card{sel}">'
        f'<div class="article-title">{titre}</div>'
        f'<div class="article-meta">'
        f'<div class="meta-item">📡 {media}</div>'
        f'<div class="meta-item">📅 {date_pub}</div>'
        f'</div>'
        f'<div class="section-label">Résumé</div>'
        f'<div class="article-resume">{resume}</div>'
        f'{badges}'
        f'{citations}'
        f'</div>'
    )
    return html


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
    st.markdown(
        '<div class="hero">'
        '<h1>📰 Veille presse hebdomadaire</h1>'
        '<div class="hero-sub">Articles analysés par IA — sélectionnez, consultez et partagez</div>'
        '</div>',
        unsafe_allow_html=True,
    )

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
        if kw and kw not in ("\u2014", ""):
            nb_with_kw += 1

    # Médias uniques
    medias = set()
    for _, row in df_filtered.iterrows():
        m = col(row, "media", "média")
        if m != "\u2014":
            medias.add(m)

    # --- Barre de stats ---
    nb_medias = len(medias)
    st.markdown(
        f'<div class="stats-bar">'
        f'<div class="stat-card"><div class="stat-number">{nb}</div>'
        f'<div class="stat-label">Article{"s" if nb > 1 else ""}</div></div>'
        f'<div class="stat-card"><div class="stat-number">{nb_medias}</div>'
        f'<div class="stat-label">Média{"s" if nb_medias > 1 else ""} source{"s" if nb_medias > 1 else ""}</div></div>'
        f'<div class="stat-card"><div class="stat-number">{nb_with_kw}</div>'
        f'<div class="stat-label">Mention{"s" if nb_with_kw > 1 else ""} Procivis</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if nb == 0:
        st.info("Aucun article pour cette semaine.")
        return

    # --- Construire la liste des index et gérer l'ordre ---
    article_indices = list(df_filtered.index)

    # Initialiser l'ordre dans session_state
    order_key = f"order_{selected_week}"
    if order_key not in st.session_state or set(st.session_state[order_key]) != set(article_indices):
        st.session_state[order_key] = list(article_indices)

    ordered_indices = st.session_state[order_key]

    # Callback "Tout sélectionner" : force l'état de chaque checkbox
    def on_select_all_change():
        val = st.session_state["select_all"]
        for i in article_indices:
            st.session_state[f"art_{i}"] = val

    st.checkbox(
        "Tout sélectionner / désélectionner",
        key="select_all",
        on_change=on_select_all_change,
    )

    selected_articles = []

    # --- Liste des articles (dans l'ordre choisi) ---
    for position, idx in enumerate(ordered_indices):
        row = df_filtered.loc[idx]
        media = col(row, "media", "média")
        titre = col(row, "titre")
        date_pub = col(row, "date_publication", "date publication")
        resume = col(row, "resume", "résumé")
        mots_cles = col(row, "mots_cles_trouves", "mots-clés trouvés", default="")
        contexte = col(row, "contexte_citations", "contexte citations", default="")
        drive_id = col(row, "id_fichier_drive", "id fichier drive", default="")

        # Initialiser la session_state si pas encore fait
        if f"art_{idx}" not in st.session_state:
            st.session_state[f"art_{idx}"] = False

        # Ligne : numéro + checkbox + boutons ↑↓
        col_num, col_check, col_up, col_down = st.columns([0.3, 6, 0.4, 0.4])
        with col_num:
            st.markdown(f'<div style="padding-top:6px"><span class="order-number">{position + 1}</span></div>', unsafe_allow_html=True)
        with col_check:
            checked = st.checkbox("Garder cet article", key=f"art_{idx}")
        with col_up:
            if position > 0:
                if st.button("↑", key=f"up_{idx}", help="Monter"):
                    order = st.session_state[order_key]
                    p = order.index(idx)
                    order[p], order[p - 1] = order[p - 1], order[p]
                    st.session_state[order_key] = order
                    st.rerun()
            else:
                st.markdown('<div style="padding-top:6px;opacity:.2;text-align:center">↑</div>', unsafe_allow_html=True)
        with col_down:
            if position < len(ordered_indices) - 1:
                if st.button("↓", key=f"down_{idx}", help="Descendre"):
                    order = st.session_state[order_key]
                    p = order.index(idx)
                    order[p], order[p + 1] = order[p + 1], order[p]
                    st.session_state[order_key] = order
                    st.rerun()
            else:
                st.markdown('<div style="padding-top:6px;opacity:.2;text-align:center">↓</div>', unsafe_allow_html=True)

        # Carte article
        card_html = build_card_html(titre, media, date_pub, resume, mots_cles, contexte, checked)
        st.markdown(card_html, unsafe_allow_html=True)

        if checked:
            selected_articles.append({
                "media": media,
                "titre": titre,
                "date_publication": date_pub,
                "fichier_drive_id": drive_id,
            })

    # --- Section envoi mail ---
    st.markdown("---")
    st.markdown(
        '<div class="send-title">✉️ Envoyer la sélection par mail</div>',
        unsafe_allow_html=True,
    )

    col_dest, col_nom = st.columns(2)
    with col_dest:
        dest_email = st.text_input(
            "Destinataire principal",
            value=DEFAULT_DEST_EMAIL,
        )
    with col_nom:
        dest_nom = st.text_input("Nom du destinataire", value=DEFAULT_DEST_NOM)

    cc_emails = st.text_input(
        "CC (copie carbone)",
        value="",
        help="Plusieurs adresses possibles, séparées par des virgules",
    )

    # Compteur sélection — style custom au lieu du warning illisible
    n_sel = len(selected_articles)
    if n_sel == 0:
        st.markdown(
            '<div class="selection-count empty">Aucun article sélectionné — cochez « Garder cet article » ci-dessus</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="selection-count">🎯 {n_sel} article{"s" if n_sel > 1 else ""} sélectionné{"s" if n_sel > 1 else ""}</div>',
            unsafe_allow_html=True,
        )

    disabled = n_sel == 0 or not dest_email
    if st.button("📤 Envoyer", type="primary", use_container_width=True, disabled=disabled):
        payload = {
            "destinataire_email": dest_email,
            "destinataire_nom": dest_nom,
            "cc_emails": cc_emails,
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


if __name__ == "__main__":
    main()
