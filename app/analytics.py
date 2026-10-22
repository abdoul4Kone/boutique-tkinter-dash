"""Instantanés cohérents, présentation française et diagnostics des analyses."""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
from numbers import Integral

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler


FRENCH_PLOTLY_LOCALE = {
    'dictionary': {
        'Download plot as a PNG': 'Télécharger le graphique en PNG',
        'Download plot as a png': 'Télécharger le graphique en PNG',
        'Zoom': 'Zoomer', 'Pan': 'Déplacer', 'Box Select': 'Sélection rectangulaire',
        'Lasso Select': 'Sélection au lasso', 'Zoom in': 'Agrandir', 'Zoom out': 'Réduire',
        'Autoscale': 'Échelle automatique', 'Reset axes': 'Réinitialiser les axes',
        'Toggle Spike Lines': 'Afficher les repères',
        'Show closest data on hover': 'Afficher le point le plus proche',
        'Compare data on hover': 'Comparer les données au survol',
        'Double-click to zoom back out': 'Double-cliquer pour rétablir le zoom',
        'Click to enter Plot title': 'Saisir le titre du graphique',
        'Click to enter X axis title': 'Saisir le titre de l’axe horizontal',
        'Click to enter Y axis title': 'Saisir le titre de l’axe vertical',
        'Produced with Plotly.js': 'Réalisé avec Plotly.js'
    },
    'format': {
        'days': ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi'],
        'shortDays': ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.'],
        'months': ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août',
                   'septembre', 'octobre', 'novembre', 'décembre'],
        'shortMonths': ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août',
                        'sept.', 'oct.', 'nov.', 'déc.'],
        'date': '%d/%m/%Y', 'decimal': ',', 'thousands': ' ', 'grouping': [3], 'time': '%H:%M:%S'
    }
}


def french_number(value, decimals=0):
    if value is None or pd.isna(value):
        return 'Non documenté'
    return f'{float(value):,.{decimals}f}'.replace(',', '\u202f').replace('.', ',')


def french_date(value, clock=False):
    if value is None or pd.isna(value):
        return 'Non documentée'
    return pd.Timestamp(value).strftime('%d/%m/%Y à %H:%M:%S' if clock else '%d/%m/%Y')


@dataclass(frozen=True)
class Snapshot:
    version: str
    sales: pd.DataFrame
    products: pd.DataFrame
    loaded_at: datetime


class DashboardSnapshots:
    """Publier ensemble les ventes et le catalogue ; conserver l'ancien en cas d'échec."""
    def __init__(self, engine, sales_query, keep=8):
        self.engine, self.sales_query, self.keep = engine, sales_query, keep
        self.lock = RLock()
        self.versions = OrderedDict()

    def refresh(self):
        # Sérialiser les actualisations et lire un même état transactionnel de MySQL.
        with self.lock:
            with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
                with connection.begin():
                    sales = pd.read_sql(self.sales_query, connection)
                    products = pd.read_sql('SELECT id, nom, stock, categorie FROM Produit ORDER BY id', connection)
            sales['date_commande'] = pd.to_datetime(sales['date_commande'])
            for column in ('prix', 'nombre_article', 'stock', 'lat', 'lng'):
                sales[column] = pd.to_numeric(sales[column], errors='coerce')
            sales['prix_historique_connu'] = sales['prix'].notna()
            sales['montant'] = (sales['nombre_article'] * sales['prix']).round(2)
            products['stock'] = pd.to_numeric(products['stock'], errors='coerce')
            snapshot = Snapshot(uuid4().hex, sales, products, datetime.now(timezone.utc))
            self.versions[snapshot.version] = snapshot
            while len(self.versions) > self.keep:
                self.versions.popitem(last=False)
            return snapshot

    def get(self, version=None):
        with self.lock:
            if version is None and self.versions:
                return next(reversed(self.versions.values()))
            if version not in self.versions:
                raise ValueError('Cette version des données a expiré. Cliquez sur Actualiser les données.')
            return self.versions[version]


def product_performance(sales, products, categories=None):
    """Le catalogue actuel définit l'univers, les filtres de vente définissent le comptage."""
    catalog = products.loc[products['categorie'].isin(categories)].copy() if categories else products.copy()
    counts = sales.groupby('produit_id')['detailcommande_id'].nunique().rename('nombre_commandes')
    performance = catalog.rename(columns={'id': 'produit_id', 'nom': 'produit_nom'}).merge(
        counts, how='left', left_on='produit_id', right_index=True, validate='one_to_one')
    performance['nombre_commandes'] = performance['nombre_commandes'].fillna(0).astype(int)
    return performance.sort_values(['nombre_commandes', 'produit_id'], kind='stable').reset_index(drop=True)


def required_history(horizon):
    if isinstance(horizon, bool) or not isinstance(horizon, Integral) or horizon not in (7, 30, 90):
        raise ValueError('Choisissez un horizon de 7, 30 ou 90 jours.')
    return max(45, 2 * horizon) + 3 * horizon


