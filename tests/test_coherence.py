"""Régressions métier sans interface graphique ni serveur MySQL.

Les traitements partagés sont importés directement. Les classes d'écran sont
chargées seules pour tester leurs actions avec des widgets factices.
"""

import ast
import copy
from decimal import Decimal
import hmac
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def definitions(filename, names, **namespace):
    path = ROOT / filename
    namespace.setdefault("__file__", str(path))
    namespace.setdefault("Path", Path)
    namespace.setdefault("sys", sys)
    from app.runtime import run_task
    namespace.setdefault('PageFrame', object)
    namespace.setdefault('run_task', run_task)
    namespace.setdefault('initial_data', None)
    namespace.setdefault('re', __import__('re'))
    from app.views.components import field_error,form_notice
    namespace.setdefault('field_error',field_error)
    namespace.setdefault('form_notice',form_notice)
    namespace.setdefault('tk', SimpleNamespace(Tk=object))
    namespace.setdefault('user_id', 7)
    namespace.setdefault('current_user_id', lambda: namespace.get('user_id', 7))
    namespace.setdefault("SESSION_FILE", ROOT / "var/session.json")
    namespace.setdefault("DatabaseError", DatabaseError)
    namespace.setdefault("open_page", Mock())
    from app.commerce import place_order
    from app.config import admin_credentials
    namespace.setdefault("place_order", place_order)
    namespace.setdefault("admin_credentials", admin_credentials)
    if filename=='app/admin/dashboard.py':
        from app import analytics
        from dash import html,dash_table
        namespace.setdefault('html',html);namespace.setdefault('dash_table',dash_table)
        for key in ('french_number','french_date','french_export','COLUMN_LABELS','required_history',
                    'validation_windows','weekly_reference','segmentation_diagnostics','product_performance'):
            namespace.setdefault(key,getattr(analytics,key))
        namespace.setdefault('sales_for',lambda version=None:namespace['df'])
        names=list(dict.fromkeys([*names,'chart','message_figure']))
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    nodes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            node.decorator_list = []
            nodes.append(node)
    missing = set(names) - {node.name for node in nodes}
    if missing:
        raise AssertionError(f"Définitions absentes : {missing}")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


def field(value):
    return SimpleNamespace(get=lambda: value)


class DatabaseError(Exception):
    pass


class MemoryDatabase:
    """Double qui conserve ou annule les mutations de toute la transaction."""

    def __init__(self, failure=None):
        self.state = {"stock": {1: 5, 2: 4}, "orders": [], "lines": [],
                      "payments": [], "cart": {1: 1, 2: 2}}
        self.prices = {1: Decimal("100"), 2: Decimal("50")}
        self.failure = failure
        self.snapshot = None
        self.commits = 0
        self.started = 0
        self.closed = False

    def cursor(self):
        return MemoryCursor(self)

    def start_transaction(self):
        self.snapshot = copy.deepcopy(self.state)
        self.started += 1

    def rollback(self):
        if self.snapshot is not None:
            self.state = self.snapshot
            self.snapshot = None

    def commit(self):
        self.commits += 1
        self.snapshot = None

    def close(self):
        self.closed = True


class MemoryCursor:
    def __init__(self, db):
        self.db = db
        self.lastrowid = 1
        self.rowcount = 0
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=()):
        sql = " ".join(query.upper().split())
        if sql.startswith("SELECT P.NOM"):
            self.result = [(f"Article {pid}", qty, self.db.prices[pid], "hp.png", pid,
                            self.db.state["stock"][pid])
                           for pid, qty in self.db.state["cart"].items()]
        elif sql.startswith("SELECT STOCK FROM PRODUIT"):
            self.result = [(self.db.state["stock"][params[0]],)]
        elif sql.startswith("INSERT INTO PANIER"):
            self.db.state["cart"][params[1]] = params[2]
        elif sql.startswith("SELECT MIN(LIVRAISON)"):
            self.result = [(1000,)]
        elif sql.startswith("SELECT LIVRAISON"):
            self.result = [] if self.db.failure == "relais" else [(1000,)]
        elif sql.startswith("INSERT INTO DETAILCOMMANDE"):
            self.db.state["orders"].append(params)
        elif sql.startswith("UPDATE PRODUIT"):
            quantity, pid, minimum = params
            self.rowcount = int(self.db.state["stock"][pid] >= minimum)
            if self.db.failure == "concurrent_stock":
                self.rowcount = 0
            if self.rowcount:
                self.db.state["stock"][pid] -= quantity
        elif sql.startswith("INSERT INTO COMMANDE"):
            self.db.state["lines"].append(params)
        elif sql.startswith("INSERT INTO PAIEMENT"):
            if self.db.failure == "payment":
                raise DatabaseError("Échec simulé de l'écriture du paiement")
            self.db.state["payments"].append(params)
        elif sql.startswith("DELETE FROM PANIER"):
            self.db.state["cart"].pop(params[1], None)
        else:
            raise AssertionError(f"SQL inattendu : {query}")

    def fetchall(self):
        return self.result

    def fetchone(self):
        return self.result[0] if self.result else None


