# Lire et évaluer les analyses

Le tableau de bord sert à explorer les commandes de démonstration. Les chiffres décrivent la sélection affichée ; les prévisions et les segments demandent une évaluation avant interprétation.

## Actualiser les données

Après une commande, cliquer sur **Actualiser les données**. Le bandeau indique la date et l’heure de la dernière lecture réussie, en UTC, qui correspond à l’heure d’Abidjan.

Les ventes et le catalogue sont lus dans une même transaction MySQL avec isolation `REPEATABLE READ`. Une nouvelle version n’est publiée qu’après les deux lectures et la préparation des données. Si une lecture échoue, la version précédente et ses filtres restent affichés ; le bandeau propose de réessayer.

Une période couvrant tout l’historique se prolonge lorsqu’une nouvelle date apparaît. Une période personnalisée est conservée. Les choix de catégorie, ville et paiement restent en place. Les stocks affichés sont ceux de l’actualisation, pour les catégories sélectionnées ; ils ne correspondent pas à un stock historique de la période de vente.

Les vues, exports et calculs utilisent l’identifiant de la version affichée. Les huit dernières versions sont conservées dans la mémoire du serveur. Une version expirée demande une actualisation ; une nouvelle ouverture du tableau de bord charge la version la plus récente. Le serveur local utilise un seul processus ; ce cache ne constitue pas une architecture de déploiement distribué.

## Lire les classements

Une commande est comptée une fois par produit, même si plusieurs lignes portent sa référence. Ce classement ne mesure donc ni le nombre d’unités vendues, ni le chiffre d’affaires.

- **Les plus commandés** : dix références ayant au moins une commande dans la sélection.
- **Les moins commandés, zéro inclus** : dix références du catalogue actuel des catégories choisies, y compris celles sans commande dans la période, la ville ou le mode de paiement sélectionnés.

Le catalogue ne contient pas de date d’introduction des références. On ne déduit pas qu’un produit sans commande était déjà disponible durant une ancienne période. Les égalités sont départagées par identifiant pour garder un ordre reproductible. Les barres horizontales conservent les noms complets sur plusieurs lignes ; un repère et le texte « 0 commande » rendent les valeurs nulles visibles.

[Voir les classements sur les données de démonstration](media/classements.png).

## Dates, nombres et exports

Les colonnes portent des intitulés lisibles : **Date de commande**, **Prix unitaire (FCFA)**, **Ventes hors livraison (FCFA)**. Les dates suivent le format `JJ/MM/AAAA` et les décimales utilisent la virgule. Le tri des dates repose sur les valeurs chronologiques d’origine, sans trier les chaînes françaises par ordre alphabétique.

Le CSV dédié reprend les filtres et la version affichée : séparateur point-virgule, virgule décimale et UTF-8 avec marqueur BOM pour faciliter l’ouverture dans un tableur. Un prix historique inconnu reste vide dans le fichier, et est signalé dans la table. Aucun prix absent n’est remplacé par le tarif actuel.

## Évaluer les prévisions

Les ventes sont agrégées par jour. Entre la première et la dernière vente sélectionnées, un jour sans commande est compté à zéro. Cette hypothèse suppose que l’absence de commande ne provient pas d’une panne de collecte. Aucune journée postérieure à la dernière vente n’est ajoutée artificiellement. Une sélection contenant un prix inconnu ne peut pas être utilisée pour les prévisions.

Pour chaque horizon, le modèle est évalué sur **trois fenêtres chronologiques distinctes, sans chevauchement**, ayant exactement la durée demandée. L’apprentissage s’élargit à chaque fenêtre. Dans une fenêtre, les ventes futures observées ne servent jamais à construire les retards : la prévision est récursive.

| Horizon | Historique initial minimum | Trois fenêtres de validation | Historique total minimum |
| :--- | ---: | ---: | ---: |
| 7 jours | 45 jours | 3 × 7 jours | 66 jours |
| 30 jours | 60 jours | 3 × 30 jours | 150 jours |
| 90 jours | 180 jours | 3 × 90 jours | 450 jours |

Ces minimums sont une **règle du projet** : au moins 45 jours au départ, au moins deux fois l’horizon pour l’apprentissage initial, puis trois fenêtres complètes. Les 30 premiers jours servent aux variables retardées. Ces minimums rendent l’évaluation possible ; ils ne garantissent pas la qualité d’une prévision. Un horizon insuffisamment documenté est désactivé dans la liste et refusé également côté serveur.

