"""
data_loader.py — Ingestion, validation et nettoyage des données d'inventaire.

Ce module gère le chargement des fichiers Excel/CSV, valide la présence
des colonnes obligatoires, nettoie les données et produit un rapport
de validation détaillé pour l'utilisateur.
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any


# Colonnes obligatoires avec leur type attendu
COLONNES_OBLIGATOIRES: dict[str, str] = {
    "article_id": "str",
    "article_nom": "str",
    "stock_actuel": "float",
    "consommation_moyenne_jour": "float",
    "ecart_type_consommation": "float",
    "delai_fournisseur_jours": "float",
    "delai_ecart_type": "float",
    "prix_unitaire": "float",
    "cout_commande": "float",
    "taux_possession": "float",
    "fournisseur_id": "str",
    "fournisseur_nom": "str",
    "derniere_livraison_date": "date",
    "quantite_commandee_en_cours": "float",
}

# Colonnes numériques qui ne peuvent pas être négatives
COLONNES_POSITIVES = [
    "stock_actuel",
    "consommation_moyenne_jour",
    "ecart_type_consommation",
    "delai_fournisseur_jours",
    "delai_ecart_type",
    "prix_unitaire",
    "cout_commande",
    "taux_possession",
    "quantite_commandee_en_cours",
]


def load_file(filepath: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Charge un fichier Excel (.xlsx) ou CSV et retourne les données nettoyées
    accompagnées d'un rapport de validation.

    Parameters
    ----------
    filepath : str
        Chemin vers le fichier à charger (xlsx ou csv).

    Returns
    -------
    tuple[pd.DataFrame, dict]
        - df_propre : DataFrame nettoyé et typé
        - rapport_validation : dictionnaire contenant :
            - colonnes_manquantes : list[str]
            - lignes_invalides : int
            - avertissements : list[str]
            - nb_lignes_initiales : int
            - nb_lignes_finales : int

    Raises
    ------
    ValueError
        Si des colonnes obligatoires sont absentes du fichier.
    """
    rapport: dict[str, Any] = {
        "colonnes_manquantes": [],
        "lignes_invalides": 0,
        "avertissements": [],
        "nb_lignes_initiales": 0,
        "nb_lignes_finales": 0,
    }

    # --- 1. Lecture du fichier ---
    if filepath.endswith(".csv"):
        df = pd.read_csv(filepath)
    elif filepath.endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath, engine="openpyxl")
    else:
        raise ValueError(
            f"Format non supporté : {filepath}. Utilisez .xlsx ou .csv"
        )

    rapport["nb_lignes_initiales"] = len(df)

    # Normaliser les noms de colonnes (strip, lower)
    df.columns = df.columns.str.strip().str.lower()

    # --- 2. Vérification des colonnes obligatoires ---
    colonnes_presentes = set(df.columns)
    colonnes_requises = set(COLONNES_OBLIGATOIRES.keys())
    colonnes_manquantes = colonnes_requises - colonnes_presentes
    rapport["colonnes_manquantes"] = sorted(list(colonnes_manquantes))

    if colonnes_manquantes:
        raise ValueError(
            f"Colonnes obligatoires manquantes : {sorted(list(colonnes_manquantes))}. "
            f"Le fichier doit contenir : {sorted(list(colonnes_requises))}"
        )

    # --- 3. Typage et nettoyage ---
    # Colonnes numériques
    colonnes_numeriques = [
        col for col, typ in COLONNES_OBLIGATOIRES.items() if typ == "float"
    ]
    for col in colonnes_numeriques:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Colonnes texte
    colonnes_texte = [
        col for col, typ in COLONNES_OBLIGATOIRES.items() if typ == "str"
    ]
    for col in colonnes_texte:
        df[col] = df[col].astype(str).str.strip()

    # Colonne date
    df["derniere_livraison_date"] = pd.to_datetime(
        df["derniere_livraison_date"], errors="coerce"
    )

    # --- 4. Détection des lignes invalides ---
    # Une ligne est invalide si article_id est NaN/vide OU si toutes les colonnes
    # numériques clés sont NaN
    masque_invalide = (
        df["article_id"].isin(["nan", "", "None"])
        | df["stock_actuel"].isna()
        | df["consommation_moyenne_jour"].isna()
    )

    nb_invalides = masque_invalide.sum()
    rapport["lignes_invalides"] = int(nb_invalides)

    if nb_invalides > 0:
        rapport["avertissements"].append(
            f"{nb_invalides} ligne(s) invalide(s) supprimée(s) "
            f"(article_id manquant ou valeurs numériques clés manquantes)."
        )
        df = df[~masque_invalide].copy()

    # --- 5. Remplacement des valeurs négatives ---
    for col in COLONNES_POSITIVES:
        nb_neg = (df[col] < 0).sum()
        if nb_neg > 0:
            rapport["avertissements"].append(
                f"Colonne '{col}' : {nb_neg} valeur(s) négative(s) remplacée(s) par 0."
            )
            df[col] = df[col].clip(lower=0)

    # --- 6. Remplissage des NaN résiduels ---
    # Pour les colonnes numériques optionnelles, remplir avec 0
    for col in colonnes_numeriques:
        nb_nan = df[col].isna().sum()
        if nb_nan > 0:
            rapport["avertissements"].append(
                f"Colonne '{col}' : {nb_nan} valeur(s) manquante(s) remplacée(s) par 0."
            )
            df[col] = df[col].fillna(0)

    # Dates manquantes → date du jour
    nb_dates_na = df["derniere_livraison_date"].isna().sum()
    if nb_dates_na > 0:
        rapport["avertissements"].append(
            f"{nb_dates_na} date(s) de livraison manquante(s) remplacée(s) par la date du jour."
        )
        df["derniere_livraison_date"] = df["derniere_livraison_date"].fillna(
            pd.Timestamp(datetime.now().date())
        )

    # --- 7. Réinitialiser l'index ---
    df = df.reset_index(drop=True)
    rapport["nb_lignes_finales"] = len(df)

    return df, rapport


def save_to_sqlite(df: pd.DataFrame, db_path: str = "data/stocks.db") -> None:
    """
    Persiste le DataFrame nettoyé dans une base SQLite locale.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame nettoyé à sauvegarder.
    db_path : str
        Chemin vers le fichier SQLite.
    """
    import sqlite3
    import os

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        df.to_sql("articles", conn, if_exists="replace", index=False)
    finally:
        conn.close()


def load_from_sqlite(db_path: str = "data/stocks.db") -> pd.DataFrame | None:
    """
    Charge les données depuis la base SQLite locale.

    Returns None si la base n'existe pas ou si la table est vide.
    """
    import sqlite3
    import os

    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql("SELECT * FROM articles", conn)
        if df.empty:
            return None
        # Re-typer la colonne date
        df["derniere_livraison_date"] = pd.to_datetime(
            df["derniere_livraison_date"], errors="coerce"
        )
        return df
    except Exception:
        return None
    finally:
        conn.close()