class SessionTests(unittest.TestCase):
    def setUp(self):
        from app.accounts import User, SessionManager
        self.ns = dict(User=User, SessionManager=SessionManager)

    def test_new_session_round_trip(self):
        cls = self.ns["User"]
        user = cls(id=7, nom="Koné", numero_tel="0100000000")
        self.assertEqual(cls.from_dict(user.to_dict()).numero_tel, "0100000000")
        self.assertNotIn("tel", user.to_dict())

    def test_legacy_session_remains_readable(self):
        self.assertEqual(self.ns["User"].from_dict({"id": 7, "tel": "0700000000"}).numero_tel,
                         "0700000000")

    def test_corrupt_session_cannot_leave_authentication_enabled(self):
        with tempfile.TemporaryDirectory() as folder:
            session = object.__new__(self.ns["SessionManager"])
            session.SESSION_FILE = Path(folder) / "session.json"
            session.SESSION_FILE.write_text("[]", encoding="utf-8")
            session.user = object()
            session.is_authenticated = True
            with patch("builtins.print"):
                session.load_session()
            self.assertFalse(session.is_authenticated)
            self.assertIsNone(session.user)

    def test_login_uses_shared_connection_and_persists_canonical_session(self):
        from app.accounts import SessionManager
        db = Mock()
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (7, "Koné", "Test", "test@example.com", "0100000000", hashlib.sha256(b'password-test').hexdigest())
        db.cursor.return_value = cursor
        with tempfile.TemporaryDirectory() as folder:
            session = object.__new__(SessionManager)
            session.SESSION_FILE = Path(folder) / "state/session.json"
            with patch("app.accounts.connect", return_value=db) as connect:
                self.assertTrue(session.login("test@example.com", "password-test"))
            connect.assert_called_once()
            saved = json.loads(session.SESSION_FILE.read_text(encoding="utf-8"))
            self.assertEqual(saved["user"]["numero_tel"], "0100000000")
            session.load_session()
            self.assertEqual(session.user.id, 7)
        db.close.assert_called_once()


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        # Éviter le constructeur graphique, tout en exerçant les vraies méthodes.
        self.db = MemoryDatabase()
        connection = patch("app.commerce.connect", return_value=self.db)
        connection.start()
        self.addCleanup(connection.stop)
        self.messages = Mock()
        self.ns = definitions("app/views/checkout.py", ["Commander"],
                              customtkinter=SimpleNamespace(CTk=object), conn=self.db,
                              user_id=7, Decimal=Decimal, json=json,
                              messagebox=self.messages, call=Mock(),
                              mysql=SimpleNamespace(connector=SimpleNamespace(Error=DatabaseError)))
        self.order = object.__new__(self.ns["Commander"])
        for name, value in {"entry_ville": "Abidjan", "entry_quartier": "Cocody",
                            "entry_complement": "", "modeLivraison_var": "domicile",
                            "selectRelais": "Cocody", "numeroCarte": "4111111111111111",
                            "cvvCarte": "123", "moisCarte": "12", "anneeCarte": "2030",
                            "entry_indicatif": "+225", "numeroWave": "0100000000"}.items():
            setattr(self.order, name, field(value))
        self.order.selected_mode = 3
        self.order.produits = [("Article 1", 1, Decimal("100"), "hp.png", 1),
                               ("Article 2", 2, Decimal("50"), "hp.png", 2)]
        self.order.Montant = Decimal("1400")
        self.order.destroy = Mock()

    def test_success_commits_all_operations_once(self):
        self.assertTrue(self.order.valider())
        self.assertEqual(self.db.commits, 1)
        self.assertEqual(self.db.state["stock"], {1: 4, 2: 2})
        self.assertEqual(len(self.db.state["orders"]), 1)
        self.assertEqual(len(self.db.state["lines"]), 2)
        self.assertEqual(len(self.db.state["payments"]), 1)
        self.assertFalse(self.db.state["cart"])

    def test_payment_failure_rolls_back_every_mutation(self):
        self.db.failure = "payment"
        original = copy.deepcopy(self.db.state)
        self.assertFalse(self.order.valider())
        self.assertEqual(self.db.state, original)
        self.assertEqual(self.db.commits, 0)
        self.order.destroy.assert_not_called()

    def test_stock_changed_during_write_rolls_back_order(self):
        self.db.failure = "concurrent_stock"
        original = copy.deepcopy(self.db.state)
        self.assertFalse(self.order.valider())
        self.assertEqual(self.db.state, original)

    def test_insufficient_stock_preserves_cart(self):
        self.db.state["stock"][2] = 1
        original = copy.deepcopy(self.db.state)
        self.assertFalse(self.order.valider())
        self.assertEqual(self.db.state, original)

    def test_changed_price_requires_new_confirmation(self):
        self.db.prices[1] = Decimal("150")
        self.assertFalse(self.order.valider())
        self.assertEqual(self.db.commits, 0)

    def test_changed_delivery_total_is_rejected(self):
        self.order.Montant = Decimal("1200")
        self.assertFalse(self.order.valider())
        self.assertFalse(self.db.state["orders"])

    def test_no_payment_choice_cannot_start_transaction(self):
        self.order.selected_mode = None
        self.assertFalse(self.order.valider())
        self.assertEqual(self.db.started, 0)

    def test_empty_card_cannot_be_overridden_by_wave_validation(self):
        self.order.selected_mode = 1
        for value in ['', '4111111111111111', 'abc4', '123']:
            self.order.numeroCarte = field(value)
            self.assertFalse(self.order.valider())
        self.assertEqual(self.db.started, 0)

    def test_payment_data_is_read_on_confirmation_and_minimized(self):
        self.order.selected_mode = 1
        self.order.numeroCarte = field('4444')
        self.assertTrue(self.order.valider())
        details = json.loads(self.db.state["payments"][0][3])
        self.assertEqual(details["carte_fin"], "4444")
        self.assertNotIn("cvv", details)
        self.assertNotIn("no_carte", details)
        self.assertEqual(details["statut"], "simulation")

    def test_second_confirmation_cannot_create_duplicate_order(self):
        self.assertTrue(self.order.valider())
        self.assertFalse(self.order.valider())
        self.assertEqual(self.db.commits, 1)
        self.assertEqual(len(self.db.state["orders"]), 1)

    def test_relay_must_belong_to_chosen_city(self):
        self.order.modeLivraison_var = field("relais")
        self.db.failure = "relais"
        self.assertFalse(self.order.valider())
        self.assertFalse(self.db.state["orders"])


class BasketTests(unittest.TestCase):
    def test_product_selection_is_retained_when_login_is_required(self):
        from app.views.product import ProductPage
        page = object.__new__(ProductPage)
        page.window = Mock()
        page.product_id = 11
        page.session = SimpleNamespace(is_authenticated=False)
        with patch("app.views.product.open_page") as launch:
            page.add()
        launch.assert_called_once_with("connexion", page.window, return_to="produit:11")

    def test_rejected_product_update_does_not_change_displayed_quantity(self):
        from app.views.product import ProductPage
        page = object.__new__(ProductPage)
        page.window = Mock()
        page.product_id = 11
        page.session = SimpleNamespace(is_authenticated=True, user=SimpleNamespace(id=7))
        page.display_quantity = Mock()
        with patch("app.accounts.current_user_id", return_value=7), patch("app.views.product.set_basket_quantity", side_effect=ValueError("Stock insuffisant")):
            with patch("app.views.product.messagebox.showerror"):
                self.assertFalse(page.change_quantity(99))
        page.display_quantity.assert_not_called()

    def test_product_write_refuses_an_account_change_before_execution(self):
        from app.views.product import ProductPage
        page = object.__new__(ProductPage)
        page.window = Mock()
        page.product_id = 11
        page.session = SimpleNamespace(is_authenticated=True, user=SimpleNamespace(id=7))
        page.display_quantity = Mock()
        with patch('app.accounts.current_user_id', return_value=8), patch('app.views.product.set_basket_quantity') as save, patch('app.views.product.messagebox.showerror'):
            self.assertFalse(page.change_quantity(1))
        save.assert_not_called()
        page.display_quantity.assert_not_called()

    def test_requested_quantity_is_checked_against_current_stock(self):
        from app.commerce import set_basket_quantity
        db = MemoryDatabase()
        with patch("app.commerce.connect", return_value=db):
            with self.assertRaises(ValueError):
                set_basket_quantity(7, 1, 6)
        self.assertEqual(db.state["cart"][1], 1)
        self.assertEqual(db.commits, 0)
        self.assertTrue(db.closed)

    def test_valid_quantity_is_written_and_connection_is_closed(self):
        from app.commerce import set_basket_quantity
        db = MemoryDatabase()
        with patch("app.commerce.connect", return_value=db):
            set_basket_quantity(7, 1, 3)
        self.assertEqual(db.state["cart"][1], 3)
        self.assertEqual(db.commits, 1)
        self.assertTrue(db.closed)

    def test_each_basket_button_updates_its_own_row_only_after_success(self):
        widgets = []

        class Widget:
            def __init__(self, *args, **kwargs):
                self.options = kwargs
                widgets.append(self)

            def grid(self, **kwargs):
                return self

            def configure(self, **kwargs):
                self.options.update(kwargs)

        ns = definitions("app/views/cart.py", ["Panier"], os=os, user_id=7,
                         customtkinter=SimpleNamespace(CTk=object, CTkLabel=Widget,
                             CTkButton=Widget, CTkFrame=Widget, CTkImage=Mock(), CTkFont=Mock()),
                         Image=SimpleNamespace(open=Mock()),
                         relative_to_assets=lambda name: ROOT / "assets/images" / name)
        basket = object.__new__(ns["Panier"])
        basket.produits = [["Premier", 1, 100, "hp.png", 5, 1],
                           ["Second", 2, 50, "hp.png", 3, 2]]
        basket.listProdFrame = SimpleNamespace(winfo_exists=lambda: True)
        basket.load_image = Mock()
        basket.nbProd = Mock()
        basket.coutTotVar = Mock()
        write = Mock(return_value=True)
        ns["fillPanier"] = write
        with patch.dict(sys.modules, {"script": SimpleNamespace(fillPanier=write)}):
            basket.listProduit(basket.produits)
            buttons = [w for w in widgets if w.options.get("text") == "+"]
            quantities = [w for w in widgets if w.options.get("text", "").startswith("Quantité")]
            buttons[0].options["command"]()
            self.assertEqual(quantities[0].options["text"], "Quantité : 2")
            self.assertEqual(quantities[1].options["text"], "Quantité : 2")
            buttons[1].options["command"]()
            self.assertEqual(quantities[1].options["text"], "Quantité : 3")
            write.return_value = False
            buttons[0].options["command"]()
            self.assertEqual(basket.produits[0][1], 2)
            self.assertEqual(quantities[0].options["text"], "Quantité : 2")