def validation_windows(length, horizon):
    minimum = required_history(horizon)
    if length < minimum:
        raise ValueError(f'Horizon de {horizon} jours : au moins {minimum} jours d’historique sont nécessaires '
                         'pour trois périodes de validation complètes.')
    return [(length - step * horizon, length - (step - 1) * horizon) for step in (3, 2, 1)]


def weekly_reference(history, horizon):
    values = np.asarray(history, dtype=float)
    if len(values) < 7:
        raise ValueError('Sept jours sont nécessaires pour la référence hebdomadaire.')
    return np.tile(values[-7:], int(np.ceil(horizon / 7)))[:horizon]


CLUSTER_FEATURES = ['total_amount', 'avg_amount', 'nb_transactions',
                    'recency', 'purchase_frequency', 'avg_items_per_order']


def segmentation_diagnostics(customers, labels, n_clusters):
    """Séparation dans les six dimensions ; sensibilité aux graines et aux sous-échantillons."""
    values = customers[CLUSTER_FEATURES].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError('Les indicateurs clients contiennent des valeurs invalides.')
    labels = np.asarray(labels)
    n = len(values)
    scaled = StandardScaler().fit_transform(values)
    sizes = np.bincount(labels.astype(int), minlength=n_clusters)
    # Échantillon reproductible contenant chaque segment, coût quadratique plafonné.
    rng = np.random.default_rng(2026)
    sample = np.arange(n)
    if n > 1000:
        mandatory = np.array([np.flatnonzero(labels == k)[0] for k in np.unique(labels)])
        rest = np.setdiff1d(sample, mandatory)
        sample = np.r_[mandatory, rng.choice(rest, 1000 - len(mandatory), replace=False)]
    silhouette = None
    if 2 <= len(np.unique(labels[sample])) < len(sample):
        silhouette = float(silhouette_score(scaled[sample], labels[sample]))
    seeds, resamples = [], []
    if n >= max(10, 3 * n_clusters):
        for seed in (11, 23, 37, 51, 71):
            alternative = KMeans(n_clusters=n_clusters, n_init=10, random_state=seed).fit_predict(scaled)
            seeds.append(float(adjusted_rand_score(labels, alternative)))
            indices = rng.choice(n, max(n_clusters + 1, int(.8 * n)), replace=False)
            if len(np.unique(values[indices], axis=0)) < n_clusters:
                continue
            scaler = StandardScaler().fit(values[indices])
            sample_scaled = scaler.transform(values[indices])
            model = KMeans(n_clusters=n_clusters, n_init=10, random_state=seed).fit(sample_scaled)
            if len(np.unique(model.labels_)) != n_clusters:
                continue
            assigned = model.predict(scaler.transform(values))
            if len(np.unique(assigned)) == n_clusters:
                resamples.append(float(adjusted_rand_score(labels, assigned)))
    result = dict(silhouette=silhouette, silhouette_clients=len(sample), clients=n,
                  sizes=sizes.tolist(), seed_median=float(np.median(seeds)) if seeds else None,
                  sample_median=float(np.median(resamples)) if resamples else None,
                  sample_min=float(np.min(resamples)) if resamples else None,
                  successful_resamples=len(resamples), attempted_resamples=5)
    if silhouette is None or len(resamples) < 3:
        result['status'] = 'Évaluation insuffisante'
    elif (silhouette < .25 or min(sizes) < 3 or result['seed_median'] < .8
          or result['sample_median'] < .75 or result['sample_min'] < .6):
        result['status'] = 'Groupes fragiles : interprétation prudente'
    else:
        result['status'] = 'Résultats favorables dans cet échantillon'
    return result


COLUMN_LABELS = {
    'client_id': 'Référence client', 'nom': 'Nom', 'prenoms': 'Prénoms', 'sexe': 'Sexe',
    'detailcommande_id': 'Référence commande', 'date_commande': 'Date de commande',
    'ville_residence': 'Ville', 'produit_id': 'Référence produit', 'produit_nom': 'Produit',
    'categorie': 'Catégorie', 'stock': 'Stock actuel', 'mode_paiement_id': 'Référence du paiement',
    'type_paiement': 'Mode de paiement', 'nombre_article': 'Quantité', 'prix': 'Prix unitaire (FCFA)',
    'lat': 'Latitude', 'lng': 'Longitude', 'prix_historique_connu': 'Prix historique connu',
    'montant': 'Ventes hors livraison (FCFA)'
}


def french_export(data):
    result = data.copy()
    for column in ('prix', 'montant'):
        if column in result:
            result[column] = pd.to_numeric(result[column], errors='coerce').round(2)
    result['date_commande'] = result['date_commande'].map(lambda value: french_date(value, True))
    result['prix_historique_connu'] = result['prix_historique_connu'].map({True: 'Oui', False: 'Non'})
    return result.rename(columns=COLUMN_LABELS)
