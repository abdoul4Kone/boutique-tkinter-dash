"""Générateur de 560 commandes fictives de 2024 pour une base de démonstration.

Ces ventes passées ne modifient pas le stock actuel : la boutique reste utilisable après la génération.
"""

import random
from datetime import datetime, timedelta
from app.database import connect, DatabaseError


def main(product_id=None, return_to="accueil"):
    def generate_and_insert_orders():
        connection = None
        inserted = 0
        try:
            # Connexion à la base de données
            connection = connect()
            cursor = connection.cursor()

            # Récupérer les IDs des clients
            cursor.execute("SELECT id FROM Client")
            client_ids = [row[0] for row in cursor.fetchall()]

            # Récupérer les produits (IDs, stocks et prix)
            cursor.execute("SELECT id, stock, prix FROM Produit")
            products = cursor.fetchall()

            # Récupérer les modes de paiement (IDs)
            cursor.execute("SELECT id FROM ModePaiement")
            payment_mode_ids = [row[0] for row in cursor.fetchall()]

            # Récupérer les villes et leurs informations
            cursor.execute("SELECT city, quartier FROM Ville")
            locations = cursor.fetchall()

            # Vérifications initiales
            if not client_ids or not products or not payment_mode_ids or not locations:
                print("La base de données ne contient pas assez de clients, produits, modes de paiement ou villes.")
                return

            # Générer 560 commandes
            for _ in range(560):
                client_id = random.choice(client_ids)
                product_id, _, price = random.choice(products)
                quantity = random.randint(1, 5)
                total_price = quantity * price

                # Générer une date de commande entre le 10 avril et le 31 décembre 2024
                start_date = datetime(2024, 4, 10)
                end_date = datetime(2024, 12, 31)
                date_commande = start_date + timedelta(days=random.randint(0, (end_date - start_date).days))

                # Choisir une localisation aléatoire
                ville_residence, commune = random.choice(locations)
                residence = f"{commune} Residence {random.randint(1, 100)}"

                # Insérer dans DetailCommande
                cursor.execute(
                    """
                    INSERT INTO DetailCommande (date_commande, Ville_de_residence, commune, residence, montant_total)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (date_commande, ville_residence, commune, residence, total_price)
                )
                detail_commande_id = cursor.lastrowid

                # Insérer dans Commande
                cursor.execute(
                    """
                    INSERT INTO Commande (commande_id, client_id, produit_id, nombre_article, prix_unitaire)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (detail_commande_id, client_id, product_id, quantity, price)
                )

                # Insérer dans Paiement
                payment_mode_id = random.choice(payment_mode_ids)
                cursor.execute(
                    """
                    INSERT INTO Paiement (commande_id, mode_paiement_id, montant)
                    VALUES (%s, %s, %s)
                    """,
                    (detail_commande_id, payment_mode_id, total_price)
                )

                inserted += 1

            # Valider les changements
            connection.commit()
            print(f"{inserted} commandes ont été générées et insérées avec succès.")

        except DatabaseError as err:
            print(f"Erreur : {err}")
            if connection is not None:
                connection.rollback()

        finally:
            if connection is not None and connection.is_connected():
                cursor.close()
                connection.close()

    generate_and_insert_orders()

