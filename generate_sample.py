"""
generate_sample.py — Génération du fichier sample_data.xlsx avec 50 articles réalistes.

Ce script crée un jeu de données de test couvrant :
- Segments ABC : A (10 articles), B (15 articles), C (25 articles)
- Segments XYZ répartis uniformément
- Au moins 5 alertes CRITIQUE, 10 PRÉVENTIF, 5 DORMANT
- 4 fournisseurs avec fiabilités différentes (~90, ~70, ~55, ~40)
- Prix unitaires entre 10 et 5000 MAD
- Délais fournisseurs entre 3 et 21 jours
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

np.random.seed(42)

# --- 4 Fournisseurs avec profils de fiabilité distincts ---
FOURNISSEURS = {
    "F01": {"nom": "Maroc Acier Premium", "delai_moy": 5, "delai_std": 0.5, "fiabilite": 90},
    "F02": {"nom": "Atlas Composants", "delai_moy": 8, "delai_std": 2.0, "fiabilite": 70},
    "F03": {"nom": "Tanger Pièces Ind.", "delai_moy": 14, "delai_std": 5.0, "fiabilite": 55},
    "F04": {"nom": "Casablanca Import", "delai_moy": 18, "delai_std": 7.0, "fiabilite": 40},
}

# --- Noms réalistes d'articles industriels ---
NOMS_ARTICLES = [
    # Segment A — articles à forte valeur (10)
    "Moteur électrique 5.5kW",
    "Variateur de fréquence 7.5kW",
    "Automate Siemens S7-1200",
    "Roulement à billes SKF 6310",
    "Capteur de pression 0-10bar",
    "Vérin pneumatique DN100",
    "Écran tactile HMI 10 pouces",
    "Servomoteur Schneider 2kW",
    "Réducteur planétaire i=10",
    "Carte mère contrôleur PLC",
    # Segment B — articles à valeur moyenne (15)
    "Courroie trapézoïdale B68",
    "Filtre hydraulique 10µm",
    "Contacteur tripolaire 25A",
    "Thermocouple type K",
    "Relais thermique 10-16A",
    "Électrovanne 3/2 voies",
    "Flexible hydraulique DN12",
    "Interrupteur sectionneur 63A",
    "Joint torique Viton 50mm",
    "Garniture mécanique 35mm",
    "Fusible NH taille 1 100A",
    "Disjoncteur moteur 6-10A",
    "Poulie aluminium Ø150mm",
    "Raccord rapide pneumatique 8mm",
    "Chaîne à rouleaux simple 12B",
    # Segment C — consommables et petites pièces (25)
    "Boulon M10x50 inox A2",
    "Écrou frein M8 zingué",
    "Rondelle Grower M12",
    "Collier de serrage 20-32mm",
    "Graisse lithium EP2 1kg",
    "Huile hydraulique ISO 46 5L",
    "Ruban adhésif isolant 20m",
    "Gaine thermorétractable 10mm",
    "Cosse à sertir 6mm²",
    "Serre-câble plastique 200mm",
    "Rivet aveugle 4x10mm",
    "Goupille fendue 3x30mm",
    "Vis CHC M6x20 DIN 912",
    "Embout de câble 2.5mm²",
    "Presse-étoupe PG11",
    "Domino de connexion 6mm²",
    "Manchon isolant 16mm²",
    "Spray dégrippant 500ml",
    "Chiffon non-tissé (paquet 100)",
    "Marqueur industriel jaune",
    "Papier abrasif P120 feuille",
    "Disque à tronçonner 125mm",
    "Foret HSS Ø8mm",
    "Lame de scie à métaux 300mm",
    "Clé Allen 5mm chromée",
]


def generate_articles() -> pd.DataFrame:
    """Génère les 50 articles avec des données réalistes."""
    articles = []
    today = datetime.now()

    for i, nom in enumerate(NOMS_ARTICLES):
        article_id = f"ART-{i + 1:03d}"

        # --- Déterminer le segment ABC et ajuster les paramètres ---
        if i < 10:
            # Segment A : forte valeur, forte consommation
            prix = np.random.uniform(800, 5000)
            conso = np.random.uniform(5, 25)
            fournisseur_id = np.random.choice(["F01", "F02"])
        elif i < 25:
            # Segment B : valeur moyenne
            prix = np.random.uniform(100, 800)
            conso = np.random.uniform(3, 15)
            fournisseur_id = np.random.choice(["F01", "F02", "F03"])
        else:
            # Segment C : faible valeur, consommables
            prix = np.random.uniform(10, 100)
            conso = np.random.uniform(1, 30)
            fournisseur_id = np.random.choice(["F02", "F03", "F04"])

        # --- Déterminer le segment XYZ (variabilité) ---
        xyz_type = np.random.choice(["X", "Y", "Z"], p=[0.35, 0.40, 0.25])
        if xyz_type == "X":
            cv = np.random.uniform(0.05, 0.18)
        elif xyz_type == "Y":
            cv = np.random.uniform(0.22, 0.45)
        else:
            cv = np.random.uniform(0.55, 1.2)

        ecart_type = conso * cv

        # --- Fournisseur ---
        f = FOURNISSEURS[fournisseur_id]
        delai = f["delai_moy"] + np.random.uniform(-1, 2)
        delai = max(3, min(21, delai))
        delai_std = f["delai_std"] + np.random.uniform(-0.2, 0.5)
        delai_std = max(0.1, delai_std)

        # --- Stock actuel (créer les situations d'alerte) ---
        # Calculer SS et ROP approximatifs pour dimensionner le stock
        from statistics import NormalDist
        z = NormalDist().inv_cdf(0.95)
        ss_approx = z * np.sqrt(delai * ecart_type**2 + conso**2 * delai_std**2)
        rop_approx = conso * delai + ss_approx

        # Créer différents profils de stock
        if i in [1, 3, 7, 12, 18]:
            # 5 articles CRITIQUE : stock < SS
            stock = ss_approx * np.random.uniform(0.1, 0.7)
        elif i in [0, 2, 5, 8, 11, 14, 19, 22, 26, 30]:
            # 10 articles PRÉVENTIF : SS <= stock < ROP
            stock = ss_approx + (rop_approx - ss_approx) * np.random.uniform(0.1, 0.8)
        elif i in [45, 46, 47, 48, 49]:
            # 5 articles DORMANT : très faible consommation
            conso = np.random.uniform(0.001, 0.008)
            ecart_type = conso * 0.5
            stock = np.random.uniform(50, 200)
        else:
            # Articles OK : stock >= ROP
            stock = rop_approx * np.random.uniform(1.1, 2.5)

        stock = max(0, round(stock, 1))

        # --- Taux de possession ---
        taux_possession = np.random.choice([0.15, 0.20, 0.25, 0.30])

        # --- Coût de commande ---
        cout_commande = np.random.uniform(30, 200)

        # --- Dernière livraison ---
        jours_depuis = int(np.random.uniform(5, 60))
        derniere_livraison = today - timedelta(days=jours_depuis)

        # --- Commande en cours ---
        # Articles critiques ont parfois une commande en cours
        if i in [1, 3] and np.random.random() > 0.3:
            qte_commandee = round(conso * 30, 0)
        else:
            qte_commandee = 0

        articles.append({
            "article_id": article_id,
            "article_nom": nom,
            "stock_actuel": round(stock, 1),
            "consommation_moyenne_jour": round(conso, 3),
            "ecart_type_consommation": round(ecart_type, 3),
            "delai_fournisseur_jours": round(delai, 1),
            "delai_ecart_type": round(delai_std, 2),
            "prix_unitaire": round(prix, 2),
            "cout_commande": round(cout_commande, 2),
            "taux_possession": taux_possession,
            "fournisseur_id": fournisseur_id,
            "fournisseur_nom": f["nom"],
            "derniere_livraison_date": derniere_livraison.strftime("%Y-%m-%d"),
            "quantite_commandee_en_cours": qte_commandee,
        })

    return pd.DataFrame(articles)


if __name__ == "__main__":
    df = generate_articles()

    # Sauvegarder en Excel
    output_path = os.path.join(os.path.dirname(__file__), "sample_data.xlsx")
    df.to_excel(output_path, index=False, engine="openpyxl")
    print(f"[OK] Fichier sample_data.xlsx genere avec {len(df)} articles.")
    print(f"   Chemin : {output_path}")

    # Afficher un resume
    print(f"\n[Resume] :")
    print(f"   Prix min : {df['prix_unitaire'].min():.2f} MAD")
    print(f"   Prix max : {df['prix_unitaire'].max():.2f} MAD")
    print(f"   Fournisseurs : {df['fournisseur_id'].nunique()}")
    print(f"   Delai min : {df['delai_fournisseur_jours'].min():.1f} j")
    print(f"   Delai max : {df['delai_fournisseur_jours'].max():.1f} j")