Chaque fenêtre compare XGBoost à deux références : répéter la vente du dernier jour connu, et répéter la dernière semaine connue. La table indique l’erreur absolue moyenne quotidienne en FCFA. Elle permet de voir si un bon résultat moyen masque une mauvaise période. Le nombre de fenêtres où le modèle améliore strictement la référence hebdomadaire est affiché, sans compter une égalité comme une amélioration.

Après l’évaluation, un modèle final est réentraîné sur tout l’historique sélectionné. Le graphique affiche sa prévision et la référence hebdomadaire. Il ne présente pas de bande historique comme un intervalle de confiance. Les horizons longs restent exploratoires : la demande, les stocks, les promotions et les comportements peuvent évoluer.

Sur les commandes créées par `generer-commandes`, tirées au hasard, le modèle ne fait pas mieux que la répétition de la dernière semaine : ces ventes n’ont aucune régularité à apprendre. L’écran le signale, ce qui montre que l’évaluation ne favorise pas le modèle. Avec environ 265 jours d’historique, l’horizon de 90 jours, qui en demande 450, est désactivé.

[Voir l’écran de prévision et ses trois périodes de validation](media/previsions.png).

La démarche respecte l’ordre temporel décrit dans la [documentation scikit-learn sur la validation des séries](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html). Les fenêtres du projet sont calculées explicitement pour correspondre aux horizons proposés.

## Évaluer les segments clients

Les commandes dont tous les prix sélectionnés sont connus servent à calculer six indicateurs : montant total, panier moyen, nombre de commandes, récence, fréquence d’achat et quantité moyenne par commande. Une commande comportant plusieurs lignes reste une seule transaction. Les indicateurs sont standardisés avant K-means.

Les diagnostics apparaissent **avant les profils** :

- **Séparation** : coefficient de silhouette dans les six dimensions standardisées. Son calcul porte sur tous les clients jusqu’à 1 000 ; au-delà, un échantillon reproductible de 1 000 inclut chaque segment.
- **Sensibilité à l’initialisation** : cinq ajustements supplémentaires, avec des graines différentes et dix initialisations de K-means chacun.
- **Sensibilité aux clients observés** : cinq sous-échantillons à 80 %, tirés sans remise. La standardisation et K-means sont réestimés dans chaque sous-échantillon, puis tous les clients sont réaffectés selon ce modèle.

Les partitions sont comparées au regroupement initial par l’**indice de Rand ajusté (ARI)** : une permutation des numéros de segment ne change pas la comparaison. La médiane et le minimum des ARI de sous-échantillonnage rendent visibles les résultats défavorables. Le nombre d’essais exploitables est indiqué. Ces calculs mesurent une sensibilité de la partition, pas une performance prédictive sur de futurs clients.

La stabilité n’est pas calculée avec moins de `max(10, 3 × nombre de segments)` clients. Les sous-échantillons sans assez de profils distincts ou produisant un segment vide sont écartés. Moins de trois essais exploitables, ou une silhouette non définie, conduit à **Évaluation insuffisante**.

Les règles de prudence suivantes sont explicites et propres au projet :

| Critère | Résultat signalé comme fragile |
| :--- | :--- |
| Silhouette | Inférieure à 0,25 |
| Plus petit segment | Moins de 3 clients |
| ARI médian selon les graines | Inférieur à 0,80 |
| ARI médian des sous-échantillons | Inférieur à 0,75 |
| ARI minimum des sous-échantillons | Inférieur à 0,60 |

Ces seuils ne sont pas des normes universelles. Un résultat favorable signifie seulement que ces contrôles sont favorables **dans l’échantillon observé**. Les profils restent des descriptions neutres, sans qualification automatique « Premium » ou « Inactif ».

Les indicateurs financiers et de fréquence sont en partie liés : leur redondance influence les distances. Le graphique montant/nombre de commandes est une projection de deux des six dimensions. La stabilité dans le temps, l’utilité commerciale et les causes des différences ne sont pas établies par ces contrôles.

[Voir les diagnostics et les profils sur les données de démonstration](media/segmentation.png).

Définitions de référence : [coefficient de silhouette](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html) et [indice de Rand ajusté](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.adjusted_rand_score.html). La présentation des graphiques utilise la [configuration locale de Plotly](https://plotly.com/javascript/configuration-options/#change-the-default-locale), avec les traductions fournies localement au graphique.

**Abdoulaye KONE - Analyste Statisticien**<br>
Projet collaboratif du groupe 9, ENSEA d’Abidjan. [Équipe et reprise](../README.md#équipe-et-reprise).
