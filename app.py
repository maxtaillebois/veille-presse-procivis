"""
Veille Presse Procivis — Application Streamlit
================================================
Interface de consultation et sélection des articles de veille presse.
Lit les données depuis Google Sheets (alimenté par N8N) et permet
d'envoyer un récapitulatif par mail via un webhook N8N.

Onglet unique : Veille interne Procivis.
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

# Mots-clés Procivis pour les badges visuels
MOTS_CLES = ["Procivis", "Immo de France", "Maisons d'en France", "Yannick Borde"]


# ---------------------------------------------------------------------------
# Connexion Google Sheets
# ---------------------------------------------------------------------------

@st.cache_resource
def get_gspread_client():
    """Initialise le client gspread via le service account."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def load_data() -> pd.DataFrame:
    """Charge l'onglet Veille Procivis en DataFrame."""
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
    """Retourne le label semaine au format S##-YYYY."""
    iso = dt.isocalendar()
    return f"S{iso.week:02d}-{iso.year}"


def available_weeks(df: pd.DataFrame) -> list[str]:
    """Retourne la liste des semaines présentes dans les données, triées décroissant."""
    if df.empty or "semaine" not in df.columns:
        return []
    weeks = sorted(df["semaine"].dropna().unique(), reverse=True)
    return list(weeks)


def col(row: pd.Series, *keys: str, default: str = "—") -> str:
    """Lit la première colonne trouvée parmi les clés proposées (gestion accents/variantes)."""
    for k in keys:
        val = row.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Veille Presse Procivis",
        page_icon="📰",
        layout="wide",
    )

    # --- En-tête ---
    st.title("📰 Veille presse — Procivis")
    st.caption("Consultez les articles analysés par l'IA, sélectionnez ceux à conserver et envoyez le récapitulatif par mail.")

    # --- Chargement ---
    with st.spinner("Chargement des données…"):
        df = load_data()

    if df.empty:
        st.info("Aucune donnée dans le Google Sheet pour le moment. Le workflow N8N n'a peut-être pas encore tourné.")
        return

    # Normaliser les noms de colonnes (le workflow envoie en snake_case, le Sheet peut avoir des accents)
    col_map = {}
    for c in df.columns:
        col_map[c] = c.lower().strip()
    df = df.rename(columns=col_map)

    # --- Filtre semaine ---
    weeks = available_weeks(df)
    current = week_label(datetime.now())

    col_filter, col_refresh = st.columns([3, 1])
    with col_filter:
        options = weeks if weeks else [current]
        default_idx = 0
        if current in options:
            default_idx = options.index(current)
        selected_week = st.selectbox("Filtrer par semaine", options=["Toutes"] + options, index=0)

    with col_refresh:
        st.write("")
        st.write("")
        if st.button("🔄 Rafraîchir", use_container_width=True):
            st.cache_resource.clear()
            st.rerun()

    # --- Filtrage ---
    if selected_week != "Toutes":
        df_filtered = df[df["semaine"] == selected_week].copy()
    else:
        df_filtered = df.copy()

    nb = len(df_filtered)
    st.markdown(f"**{nb} article{'s' if nb > 1 else ''}** trouvé{'s' if nb > 1 else ''}")

    if nb == 0:
        st.info("Aucun article pour cette semaine.")
        return

    # --- Liste des articles ---
    st.markdown("---")

    select_all = st.checkbox("Tout sélectionner", key="select_all")
    selected_articles = []

    for idx, row in df_filtered.iterrows():
        media = col(row, "media", "média")
        titre = col(row, "titre")
        date_pub = col(row, "date_publication", "date publication")
        resume = col(row, "resume", "résumé")
        mots_cles = col(row, "mots_cles_trouves", "mots-clés trouvés", "mots_cles_trouves", default="")
        contexte = col(row, "contexte_citations", "contexte citations", default="")
        drive_id = col(row, "id_fichier_drive", "id fichier drive", default="")

        with st.container():
            col_check, col_content = st.columns([0.4, 9.6])

            with col_check:
                checked = st.checkbox("Sel.", value=select_all, key=f"art_{idx}", label_visibility="collapsed")

            with col_content:
                st.markdown(f"**{titre}**")
                st.caption(f"📡 {media}  ·  📅 {date_pub}")
                st.write(resume)

                # Mots-clés trouvés → badges
                if mots_cles:
                    kw_list = [k.strip() for k in mots_cles.split(",") if k.strip()]
                    if kw_list:
                        badges = "  ".join([f":blue-background[{kw}]" for kw in kw_list])
                        st.markdown(f"🔑 {badges}")

                        # Contexte de citation (JSON)
                        if contexte and contexte not in ("—", "[]", ""):
                            try:
                                ctx_data = json.loads(contexte)
                                if ctx_data:
                                    with st.expander("Voir le contexte des citations"):
                                        for item in ctx_data:
                                            kw = item.get("mot_cle", "")
                                            ctx_text = item.get("contexte", "")
                                            st.markdown(f"**{kw}** : « _{ctx_text}_ »")
                            except (json.JSONDecodeError, TypeError):
                                pass

            if checked:
                selected_articles.append({
                    "media": media,
                    "titre": titre,
                    "date_publication": date_pub,
                    "fichier_drive_id": drive_id,
                })

        st.divider()

    # --- Section envoi mail ---
    st.markdown("### ✉️ Envoyer la sélection par mail")

    col_dest, col_nom = st.columns(2)
    with col_dest:
        dest_email = st.text_input("Email du destinataire", value=DEFAULT_DEST_EMAIL)
    with col_nom:
        dest_nom = st.text_input("Nom du destinataire", value=DEFAULT_DEST_NOM)

    col_count, col_send = st.columns([3, 1])
    with col_count:
        n_sel = len(selected_articles)
        if n_sel == 0:
            st.warning("Aucun article sélectionné.")
        else:
            st.success(f"{n_sel} article{'s' if n_sel > 1 else ''} sélectionné{'s' if n_sel > 1 else ''}")

    with col_send:
        disabled = n_sel == 0 or not dest_email
        if st.button("Envoyer", type="primary", use_container_width=True, disabled=disabled):
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


if __name__ == "__main__":
    main()
