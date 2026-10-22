# Installation

Environnement vérifié : Windows, Python 3.12, MySQL Community Server 8.4.

## Dépendances

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-lock.txt
.venv\Scripts\python -m pip check
Copy-Item .env.example .env
```

`requirements.txt` fixe les dépendances directes ; `requirements-lock.txt` conserve l’environnement complet vérifié.

## Base MySQL

1. Créer une base vide et un utilisateur limité à cette base, par exemple depuis un compte administrateur MySQL :

   ```sql
   CREATE DATABASE e_commerce CHARACTER SET utf8mb4;
   CREATE USER 'group9'@'localhost' IDENTIFIED BY 'un-mot-de-passe-solide';
   GRANT SELECT, INSERT, UPDATE, DELETE ON e_commerce.* TO 'group9'@'localhost';
   ```

2. Exécuter `database/schema.sql` dans cette base. Il crée les tables, les vingt produits, les modes de paiement et les tarifs de livraison.
3. Renseigner `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` et `DB_NAME` dans `.env`. Les variables d’environnement du même nom, si elles existent, ont la priorité.

**Base créée avec une ancienne version du projet.** Faire une sauvegarde, examiner `database/correction_coherence.sql`, puis appliquer `database/migration_prix_historiques.sql` si la colonne `Commande.prix_unitaire` n’existe pas. Cette migration peut être relancée sans perte ; les prix des anciennes commandes restent vides.

## Administration

Choisir `GROUP9_ADMIN_USER` et un `GROUP9_ADMIN_PASSWORD` d’au moins douze caractères dans `.env`. Le tableau de bord écoute uniquement `127.0.0.1:8050` et demande ces identifiants.

## Données de démonstration

```powershell
.venv\Scripts\python main.py generer-clients
.venv\Scripts\python main.py generer-commandes
```

Les générateurs écrivent dans la base configurée : les réserver à une base de démonstration. Le second crée des ventes de 2024 sans modifier le stock actuel.

## Sécurité

- Mots de passe clients hachés avec PBKDF2-HMAC-SHA256, sel aléatoire et 600 000 itérations ; un ancien hachage SHA-256 est remplacé à la connexion suivante.
- Session locale signée par HMAC, valable huit heures.
- Tableau de bord protégé par authentification HTTP, ralenti après cinq échecs par minute.
- Requêtes SQL paramétrées ; quantités, prix et montants revérifiés côté service avant toute commande.
- `.env`, `var/` et `.venv/` sont ignorés par Git. Ne jamais publier `.env`, une sauvegarde de la base ou un mot de passe.

Ce prototype est conçu pour un poste local. Une mise en ligne demanderait au minimum HTTPS, une authentification centralisée et une gestion des secrets adaptée.

## Tests

```powershell
.venv\Scripts\python -B -m unittest discover -s tests -v
```

Les tests n’utilisent pas MySQL et ne modifient aucune base.
