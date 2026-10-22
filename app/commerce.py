"""Paniers, livraison et confirmation atomique des commandes, sans interface."""

from decimal import Decimal
import json
from numbers import Integral
import re

from app.database import connect


def get_products(product_id=None):
    """Prix, stocks et noms du catalogue proviennent de la même source."""
    db = connect()
    try:
        with db.cursor() as cursor:
            query = 'SELECT id, nom, categorie, prix, stock, image FROM Produit'
            cursor.execute(query + (' WHERE id = %s' if product_id is not None else ' ORDER BY id'),
                           (product_id,) if product_id is not None else ())
            return [dict(zip(('id', 'nom', 'categorie', 'prix', 'stock', 'image'), row)) for row in cursor.fetchall()]
    finally:
        db.close()


def get_cart(client_id):
    if client_id is None:
        return []
    db = connect()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT p.nom, pa.nombre_article, p.prix, p.image, p.stock, p.id
                FROM Panier pa JOIN Produit p ON p.id = pa.produit_id
                WHERE pa.client_id = %s ORDER BY p.id
            """, (client_id,))
            return [list(row) for row in cursor.fetchall()]
    finally:
        db.close()


def set_basket_quantity(client_id, product_id, quantity):
    if (isinstance(quantity, bool) or
            not (isinstance(quantity, Integral) or
                 isinstance(quantity, str) and re.fullmatch(r"[0-9]+", quantity))):
        raise ValueError("La quantité doit être un nombre entier positif ou nul.")
    quantity = int(quantity)
    if client_id is None or quantity < 0:
        raise ValueError("Connectez-vous et choisissez une quantité positive ou nulle.")
    db = connect()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT stock FROM Produit WHERE id = %s FOR UPDATE", (product_id,))
            product = cursor.fetchone()
            if product is None or quantity > product[0]:
                raise ValueError("La quantité demandée dépasse le stock disponible.")
            if quantity:
                cursor.execute("""
                    INSERT INTO Panier (client_id, produit_id, nombre_article)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE nombre_article = %s
                """, (client_id, product_id, quantity, quantity))
            else:
                cursor.execute("DELETE FROM Panier WHERE client_id = %s AND produit_id = %s",
                               (client_id, product_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_customer(client_id):
    db = connect()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT nom, prenoms, sexe, date_naissance, email, NULL, numero_tel
                FROM Client WHERE id = %s
            """, (client_id,))
            return cursor.fetchone()
    finally:
        db.close()


def localities():
    db = connect()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT city, quartier, livraison FROM Ville ORDER BY city, quartier")
            return cursor.fetchall()
    finally:
        db.close()


def delivery_rates(rows=None):
    districts, cities = {}, {}
    for city, district, price in localities() if rows is None else rows:
        price = int(price) if price is not None else 6000
        city_key = city.strip().casefold()
        districts[(city_key, district.strip().casefold())] = price
        cities[city_key] = min(cities.get(city_key, price), price)
    return districts, cities