class SessionProcessTests(unittest.TestCase):
    def setUp(self):
        from app.accounts import SessionManager, User
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.session = object.__new__(SessionManager)
        self.session.SESSION_FILE = Path(self.folder.name) / "session.json"
        self.session.user = User(id=7, email="old@example.com")
        self.session.is_authenticated = True
        self.session.save_session()
        self.db = Mock()
        self.cursor = MagicMock()
        self.cursor.__enter__.return_value = self.cursor
        self.cursor.fetchone.return_value = (8, "Client", "Test", "new@example.com", "0100000000", hashlib.sha256(b'password').hexdigest())
        self.db.cursor.return_value = self.cursor

    def test_refused_login_clears_old_account_in_memory_and_on_disk(self):
        self.cursor.fetchone.return_value = None
        with patch("app.accounts.connect", return_value=self.db):
            self.assertFalse(self.session.login("unknown@example.com", "invalid"))
        self.assertFalse(self.session.is_authenticated)
        self.assertIsNone(self.session.user)
        self.assertFalse(self.session.SESSION_FILE.exists())
        self.session.load_session()
        self.assertFalse(self.session.is_authenticated)
        self.db.close.assert_called_once()

    def test_database_outage_is_distinct_from_invalid_credentials(self):
        from app.database import DatabaseError as ConnectionError
        with patch("app.accounts.connect", side_effect=ConnectionError("Unavailable")):
            with self.assertRaises(ConnectionError):
                self.session.login("new@example.com", "password")
        self.assertFalse(self.session.is_authenticated)
        self.assertFalse(self.session.SESSION_FILE.exists())

    def test_failed_local_save_cannot_leave_a_successful_login(self):
        with patch("app.accounts.connect", return_value=self.db):
            with patch("app.accounts.os.replace", side_effect=OSError("Disk full")):
                with self.assertRaises(OSError):
                    self.session.login("new@example.com", "password")
        self.assertFalse(self.session.is_authenticated)
        self.assertIsNone(self.session.user)
        self.assertEqual(list(Path(self.folder.name).iterdir()), [self.session.SESSION_FILE.with_suffix('.key')])
        self.db.close.assert_called_once()

    def test_atomic_session_write_preserves_previous_file_on_failure(self):
        original = self.session.SESSION_FILE.read_bytes()
        self.session.user.id = 8
        with patch("app.accounts.os.replace", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                self.session.save_session()
        self.assertEqual(self.session.SESSION_FILE.read_bytes(), original)
        self.assertEqual(set(Path(self.folder.name).iterdir()), {self.session.SESSION_FILE, self.session.SESSION_FILE.with_suffix('.key')})

    def test_login_ui_keeps_window_open_and_distinguishes_technical_errors(self):
        from app.database import DatabaseError as ConnectionError
        messages = Mock()
        session = Mock()
        ns = definitions("app/views/login.py", ["Login"], tk=SimpleNamespace(Tk=object),
                         SessionManager=Mock(return_value=session), messagebox=messages,
                         DatabaseError=ConnectionError, RETURN_PAGE="panier")
        window = object.__new__(ns["Login"])
        window.entry_email = field("client@example.com")
        window.entry_password = field("password")
        window.form_message = Mock()
        window.submit_button = Mock()
        window.destroy = Mock()
        for error, title in [(ConnectionError("Unavailable"), "Connexion indisponible"),
                             (OSError("Disk full"), "Session indisponible")]:
            with self.subTest(error=type(error).__name__):
                session.login.side_effect = error
                window.verification()
                self.assertTrue(window.form_message.configure.call_args.kwargs['text'].startswith(title))
        session.login.side_effect = None
        session.login.return_value = False
        window.verification()
        self.assertEqual(window.form_message.configure.call_args.kwargs['text'], "Adresse électronique ou mot de passe incorrect.")
        messages.showerror.assert_not_called()
        window.destroy.assert_not_called()
        ns["open_page"].assert_not_called()


class PaymentServiceTests(unittest.TestCase):
    def place(self, mode, details):
        from app.commerce import place_order
        return place_order(7, [("Article 1", 1, 100, "hp.png", 1),
                               ("Article 2", 2, 50, "hp.png", 2)],
                           city="Abidjan", district="Cocody", residence="",
                           delivery_mode="domicile", relay="", displayed_total=1400,
                           payment_mode=mode, payment_details=details)

    def test_invalid_payment_details_are_rejected_before_any_database_access(self):
        invalid = [(1, {}), (1, {"carte_fin": ""}), (1, {"carte_fin": "123"}),
                   (1, {"carte_fin": "4111111111111111"}), (1, {"carte_fin": "abcd"}),
                   (1, {"carte_fin": "１２３４"}), (2, {}),
                   (2, {"telephone": "0100000000"}), (2, {"telephone": "+225 short"}),
                   (2, {"telephone": "++225 0100000000"}), (3, None), (True, {})]
        with patch("app.commerce.connect") as connect:
            for mode, details in invalid:
                with self.subTest(mode=mode, details=details):
                    with self.assertRaises(ValueError):
                        self.place(mode, details)
            connect.assert_not_called()

    def test_all_simulated_payment_modes_commit_only_minimal_details(self):
        cases = [(1, {"carte_fin": "4444", "cvv": "123", "no_carte": "ignored"},
                  {"carte_fin": "4444"}),
                 (2, {"telephone": " +225   0100000000 ", "extra": "ignored"},
                  {"telephone": "+225 0100000000"}), (3, {"extra": "ignored"}, {})]
        for mode, supplied, expected in cases:
            with self.subTest(mode=mode):
                db = MemoryDatabase()
                with patch("app.commerce.connect", return_value=db):
                    result = self.place(mode, supplied)
                stored = json.loads(db.state["payments"][0][3])
                receipt=stored.pop('commande')
                self.assertEqual(receipt['livraison'],{'mode':'domicile','relais':None,'frais':'1200'})
                self.assertEqual(receipt['articles'],[{'produit_id':1,'nom':'Article 1'},{'produit_id':2,'nom':'Article 2'}])
                self.assertEqual(stored, {"statut": "simulation", "montant": "1400.00", **expected})
                stored['commande']=receipt
                self.assertEqual(result["payment"], stored)
                self.assertEqual(db.commits, 1)
                self.assertFalse(db.state["cart"])

    def test_fractional_boolean_and_invalid_quantities_do_not_access_database(self):
        from app.commerce import set_basket_quantity
        with patch("app.commerce.connect") as connect:
            for quantity in [1.9, 1.0, Decimal("1.9"), True, False, "1.9", "", None, -1]:
                with self.subTest(quantity=quantity):
                    with self.assertRaises(ValueError):
                        set_basket_quantity(7, 1, quantity)
            connect.assert_not_called()

    def test_integer_text_and_zero_quantity_remain_supported(self):
        from app.commerce import set_basket_quantity
        db = MemoryDatabase()
        with patch("app.commerce.connect", return_value=db):
            set_basket_quantity(7, 1, "3")
            self.assertEqual(db.state["cart"][1], 3)
            set_basket_quantity(7, 1, 0)
        self.assertNotIn(1, db.state["cart"])
        self.assertEqual(db.commits, 2)


class DeliveryProcessTests(unittest.TestCase):
    class Variable:
        def __init__(self, value=None):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    def setUp(self):
        from app.commerce import delivery_rates
        from app.database import DatabaseError as ConnectionError
        self.messages = Mock()
        self.localities = Mock(return_value=[("Abidjan", "Cocody", 1000),
                                            ("Abidjan", "Plateau", 2000),
                                            ("Bouaké", "Centre", 3000)])
        self.ns = definitions("app/views/checkout.py", ["Commander"],
                              customtkinter=SimpleNamespace(CTk=object),
                              DatabaseError=ConnectionError, Decimal=Decimal,
                              delivery_rates=delivery_rates, localities=self.localities,
                              messagebox=self.messages)
        self.order = object.__new__(self.ns["Commander"])
        for name, value in {"entry_ville": "Abidjan", "modeLivraison_var": "relais",
                            "relaisPrix": 2000, "domicilePrix": 1200,
                            "relaisPrixVar": "2000 FCFA", "domicilePrixVar": "1200 FCFA",
                            "coutLivVar": "2000 FCFA", "coutTotVar": "2200 FCFA"}.items():
            setattr(self.order, name, self.Variable(value))
        relay = self.Variable("Plateau")
        relay.configure = Mock()
        self.order.selectRelais = relay
        self.order._delivery_city = "abidjan"
        self.order.pointRelais = Mock()
        self.order.point = Mock()
        self.order.boutonCommander = Mock()
        self.order.prix_prod = 200
        self.order.produits = [('Article', 1, 200, 'hp.png', 1)]

    def test_refresh_preserves_relay_and_mode_when_city_is_unchanged(self):
        self.order.execute_all_keyrelease_actions()
        self.assertEqual(self.order.selectRelais.get(), "Plateau")
        self.assertEqual(self.order.modeLivraison_var.get(), "relais")
        self.assertEqual(self.order.Montant, 2200)
        self.localities.assert_called_once_with()
        self.order.boutonCommander.configure.assert_called_with(state="normal")

    def test_changed_city_requires_confirmation_of_new_relay(self):
        self.order.entry_ville.set("Bouaké")
        self.order.execute_all_keyrelease_actions()
        self.assertEqual(self.order.selectRelais.get(), "Centre")
        self.assertEqual(self.order.modeLivraison_var.get(), "")

    def test_city_without_relay_falls_back_to_home_delivery(self):
        self.order.entry_ville.set("Autre ville")
        self.order.execute_all_keyrelease_actions()
        self.assertEqual(self.order.modeLivraison_var.get(), "domicile")
        self.assertEqual(self.order.selectRelais.get(), "")
        self.assertEqual(self.order.Montant, 7400)

    def test_delivery_outage_blocks_confirmation_then_recovers_without_losing_choice(self):
        from app.database import DatabaseError as ConnectionError
        self.order.execute_all_keyrelease_actions()
        self.localities.side_effect = ConnectionError("Unavailable")
        self.order.execute_all_keyrelease_actions()
        self.order.boutonCommander.configure.assert_called_with(state="disabled")
        self.assertEqual(self.order.coutTotVar.get(), "Indisponible")
        self.assertIsNone(self.order.last_keypress)
        self.assertFalse(self.order.valider())
        self.assertEqual(self.order.selectRelais.get(), "Plateau")
        self.localities.side_effect = None
        self.order.execute_all_keyrelease_actions()
        self.assertFalse(self.order.delivery_unavailable)
        self.order.boutonCommander.configure.assert_called_with(state="normal")
        self.assertEqual(self.order.coutTotVar.get(), "2 200 FCFA")
        self.assertEqual(self.order.modeLivraison_var.get(), "relais")

    def test_initial_tariff_failure_can_be_retried(self):
        from app.database import DatabaseError as ConnectionError
        self.localities.side_effect = ConnectionError("Unavailable")
        self.assertEqual(self.order.get_livraisons(), ({}, {}))
        self.assertTrue(self.order.delivery_unavailable)
        self.messages.showerror.assert_called_once()
        self.localities.side_effect = None
        self.order.execute_all_keyrelease_actions()
        self.assertFalse(self.order.delivery_unavailable)
        self.assertEqual(self.order.Montant, 2200)


class ProductImageProcessTests(unittest.TestCase):
    def test_missing_or_unreadable_images_never_hide_cart_or_checkout_rows(self):
        from PIL import Image
        for filename, classname in [("app/views/cart.py", "Panier"),
                                    ("app/views/checkout.py", "Commander")]:
            for damaged in [False, True]:
                with self.subTest(screen=classname, damaged=damaged):
                    widgets = []

                    class Widget:
                        def __init__(self, *args, **kwargs):
                            self.options = kwargs
                            widgets.append(self)

                        def grid(self, **kwargs):
                            pass

                        def configure(self, **kwargs):
                            self.options.update(kwargs)

                    toolkit = SimpleNamespace(CTk=object, CTkLabel=Widget, CTkFrame=Widget,
                                              CTkButton=Widget, CTkImage=Mock(), CTkFont=Mock())
                    with tempfile.TemporaryDirectory() as folder:
                        if damaged:
                            (Path(folder) / "article.png").write_bytes(b"unreadable image")
                        write = Mock(return_value=True)
                        ns = definitions(filename, [classname], customtkinter=toolkit, Image=Image,
                                         relative_to_assets=lambda name: Path(folder) / name,
                                         fillPanier=write, os=os)
                        page = object.__new__(ns[classname])
                        row = ["Article visible", 2, 100, "article.png", 5, 1]
                        page.produits = [row] if classname == "Panier" else [row[:4] + [1]]
                        page.listProdFrame = SimpleNamespace(winfo_exists=lambda: True)
                        page.nbProd = Mock()
                        page.coutTotVar = Mock()
                        page.listProduit(page.produits)
                        texts = [w.options.get("text") for w in widgets]
                        self.assertIn("Article visible", texts)
                        self.assertIn("Quantité : 2", texts)
                        self.assertIn("Image\nindisponible", texts)
                        self.assertEqual(page.prix_panier(page.produits), 200)
                        if classname == "Panier":
                            button = next(w for w in widgets if w.options.get("text") == "+")
                            button.options["command"]()
                            write.assert_called_once_with(1, 3)
                            self.assertEqual(page.prix_panier(page.produits), 300)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.ns = definitions("app/admin/dashboard.py", ["filter_sales", "prepare_features_for_prediction"], pd=pd)
        self.data = pd.DataFrame({
            "date_commande": pd.to_datetime(["2024-05-01 10:00", "2024-05-01 23:59",
                                              "2024-05-02 09:00"]),
            "categorie": ["Tech", "Mode", "Tech"],
            "ville_residence": ["Abidjan", "Abidjan", "Bouaké"],
            "type_paiement": ["Wave", "Carte", "Wave"], "montant": [100, 200, 400]})

    def test_last_day_includes_evening_orders(self):
        selected = self.ns["filter_sales"](self.data, "2024-05-01", "2024-05-01")
        self.assertEqual(selected["montant"].sum(), 300)

    def test_category_city_and_payment_filters_are_combined(self):
        selected = self.ns["filter_sales"](self.data, None, None, ["Tech"], ["Abidjan"], ["Wave"])
        self.assertEqual(selected["montant"].tolist(), [100])

    def test_daily_features_preserve_all_intraday_sales_without_target_leakage(self):
        daily = self.ns["prepare_features_for_prediction"](self.data)
        self.assertEqual(daily["montant"].tolist(), [300, 400])
        self.assertEqual(daily["rolling_mean_7d"].tolist(), [0, 300])
        self.assertEqual(daily["lag_1d"].tolist(), [0, 300])

    def test_sql_join_does_not_multiply_a_sale_by_city_districts(self):
        tree = ast.parse((ROOT / "app/admin/dashboard.py").read_text(encoding="utf-8-sig"))
        query = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "main_query" for t in n.targets))
        with sqlite3.connect(":memory:") as db:
            db.executescript("""
                CREATE TABLE Client(id, nom, prenoms, sexe);
                CREATE TABLE Commande(commande_id, client_id, produit_id, nombre_article, prix_unitaire);
                CREATE TABLE DetailCommande(id, date_commande, Ville_de_residence);
                CREATE TABLE Produit(id, nom, categorie, stock, prix);
                CREATE TABLE Paiement(commande_id, mode_paiement_id);
                CREATE TABLE ModePaiement(id, type_paiement);
                CREATE TABLE Ville(city, lat, lng);
                INSERT INTO Client VALUES(1, 'Client', 'Test', 'Masculin');
                INSERT INTO Commande VALUES(1, 1, 1, 2, 100);
                INSERT INTO DetailCommande VALUES(1, '2024-05-01', 'Abidjan');
                INSERT INTO Produit VALUES(1, 'Article', 'Tech', 5, 100);
                INSERT INTO Paiement VALUES(1, 1);
                INSERT INTO ModePaiement VALUES(1, 'Wave');
            """)
            db.executemany("INSERT INTO Ville VALUES (?, ?, ?)", [("Abidjan", 5.3, -4)] * 7)
            self.assertEqual(len(db.execute(query).fetchall()), 1)

    def test_map_aggregates_city_revenue(self):
        import plotly.graph_objects as go
        chart = go.Figure()
        px = SimpleNamespace(scatter=Mock(return_value=chart))
        ns = definitions("app/admin/dashboard.py", ["create_map_figure"], px=px, go=go, json=json)
        data = self.data.assign(lat=5.3, lng=-4)
        ns["create_map_figure"](data)
        cities = px.scatter.call_args.args[0].set_index("ville_residence")
        self.assertEqual(cities.loc["Abidjan", "montant"], 300)

    def test_map_renders_with_installed_plotly_even_without_orders(self):
        import plotly.express as px
        import plotly.graph_objects as go
        ns = definitions("app/admin/dashboard.py", ["create_map_figure"], px=px, go=go, json=json)
        for data in [self.data.assign(lat=5.3, lng=-4),
                     pd.DataFrame(columns=["ville_residence", "montant", "lat", "lng"])]:
            self.assertIsInstance(ns["create_map_figure"](data).to_dict(), dict)

    def test_dedicated_export_matches_sidebar_filters(self):
        data=self.data.assign(prix_historique_connu=True)
        ns=definitions('app/admin/dashboard.py',['filter_sales','export_csv'],pd=pd,df=data)
        result=ns['export_csv'](1,'2024-05-01','2024-05-01',['Tech'],None,None)
        import io
        self.assertTrue(result['content'].startswith('\ufeff'))
        exported=pd.read_csv(io.StringIO(result['content']),sep=';',decimal=',')
        self.assertEqual(exported['Ventes hors livraison (FCFA)'].tolist(),[100])
        self.assertEqual(exported['Date de commande'].tolist(),['01/05/2024 à 10:00:00'])


