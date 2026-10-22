"""Lecture de vrais résultats SQL : isolation client, historique et pagination."""
import json
import sqlite3
import unittest
from decimal import Decimal
from unittest.mock import patch
from app.commerce import get_customer_orders,get_order_details
from app.forms import registration_errors


class Cursor:
    def __init__(self,db):self.cursor=db.cursor()
    def __enter__(self):return self
    def __exit__(self,*args):self.cursor.close()
    def execute(self,query,params=()):self.cursor.execute(query.replace('%s','?'),params)
    def fetchone(self):return self.cursor.fetchone()
    def fetchall(self):return self.cursor.fetchall()


class Database:
    def __init__(self,db):self.db=db
    def cursor(self):return Cursor(self.db)
    def close(self):pass


class OrderHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.executescript('''
          CREATE TABLE Produit(id,nom);
          CREATE TABLE DetailCommande(id,date_commande,Ville_de_residence,commune,residence,montant_total);
          CREATE TABLE Commande(commande_id,client_id,produit_id,nombre_article,prix_unitaire);
          CREATE TABLE ModePaiement(id,type_paiement);
          CREATE TABLE Paiement(id,commande_id,mode_paiement_id,details_paiement,date_paiement);
          INSERT INTO Produit VALUES(1,'Nom actuel modifié');
          INSERT INTO DetailCommande VALUES(1,'2024-01-01 10:00','Abidjan','Cocody','Rue A',2200);
          INSERT INTO DetailCommande VALUES(2,'2024-01-01 10:00','Bouaké','Centre','Adresse privée autre client',900);
          INSERT INTO DetailCommande VALUES(3,'2024-01-01 10:00','Abidjan','Plateau','',NULL);
          INSERT INTO DetailCommande VALUES(4,'2024-01-01 10:00','Abidjan','Incohérent','Ne pas exposer',500);
          INSERT INTO Commande VALUES(1,7,1,2,100),(2,8,1,1,900),(3,7,1,1,NULL),(4,7,1,1,100),(4,8,1,1,400);
          INSERT INTO ModePaiement VALUES(1,'Wave');
        ''')
        payload=json.dumps({'statut':'simulation','commande':{'livraison':{'mode':'relais','relais':'Cocody','frais':'2000'},'articles':[{'produit_id':1,'nom':'Nom au moment de l’achat'}]}})
        self.db.executemany('INSERT INTO Paiement VALUES(?,?,?,?,?)',[(1,1,1,payload,'2024-01-01'),(2,1,1,payload,'2024-01-01')])
        self.connection=patch('app.commerce.connect',side_effect=lambda:Database(self.db))
        self.connection.start();self.addCleanup(self.connection.stop);self.addCleanup(self.db.close)

    def test_only_own_orders_and_no_mixed_customer_order(self):
        result=get_customer_orders(7)
        self.assertEqual(result['total'],2)
        self.assertEqual([x['id'] for x in result['orders']],[3,1])
        self.assertEqual([x['id'] for x in get_customer_orders(8)['orders']],[2])

    def test_other_customer_cannot_read_address_or_items(self):
        self.assertIsNone(get_order_details(7,2))
        self.assertIsNone(get_order_details(8,1))
        self.assertIsNone(get_order_details(7,4))

    def test_historical_name_price_quantity_and_delivery_survive_catalogue_change(self):
        result=get_order_details(7,1)
        self.assertEqual(result['items'][0]['name'],'Nom au moment de l’achat')
        self.assertEqual(result['items'][0]['unit_price'],100)
        self.assertEqual(result['subtotal'],Decimal('200'))
        self.assertEqual(result['delivery'],{'mode':'relais','relay':'Cocody','fee':Decimal('2000')})
        self.assertEqual(result['order']['total'],2200)

    def test_duplicate_payments_do_not_multiply_items_or_orders(self):
        self.assertEqual(len(get_order_details(7,1)['items']),1)
        self.assertEqual(get_customer_orders(7)['orders'][1]['quantity'],2)

    def test_unknown_old_price_and_delivery_remain_unknown(self):
        result=get_order_details(7,3)
        self.assertIsNone(result['subtotal'])
        self.assertIsNone(result['items'][0]['line_total'])
        self.assertIsNone(result['delivery']['fee'])
        self.assertIsNone(result['order']['total'])

    def test_pages_have_no_duplicates_when_dates_are_equal(self):
        first=get_customer_orders(7,limit=1,offset=0)
        second=get_customer_orders(7,limit=1,offset=1)
        self.assertEqual(first['orders'][0]['id'],3)
        self.assertEqual(second['orders'][0]['id'],1)
        self.assertEqual(get_customer_orders(7,offset=20)['orders'],[])

    def test_corrupt_json_does_not_prevent_reading_historical_prices(self):
        for payload in ['not JSON',json.dumps({'commande':{'articles':[{'produit_id':[], 'nom':'Invalide'}]}})]:
            with self.subTest(payload=payload):
                self.db.execute('UPDATE Paiement SET details_paiement=?',(payload,))
                result=get_order_details(7,1)
                self.assertEqual(result['subtotal'],Decimal('200'))
                self.assertEqual(result['items'][0]['name'],'Nom actuel modifié')
                self.assertIsNone(result['delivery']['fee'])

    def test_invalid_identifiers_and_pagination_never_reach_database(self):
        with patch('app.commerce.connect') as connection:
            for value in (None,True,0,-1,'7 OR 1=1'):
                with self.assertRaises(ValueError):get_order_details(value,1)
                with self.assertRaises(ValueError):get_order_details(7,value)
            for options in ({'offset':-1},{'limit':0},{'limit':51},{'offset':True}):
                with self.assertRaises(ValueError):get_customer_orders(7,**options)
            connection.assert_not_called()

    def test_new_customer_has_an_empty_history(self):
        self.assertEqual(get_customer_orders(999)['total'],0)


class RegistrationValidationTests(unittest.TestCase):
    def data(self):
        return dict(nom='Démo',prenoms='Client',email='client@example.test',birth='1990-01-01',
                    password='demonstration-2026',confirmation='demonstration-2026',prefix='+225',phone='0100000000')

    def test_valid_form_has_no_errors(self):self.assertEqual(registration_errors(self.data()),{})

    def test_errors_are_associated_with_fields(self):
        data=self.data();data.update(email='incorrect',birth='2099-01-01',phone='abc',confirmation='autre')
        self.assertEqual(set(registration_errors(data)),{'email','birth','phone','confirmation'})

    def test_spaces_and_unicode_digits_are_not_accepted_as_phone_numbers(self):
        for value in ('０１００００００００','01 00 00 00 00','123'):
            data=self.data();data['phone']=value
            self.assertIn('phone',registration_errors(data))