def place_order(client_id, expected_products, *, city, district, residence,
                delivery_mode, relay, displayed_total, payment_mode, payment_details):
    if (not client_id or not expected_products or not city.strip() or not district.strip()
            or delivery_mode not in ("relais", "domicile") or payment_mode not in (1, 2, 3)):
        raise ValueError("Le panier, l’adresse, la livraison ou le paiement sont incomplets.")
    if isinstance(payment_mode, bool) or not isinstance(payment_details, dict):
        raise ValueError("Les informations du paiement simulé sont invalides.")
    payment = {}
    if payment_mode == 1:
        card_end = str(payment_details.get("carte_fin", "")).strip()
        if not re.fullmatch(r"[0-9]{4}", card_end):
            raise ValueError("Indiquez les quatre derniers chiffres de la carte de simulation.")
        payment["carte_fin"] = card_end
    elif payment_mode == 2:
        phone = " ".join(str(payment_details.get("telephone", "")).split())
        if not re.fullmatch(r"\+?[0-9]{1,3} [0-9]{8,10}", phone):
            raise ValueError("Le numéro Wave doit comprendre un indicatif et 8 à 10 chiffres.")
        payment["telephone"] = phone
    db = connect()
    try:
        db.start_transaction()
        with db.cursor() as cursor:
            cursor.execute("""
                SELECT p.nom, pa.nombre_article, p.prix, p.image, p.id, p.stock
                FROM Panier pa JOIN Produit p ON p.id = pa.produit_id
                WHERE pa.client_id = %s ORDER BY p.id FOR UPDATE
            """, (client_id,))
            products = cursor.fetchall()
            expected = {int(p[-1]): (int(p[1]), Decimal(str(p[2]))) for p in expected_products}
            actual = {int(p[4]): (int(p[1]), Decimal(str(p[2]))) for p in products}
            if not products or actual != expected:
                raise ValueError("Le panier ou les prix ont changé. Actualisez le panier.")
            for product in products:
                if int(product[1]) <= 0 or int(product[1]) > int(product[5]):
                    raise ValueError(f"Stock insuffisant pour {product[0]}.")
            if delivery_mode == "relais":
                cursor.execute("SELECT livraison FROM Ville WHERE city = %s AND quartier = %s",
                               (city.strip(), relay.strip()))
                result = cursor.fetchone()
                if result is None:
                    raise ValueError("Le point relais ne correspond pas à la ville choisie.")
                shipping = Decimal(str(result[0] if result[0] is not None else 6000))
            else:
                cursor.execute("SELECT MIN(livraison) FROM Ville WHERE city = %s", (city.strip(),))
                result = cursor.fetchone()
                price = result[0] if result and result[0] is not None else 6000
                shipping = Decimal(int(Decimal(str(price)) * Decimal("1.2")))
            total = (sum(Decimal(str(p[2])) * int(p[1]) for p in products) + shipping).quantize(Decimal("0.01"))
            if total != Decimal(str(displayed_total)).quantize(Decimal("0.01")):
                raise ValueError("Le montant a changé. Vérifiez le récapitulatif avant de confirmer.")
            details = {"statut": "simulation", "montant": str(total), **payment,
                       "commande": {
                           "livraison": {"mode": delivery_mode, "relais": relay.strip() if delivery_mode == 'relais' else None,
                                         "frais": str(shipping)},
                           "articles": [{"produit_id": int(p[4]), "nom": p[0]} for p in products]}}
            cursor.execute("""
                INSERT INTO DetailCommande (Ville_de_residence, commune, residence, montant_total)
                VALUES (%s, %s, %s, %s)
            """, (city.strip(), district.strip(), residence.strip(), total))
            order_id = cursor.lastrowid
            for product in products:
                quantity, product_id = int(product[1]), int(product[4])
                cursor.execute("UPDATE Produit SET stock = stock - %s WHERE id = %s AND stock >= %s",
                               (quantity, product_id, quantity))
                if cursor.rowcount != 1:
                    raise ValueError(f"Stock insuffisant pour {product[0]}.")
                cursor.execute("""
                    INSERT INTO Commande (commande_id, client_id, produit_id, nombre_article, prix_unitaire)
                    VALUES (%s, %s, %s, %s, %s)
                """, (order_id, client_id, product_id, quantity, Decimal(str(product[2]))))
            cursor.execute("""
                INSERT INTO Paiement (commande_id, mode_paiement_id, montant, details_paiement)
                VALUES (%s, %s, %s, %s)
            """, (order_id, payment_mode, total, json.dumps(details)))
            for product in products:
                cursor.execute("DELETE FROM Panier WHERE client_id = %s AND produit_id = %s",
                               (client_id, int(product[4])))
        db.commit()
        return {"id": order_id, "total": total, "payment": details}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _customer_scope():
    """Refuser aussi une ancienne commande incohérente attribuée à plusieurs clients."""
    return """EXISTS (SELECT 1 FROM Commande own WHERE own.commande_id=dc.id AND own.client_id=%s)
        AND NOT EXISTS (SELECT 1 FROM Commande other WHERE other.commande_id=dc.id AND other.client_id<>%s)"""


def _positive_id(value):
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError('Identifiant invalide.')
    return int(value)