class SecurityTests(unittest.TestCase):
    def test_passwords_have_unique_salts_and_legacy_hashes_remain_verifiable(self):
        from app.accounts import hash_password, verify_password
        first, second = hash_password('correct-password'), hash_password('correct-password')
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password('correct-password', first))
        self.assertFalse(verify_password('incorrect', first))
        self.assertTrue(verify_password('old-password', hashlib.sha256(b'old-password').hexdigest()))
        for malformed in ['admin', 'pbkdf2_sha256$1$bad$bad', None]:
            self.assertFalse(verify_password('password', malformed))

    def test_valid_legacy_login_upgrades_the_hash_and_closes_connection(self):
        from app.accounts import SessionManager, verify_password
        db, cursor = Mock(), MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (7, 'Client', 'Test', 'test@example.com', '0100000000', hashlib.sha256(b'legacy-password').hexdigest())
        db.cursor.return_value = cursor
        with tempfile.TemporaryDirectory() as folder:
            session = object.__new__(SessionManager)
            session.SESSION_FILE = Path(folder) / 'session.json'
            with patch('app.accounts.connect', return_value=db):
                self.assertTrue(session.login('test@example.com', 'legacy-password'))
            update = cursor.execute.call_args_list[-1].args
            self.assertIn('UPDATE Client', update[0])
            self.assertTrue(verify_password('legacy-password', update[1][0]))
            db.commit.assert_called_once()
            db.close.assert_called_once()

    def test_signed_sessions_reject_tampering_expiration_and_unsigned_files(self):
        from app.accounts import SessionManager, User
        with tempfile.TemporaryDirectory() as folder:
            session = object.__new__(SessionManager)
            session.SESSION_FILE = Path(folder) / 'session.json'
            session.user, session.is_authenticated = User(id=7), True
            session.save_session()
            original = session.SESSION_FILE.read_text(encoding='utf-8')
            session.load_session()
            self.assertTrue(session.is_authenticated)
            with patch('app.accounts.time.time', return_value=session.expires_at + 1):
                self.assertFalse(session.is_authenticated)
            session.load_session()
            changed = json.loads(original)
            changed['user']['id'] = 999
            session.SESSION_FILE.write_text(json.dumps(changed), encoding='utf-8')
            session.load_session()
            self.assertFalse(session.is_authenticated)
            session.SESSION_FILE.write_text(original, encoding='utf-8')
            expires = json.loads(original)['expires_at']
            with patch('app.accounts.time.time', return_value=expires + 1):
                session.load_session()
            self.assertFalse(session.is_authenticated)
            session.SESSION_FILE.write_text('{"is_authenticated": true, "user": {"id": 7}}', encoding='utf-8')
            session.load_session()
            self.assertFalse(session.is_authenticated)

    def test_registration_rejects_invalid_data_before_opening_mysql(self):
        from app.accounts import register_customer
        values = dict(nom='Client', prenoms='Test', sexe='Masculin', birth_date='1995-01-01',
                      email='test@example.com', password='strong-password', telephone='+225 0100000000')
        with patch('app.accounts.connect') as connect:
            for field_name, invalid in [('email','invalid'), ('password','short'), ('nom',' '),
                                        ('birth_date','2999-01-01'), ('telephone','abc'), ('sexe','invalid')]:
                with self.subTest(field=field_name):
                    with self.assertRaises(ValueError):
                        register_customer(**{**values, field_name:invalid})
            connect.assert_not_called()

    def test_admin_configuration_has_no_fallback_password(self):
        from app.config import admin_credentials
        with patch('app.config.setting', return_value=''):
            with self.assertRaises(ValueError):
                admin_credentials()

    def test_dashboard_rate_limit_and_successful_recovery(self):
        request = SimpleNamespace(authorization=None, remote_addr='127.0.0.1')
        response = lambda body,status,headers: SimpleNamespace(status=status,headers=headers)
        ns = definitions('app/admin/dashboard.py',['require_admin'],request=request,Response=response,
                         hmac=hmac,time=__import__('time'),admin_credentials=lambda:('admin','a-strong-test-password'))
        statuses=[ns['require_admin']().status for _ in range(5)]
        self.assertEqual(statuses,[401,401,401,401,429])
        request.authorization=SimpleNamespace(type='basic',username='admin',password='a-strong-test-password')
        self.assertIsNone(ns['require_admin']())
        request.authorization=None
        self.assertEqual(ns['require_admin']().status,401)


class HistoricalSalesTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "app/admin/dashboard.py").read_text(encoding="utf-8-sig"))
        self.query = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == "main_query" for t in n.targets))
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE Client(id, nom, prenoms, sexe);
            CREATE TABLE Commande(commande_id, client_id, produit_id, nombre_article, prix_unitaire);
            CREATE TABLE DetailCommande(id, date_commande, Ville_de_residence);
            CREATE TABLE Produit(id, nom, categorie, stock, prix);
            CREATE TABLE Paiement(commande_id, mode_paiement_id);
            CREATE TABLE ModePaiement(id, type_paiement);
            CREATE TABLE Ville(city, lat, lng);
            INSERT INTO Client VALUES(1, 'Client', 'Test', 'Masculin');
            INSERT INTO Commande VALUES(1, 1, 1, 2, 100);
            INSERT INTO DetailCommande VALUES(1, '2024-05-01', 'Abidjan');
            INSERT INTO Produit VALUES(1, 'Article', 'Tech', 5, 100);
            INSERT INTO Paiement VALUES(1, 1);
            INSERT INTO ModePaiement VALUES(1, 'Wave'), (2, 'Carte');
            INSERT INTO Ville VALUES('Abidjan', 5.3, -4), ('Abidjan', 5.3, -4);
        """)

    def sales(self):
        data = pd.read_sql(self.query, self.db)
        data['montant'] = data['nombre_article'] * data['prix']
        return data

    def test_catalog_price_changes_cannot_rewrite_historical_sales(self):
        self.assertEqual(self.sales()['montant'].sum(), 200)
        self.db.execute("UPDATE Produit SET prix = 150 WHERE id = 1")
        self.assertEqual(self.sales()['montant'].sum(), 200)

    def test_duplicate_payments_and_city_rows_never_multiply_a_sale(self):
        self.db.execute("INSERT INTO Paiement VALUES(1, 1)")
        data = self.sales()
        self.assertEqual(len(data), 1)
        self.assertEqual(data['montant'].sum(), 200)
        self.assertEqual(data['type_paiement'].tolist(), ['Wave'])

    def test_conflicting_payment_modes_are_explicit_without_duplicate_sales(self):
        self.db.execute("INSERT INTO Paiement VALUES(1, 2)")
        data = self.sales()
        self.assertEqual(len(data), 1)
        self.assertEqual(data['type_paiement'].tolist(), ['Paiements multiples'])
        self.assertTrue(data['mode_paiement_id'].isna().all())

    def test_missing_payment_does_not_hide_an_order(self):
        self.db.execute("DELETE FROM Paiement")
        data = self.sales()
        self.assertEqual(len(data), 1)
        self.assertEqual(data['type_paiement'].tolist(), ['Non renseigné'])

    def test_unknown_price_remains_unknown_even_when_catalog_has_a_price(self):
        self.db.execute("UPDATE Commande SET prix_unitaire = NULL")
        data = self.sales()
        self.assertTrue(data['montant'].isna().all())
        ns = definitions('app/admin/dashboard.py', ['complete_priced_orders'])
        self.assertTrue(ns['complete_priced_orders'](data).empty)

    def test_new_checkout_lines_capture_the_locked_unit_price(self):
        from app.commerce import place_order
        db = MemoryDatabase()
        with patch('app.commerce.connect', return_value=db):
            place_order(7, [('A', 1, 100, 'a.png', 1), ('B', 2, 50, 'b.png', 2)],
                        city='Abidjan', district='Cocody', residence='', delivery_mode='domicile',
                        relay='', displayed_total=1400, payment_mode=3, payment_details={})
        self.assertEqual(db.state['lines'], [(1, 7, 1, 1, Decimal('100')),
                                             (1, 7, 2, 2, Decimal('50'))])
        db.prices[1] = Decimal('150')
        self.assertEqual(db.state['lines'][0][-1], Decimal('100'))

    def test_migration_column_leaves_legacy_prices_null_and_preserves_rows(self):
        import re
        sql = (ROOT / 'database/migration_prix_historiques.sql').read_text(encoding='utf-8')
        statement = re.search(r"'(ALTER TABLE Commande ADD COLUMN[^']+)'", sql).group(1)
        with sqlite3.connect(':memory:') as db:
            db.executescript('CREATE TABLE Commande(commande_id, nombre_article); INSERT INTO Commande VALUES(9, 3);')
            db.execute(statement)
            self.assertEqual(db.execute('SELECT * FROM Commande').fetchall(), [(9, 3, None)])


class SegmentationAccuracyTests(unittest.TestCase):
    def setUp(self):
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        self.ns = definitions('app/admin/dashboard.py',
                              ['complete_priced_orders', 'prepare_customer_features',
                               'perform_customer_segmentation'], pd=pd, np=np,
                              KMeans=KMeans, StandardScaler=StandardScaler)
        self.data = pd.DataFrame({
            'client_id': [1, 1, 1], 'detailcommande_id': [10, 10, 11],
            'date_commande': pd.to_datetime(['2024-01-01', '2024-01-01', '2024-01-05']),
            'montant': [100., 200., 900.], 'nombre_article': [1, 2, 3]})

    def metrics(self):
        return self.ns['prepare_customer_features'](self.data, '2024-01-10')

    def test_orders_drive_transaction_count_average_basket_and_item_count(self):
        row = self.metrics().loc[1]
        self.assertEqual(row['nb_transactions'], 2)
        self.assertEqual(row['total_amount'], 1200)
        self.assertEqual(row['avg_amount'], 600)
        self.assertEqual(row['avg_items_per_order'], 3)
        self.assertEqual(row['avg_amount_per_item'], 200)

    def test_splitting_an_order_into_more_lines_does_not_change_customer_profile(self):
        original = self.metrics()
        combined = self.data.iloc[[0, 2]].copy()
        combined.loc[combined.index[0], ['montant', 'nombre_article']] = [300, 3]
        result = self.ns['prepare_customer_features'](combined, '2024-01-10')
        pd.testing.assert_frame_equal(original, result)

    def test_recency_uses_period_end_and_frequency_uses_observed_customer_days(self):
        row = self.metrics().loc[1]
        self.assertEqual(row['recency'], 5)
        self.assertAlmostEqual(row['purchase_frequency'], 0.2)

    def test_order_with_any_unknown_selected_price_is_excluded_entirely(self):
        self.data.loc[0, 'montant'] = np.nan
        row = self.metrics().loc[1]
        self.assertEqual(row['nb_transactions'], 1)
        self.assertEqual(row['total_amount'], 900)
        self.assertEqual(row['avg_amount'], 900)
        self.assertEqual(row['std_amount'], 0)
        self.assertTrue(np.isfinite(row.to_numpy(dtype=float)).all())

    def test_identical_profiles_cannot_generate_artificial_segments(self):
        metrics = pd.concat([self.metrics()] * 4, ignore_index=True)
        with self.assertRaisesRegex(ValueError, 'profils clients distincts'):
            self.ns['perform_customer_segmentation'](metrics, 4)
        self.assertNotIn('Segment', metrics)

    def test_distinct_profiles_produce_requested_nonempty_segments_without_mutation(self):
        metrics = pd.concat([self.metrics()] * 4, ignore_index=True)
        metrics['total_amount'] = [100., 200., 10000., 20000.]
        segmented, centers = self.ns['perform_customer_segmentation'](metrics, 2)
        self.assertEqual(segmented['Segment'].nunique(), 2)
        self.assertEqual(len(centers), 2)
        self.assertNotIn('Segment', metrics)

    def test_invalid_segment_count_and_insufficient_clients_have_clear_errors(self):
        for count in [None, 0, 1, 11, True, 2.0, 2]:
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    self.ns['perform_customer_segmentation'](self.metrics(), count)


class ForecastAccuracyTests(unittest.TestCase):
    def setUp(self):
        import plotly.graph_objects as go
        from datetime import timedelta
        self.ns = definitions('app/admin/dashboard.py',
                              ['filter_sales', 'prepare_features_for_prediction', 'forecast_values',
                               'train_prediction_model', 'update_predictions'],
                              pd=pd, np=np, go=go, timedelta=timedelta)
        self.data = pd.DataFrame({'date_commande': pd.date_range('2024-01-01', periods=84),
                                  'montant': np.arange(84, dtype=float) ** 2})
        self.ns['df'] = self.data

    def test_chronological_validation_uses_predictions_as_lags_then_refits_every_day(self):
        models=[]
        class Model:
            def __init__(self,**kwargs):self.features=[];models.append(self)
            def fit(self,X,y):self.fit_X,self.fit_y=X.copy(),y.copy()
            def predict(self,X):self.features.append(X.copy());return X['lag_1d'].to_numpy()+1
        daily=self.ns['prepare_features_for_prediction'](self.data)
        with patch.dict(sys.modules,{'xgboost':SimpleNamespace(XGBRegressor=Model)}):
            model,columns,metrics=self.ns['train_prediction_model'](daily,7)
        self.assertEqual(len(models),4)
        self.assertIs(model,models[-1])
        for evaluation,start in zip(models[:3],(63,70,77)):
            self.assertEqual(evaluation.fit_X.index[-1],start-1)
            self.assertEqual(evaluation.features[0]['lag_1d'].iloc[0],(start-1)**2)
            self.assertEqual(evaluation.features[1]['lag_1d'].iloc[0],(start-1)**2+1)
        self.assertEqual(model.fit_X.index[-1],83)
        self.assertEqual(len(model.fit_X),54)
        self.assertEqual(metrics['test_days'],21)
        self.assertEqual([row['days'] for row in metrics['folds']],[7,7,7])
        self.assertEqual(metrics['test_end'],'2024-03-24')
        expected=np.arange(63,70)**2
        self.assertAlmostEqual(metrics['folds'][0]['mae'],np.mean(np.abs(expected-np.arange(3845,3852))))
        self.assertAlmostEqual(metrics['folds'][0]['naive_mae'],np.mean(np.abs(expected-3844)))

    def test_recursive_forecast_clips_negative_sales_before_reusing_them(self):
        daily = self.ns['prepare_features_for_prediction'](self.data)
        model = Mock()
        model.predict.return_value = [-50]
        future = self.ns['forecast_values'](model, ['lag_1d'], daily, 7)
        self.assertEqual(future['predicted_sales'].tolist(), [0.] * 7)
        self.assertEqual(model.predict.call_args_list[1].args[0]['lag_1d'].iloc[0], 0)
        self.assertEqual(future['date_commande'].iloc[0], pd.Timestamp('2024-03-25'))

    def test_nonfinite_model_output_cannot_be_displayed_as_a_forecast(self):
        daily = self.ns['prepare_features_for_prediction'](self.data)
        for value in [float('nan'), float('inf')]:
            with self.subTest(value=value):
                model = Mock(predict=Mock(return_value=[value]))
                with self.assertRaises(ValueError):
                    self.ns['forecast_values'](model, ['lag_1d'], daily, 7)

    def test_forecast_graph_displays_three_periods_and_weekly_reference(self):
        model=Mock(predict=Mock(return_value=[-50]))
        folds=[dict(start='2024-03-04',end='2024-03-10',days=7,train_days=63,mae=100,weekly_mae=200,naive_mae=250)]*3
        metrics=dict(mae=100,naive_mae=250,weekly_mae=200,folds=folds,wins=3)
        self.ns['train_prediction_model']=Mock(return_value=(model,['lag_1d'],metrics))
        figure,report=self.ns['update_predictions'](1,7,None,None,None,None,None)
        self.assertEqual(len(figure.data[1].y),7)
        self.assertTrue(all(value>=0 for value in figure.data[1].y))
        self.assertEqual(figure.data[2].name,'Référence : dernière semaine')
        self.assertIn('100',str(report))
        self.assertIn('3/3',str(report))
        self.assertIn('intervalle de confiance',str(report))

    def test_unknown_prices_short_history_and_invalid_horizon_block_training(self):
        train = Mock()
        self.ns['train_prediction_model'] = train
        for horizon, data, message in [(7, self.data.assign(montant=np.nan), 'prix historiques'),
                                        (7, self.data.head(65), '66 jours'),
                                        (None, self.data, 'horizon')]:
            with self.subTest(message=message):
                self.ns['df'] = data
                figure,report = self.ns['update_predictions'](1, horizon, None, None, None, None, None)
                self.assertIn(message, figure.layout.annotations[0].text)
        train.assert_not_called()


class WiringTests(unittest.TestCase):
    def test_seed_product_image_paths_match_existing_files(self):
        import re
        sql = (ROOT / "database/schema.sql").read_text(encoding="utf-8-sig")
        images = re.findall(r"['\"]([^'\"]+\.(?:png|jpg))['\"]", sql)
        self.assertEqual(len(images), 20)
        existing = {p.name for p in (ROOT / "assets/images").iterdir()}
        self.assertFalse(set(images) - existing)
        self.assertIn("SET livraison = CASE", sql)
        self.assertNotIn("SET prix_livraison", sql)

    def test_dash_callbacks_receive_every_declared_argument(self):
        tree = ast.parse((ROOT / "app/admin/dashboard.py").read_text(encoding="utf-8-sig"))
        callback_count = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or ast.unparse(decorator.func) != "app.callback":
                    continue
                count = sum(isinstance(n, ast.Call) and ast.unparse(n.func) in ("Input", "State")
                            for n in ast.walk(decorator))
                self.assertEqual(count, len(node.args.args), node.name)
                callback_count += 1
        self.assertEqual(callback_count, 6)

    def test_all_navigation_targets_exist(self):
        from app.navigation import ROUTES, split_target
        for module in ROUTES.values():
            self.assertTrue((ROOT / module.replace(".", "/")).with_suffix(".py").is_file())
        for path in (ROOT / "app").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and ast.unparse(node.func) == "open_page" and node.args:
                    if isinstance(node.args[0], ast.Constant):
                        split_target(node.args[0].value)

    def test_direct_dashboard_access_requires_credentials(self):
        response = lambda text, status, headers: SimpleNamespace(status=status, headers=headers)
        request = SimpleNamespace(authorization=None)
        ns = definitions("app/admin/dashboard.py", ["require_admin"], os=os, hmac=hmac,
                         request=request, Response=response, time=__import__('time'))
        with patch.dict(os.environ, {"GROUP9_ADMIN_USER": "admin-test", "GROUP9_ADMIN_PASSWORD": "secret-test-2026"}):
            self.assertEqual(ns["require_admin"]().status, 401)
            request.authorization = SimpleNamespace(type="basic", username="admin-test", password="wrong")
            self.assertEqual(ns["require_admin"]().status, 401)
            request.authorization.password = "secret-test-2026"
            self.assertIsNone(ns["require_admin"]())


class OrganizationTests(unittest.TestCase):
    def test_only_database_module_constructs_mysql_connections(self):
        for path in (ROOT / "app").rglob("*.py"):
            if path.name == "database.py":
                continue
            source = path.read_text(encoding="utf-8-sig")
            self.assertNotIn("mysql.connector.connect", source, str(path))
            self.assertNotIn("mysql+pymysql://", source, str(path))

    def test_importing_views_does_not_start_the_application(self):
        for path in [*(ROOT / "app/views").glob("*.py"), *(ROOT / "app/admin").glob("*.py"),
                     *(ROOT / "app/scripts").glob("*.py")]:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in tree.body:
                self.assertIsInstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Expr))
                if isinstance(node, ast.Expr):
                    self.assertIsInstance(node.value, ast.Constant)

    def test_database_settings_are_shared_and_configurable(self):
        from app.config import database_settings
        values = {"DB_HOST": "test-host", "DB_PORT": "3307", "DB_USER": "test-user",
                  "DB_PASSWORD": "test-password", "DB_NAME": "test-database"}
        with patch.dict(os.environ, values):
            settings = database_settings()
        self.assertEqual(settings, {"host": "test-host", "port": 3307, "user": "test-user",
                                    "password": "test-password", "database": "test-database"})

    def test_mysql_factory_applies_the_shared_configuration(self):
        from app import database
        driver = SimpleNamespace(connect=Mock())
        settings = dict(host="test-host", port=3307, user="test-user", password="test-pass", database="test-db")
        with patch.object(database, "_driver", driver):
            with patch.object(database, "database_settings", return_value=settings):
                self.assertIs(database.connect(), driver.connect.return_value)
        driver.connect.assert_called_once_with(**settings, connection_timeout=5, charset="utf8mb4")

    def test_router_preserves_product_and_restricts_login_return(self):
        from app.navigation import command_for, normalize_return
        self.assertEqual(command_for("produit:11")[-3:], ["produit", "--id", "11"])
        self.assertEqual(normalize_return("produit:11"), "produit:11")
        self.assertEqual(normalize_return("tableau-de-bord"), "accueil")
        self.assertEqual(normalize_return("../outside.py"), "accueil")

    def test_router_uses_existing_application_without_destroying_window(self):
        from app.navigation import open_page
        from app.runtime import Application
        controller=object.__new__(Application)
        controller.navigate=Mock()
        window=SimpleNamespace(_app_controller=controller,destroy=Mock())
        with patch('app.runtime.launch') as launch:
            open_page('produit:11',window)
        controller.navigate.assert_called_once_with('produit:11',return_to=None,receipt=None)
        window.destroy.assert_not_called()
        launch.assert_not_called()

    def test_dashboard_startup_registers_callbacks_and_authentication(self):
        from app.admin.dashboard import create_app
        from app.analytics import Snapshot
        data=pd.DataFrame([dict(client_id=1,nom='Client',prenoms='Test',sexe='Masculin',detailcommande_id=1,
            date_commande=pd.Timestamp('2024-05-01'),ville_residence='Abidjan',produit_id=1,produit_nom='Article',
            categorie='Tech',stock=5,mode_paiement_id=1,type_paiement='Wave',nombre_article=1,prix=100,lat=5.3,lng=-4,
            montant=100,prix_historique_connu=True)])
        products=pd.DataFrame([dict(id=1,nom='Article',stock=5,categorie='Tech')])
        snapshot=Snapshot('initial',data,products,pd.Timestamp('2026-10-17',tz='UTC'))
        with patch('app.analytics.DashboardSnapshots') as store:
            store.return_value.refresh.return_value=snapshot
            store.return_value.get.return_value=snapshot
            app=create_app(engine=Mock())
        names={entry['callback'].__wrapped__.__name__ for entry in app.callback_map.values()}
        self.assertEqual(names,{'update_content','refresh_data','sort_detail','export_csv','update_predictions','update_segmentation'})
        self.assertIn('require_admin',[fn.__name__ for fn in app.server.before_request_funcs[None]])
        from app.admin import dashboard
        with patch.object(dashboard,'create_app',return_value=Mock()) as factory:
            dashboard.main()
        factory.return_value.run.assert_called_once_with(debug=False,host='127.0.0.1')

    def test_launcher_dispatches_product_and_return_without_importing_another_view(self):
        import main
        with patch('app.runtime.launch') as launch, patch.object(main, 'import_module') as load:
            self.assertEqual(main.main(["produit", "--id", "11", "--retour", "panier"]), 0)
        load.assert_not_called()
        launch.assert_called_once_with('produit:11',return_to='panier')


if __name__ == "__main__":
    unittest.main()