def get_customer_orders(client_id, offset=0, limit=12):
    client_id = _positive_id(client_id)
    if isinstance(offset,bool) or not isinstance(offset,Integral) or offset < 0:
        raise ValueError('Page invalide.')
    if isinstance(limit,bool) or not isinstance(limit,Integral) or not 1 <= limit <= 50:
        raise ValueError('Taille de page invalide.')
    db=connect()
    try:
        with db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM DetailCommande dc WHERE '+_customer_scope(),(client_id,client_id))
            total=int(cursor.fetchone()[0])
            cursor.execute('''SELECT dc.id, dc.date_commande, dc.Ville_de_residence, dc.montant_total,
                (SELECT SUM(co.nombre_article) FROM Commande co WHERE co.commande_id=dc.id AND co.client_id=%s)
                FROM DetailCommande dc WHERE '''+_customer_scope()+'''
                ORDER BY dc.date_commande DESC, dc.id DESC LIMIT %s OFFSET %s''',
                (client_id,client_id,client_id,int(limit),int(offset)))
            rows=[dict(zip(('id','date','city','total','quantity'),row)) for row in cursor.fetchall()]
        return {'orders':rows,'total':total,'offset':int(offset),'limit':int(limit)}
    finally:
        db.close()


def get_order_details(client_id, order_id):
    client_id,order_id=_positive_id(client_id),_positive_id(order_id)
    db=connect()
    try:
        with db.cursor() as cursor:
            cursor.execute('''SELECT dc.id,dc.date_commande,dc.Ville_de_residence,dc.commune,
                dc.residence,dc.montant_total FROM DetailCommande dc WHERE dc.id=%s AND '''+_customer_scope(),
                (order_id,client_id,client_id))
            row=cursor.fetchone()
            if row is None:
                return None
            order=dict(zip(('id','date','city','district','residence','total'),row))
            cursor.execute('''SELECT co.produit_id,p.nom,co.nombre_article,co.prix_unitaire
                FROM Commande co JOIN Produit p ON p.id=co.produit_id
                WHERE co.commande_id=%s AND co.client_id=%s ORDER BY co.produit_id''',(order_id,client_id))
            items=[dict(zip(('product_id','name','quantity','unit_price'),row)) for row in cursor.fetchall()]
            cursor.execute('''SELECT mp.type_paiement,pa.details_paiement,pa.date_paiement
                FROM Paiement pa LEFT JOIN ModePaiement mp ON mp.id=pa.mode_paiement_id
                WHERE pa.commande_id=%s ORDER BY pa.id''',(order_id,))
            payments=[];receipt={}
            for mode,payload,stamp in cursor.fetchall():
                try:
                    payload=json.loads(payload) if isinstance(payload,str) else payload
                except (ValueError,TypeError):
                    payload={}
                payload=payload if isinstance(payload,dict) else {}
                payments.append({'mode':mode or 'Non documenté','date':stamp,'simulation':payload.get('statut')=='simulation'})
                if isinstance(payload.get('commande'),dict):receipt=payload['commande']
        names={item.get('produit_id'):item.get('nom') for item in receipt.get('articles',[])
               if isinstance(item,dict) and isinstance(item.get('nom'),str)
               and isinstance(item.get('produit_id'),Integral) and not isinstance(item.get('produit_id'),bool)} if isinstance(receipt.get('articles'),list) else {}
        for item in items:
            item['name']=names.get(item['product_id'],item['name'])
            item['line_total']=Decimal(str(item['unit_price']))*item['quantity'] if item['unit_price'] is not None else None
        delivery=receipt.get('livraison') if isinstance(receipt.get('livraison'),dict) else {}
        try:
            fee=Decimal(str(delivery['frais']))
            if not fee.is_finite() or fee < 0:fee=None
        except (KeyError,ValueError,ArithmeticError):fee=None
        return {'order':order,'items':items,'payments':payments,
                'delivery':{'mode':delivery.get('mode'),'relay':delivery.get('relais'),'fee':fee},
                'subtotal':sum(item['line_total'] for item in items) if all(item['line_total'] is not None for item in items) else None}
    finally:
        db.close()
