"""Comptes clients et session locale, indépendants des interfaces."""

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import date
from tempfile import NamedTemporaryFile

from app.config import SESSION_FILE
from app.database import DatabaseError, connect

PASSWORD_ITERATIONS = 600_000


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PASSWORD_ITERATIONS)
    return f'pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password, stored):
    if not isinstance(stored, str):
        return False
    if re.fullmatch(r'[0-9a-fA-F]{64}', stored):
        return hmac.compare_digest(hashlib.sha256(password.encode('utf-8')).hexdigest(), stored.lower())
    try:
        algorithm, count, salt, expected = stored.split('$')
        rounds = int(count)
        if algorithm != 'pbkdf2_sha256' or not 600_000 <= rounds <= 2_000_000:
            return False
        salt_bytes = bytes.fromhex(salt)
        if len(salt_bytes) != 16 or len(expected) != 64:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_bytes, rounds)
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


class User:
    def __init__(self, id=None, nom=None, prenoms=None, email=None, numero_tel=None):
        self.id, self.nom, self.prenoms = id, nom, prenoms
        self.email, self.numero_tel = email, numero_tel

    def to_dict(self):
        return dict(id=self.id, nom=self.nom, prenoms=self.prenoms,
                    email=self.email, numero_tel=self.numero_tel)

    @classmethod
    def from_dict(cls, data):
        if not data:
            return None
        data = dict(data)
        if "numero_tel" not in data:
            data["numero_tel"] = data.get("tel")
        return cls(**{key: data.get(key) for key in
                      ("id", "nom", "prenoms", "email", "numero_tel")})


class SessionManager:
    _instance = None
    SESSION_FILE = SESSION_FILE
    SESSION_TTL = 8 * 60 * 60

    @property
    def is_authenticated(self):
        if getattr(self, '_authenticated', False) and time.time() < getattr(self, 'expires_at', 0):
            return True
        self._authenticated = False
        return False

    @is_authenticated.setter
    def is_authenticated(self, value):
        self._authenticated = bool(value)
        if value and not getattr(self, 'expires_at', 0):
            self.expires_at = int(time.time()) + self.SESSION_TTL
        elif not value:
            self.expires_at = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.load_session()
        return cls._instance

    def load_session(self):
        self.user = None
        self.is_authenticated = False
        try:
            if self.SESSION_FILE.exists():
                data = json.loads(self.SESSION_FILE.read_text(encoding="utf-8"))
                signature = data.pop('signature', '')
                if not hmac.compare_digest(signature, self._signature(data)):
                    return
                now = time.time()
                if not (0 <= now - data['issued_at'] < self.SESSION_TTL
                        and now < data['expires_at'] <= data['issued_at'] + self.SESSION_TTL):
                    return
                self.user = User.from_dict(data.get("user"))
                self.expires_at = data['expires_at']
                self.is_authenticated = bool(data.get("is_authenticated") and self.user
                                             and type(self.user.id) is int and self.user.id > 0)
                if not self.is_authenticated:
                    self.user = None
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            self.user = None
            self.is_authenticated = False

    def _signature(self, data, create=False):
        path = self.SESSION_FILE.with_suffix('.key')
        if create:
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(secrets.token_bytes(32))
        key = path.read_bytes()
        if len(key) != 32:
            raise OSError('Clé de session locale invalide.')
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        return hmac.new(key, payload, hashlib.sha256).hexdigest()

    def save_session(self):
        self.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        now = int(time.time())
        self.expires_at = now + self.SESSION_TTL
        payload = {
            "is_authenticated": self.is_authenticated,
            "user": self.user.to_dict() if self.user else None,
            "issued_at": now,
            "expires_at": now + self.SESSION_TTL
        }
        payload['signature'] = self._signature(payload, create=True)
        data = json.dumps(payload, ensure_ascii=False)
        temporary = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                    dir=self.SESSION_FILE.parent) as stream:
                temporary = stream.name
                stream.write(data)
            os.replace(temporary, self.SESSION_FILE)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def login(self, email, password):
        # Une nouvelle tentative ne doit jamais conserver l'ancien compte.
        self.logout()
        db = None
        try:
            db = connect()
            with db.cursor() as cursor:
                cursor.execute("""
                    SELECT id, nom, prenoms, email, numero_tel, mdp FROM Client
                    WHERE email = %s
                """, (email.strip().casefold(),))
                row = cursor.fetchone()
            if not row or not verify_password(password, row[5]):
                return False
            if not row[5].startswith('pbkdf2_sha256$'):
                with db.cursor() as cursor:
                    cursor.execute('UPDATE Client SET mdp = %s WHERE id = %s AND mdp = %s',
                                   (hash_password(password), row[0], row[5]))
                db.commit()
            self.user = User(*row[:5])
            self.is_authenticated = True
            self.save_session()
            return True
        except (DatabaseError, OSError):
            if db is not None:
                db.rollback()
            self.user = None
            self.is_authenticated = False
            raise
        finally:
            if db is not None:
                db.close()

    def logout(self):
        self.user = None
        self.is_authenticated = False
        self.SESSION_FILE.unlink(missing_ok=True)

    def get_user_display_name(self):
        if self.is_authenticated and self.user:
            return f"{self.user.prenoms} {self.user.nom}"
        return "Se connecter"


def current_user_id():
    session = SessionManager()
    user = session.user
    return user.id if user is not None and session.is_authenticated else None


def email_exists(email):
    db = connect()
    try:
        with db.cursor() as cursor:
            cursor.execute("SELECT id FROM Client WHERE email = %s", (email.strip(),))
            return cursor.fetchone() is not None
    finally:
        db.close()


def register_customer(nom, prenoms, sexe, birth_date, email, password, telephone):
    email = email.strip().casefold()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or len(email) > 100:
        raise ValueError('Adresse électronique invalide.')
    if len(password) < 12 or len(password) > 256:
        raise ValueError('Le mot de passe doit contenir de 12 à 256 caractères.')
    if not nom.strip() or not prenoms.strip() or len(nom.strip()) > 50 or len(prenoms.strip()) > 50:
        raise ValueError('Renseignez un nom et des prénoms de 50 caractères maximum.')
    if sexe not in ('Masculin', 'Feminin'):
        raise ValueError('Sélectionnez une valeur valide pour le sexe.')
    try:
        birth = date.fromisoformat(str(birth_date))
    except ValueError as error:
        raise ValueError('Date de naissance invalide.') from error
    if not date(1900, 1, 1) <= birth <= date.today():
        raise ValueError('La date de naissance doit être comprise entre 1900 et aujourd’hui.')
    telephone = telephone.strip()
    if len(telephone) > 15 or not re.fullmatch(r'\+?[0-9]{1,3} ?[0-9]{8,10}', telephone):
        raise ValueError('Numéro de téléphone invalide : indicatif et 8 à 10 chiffres attendus.')
    db = connect()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                INSERT INTO Client (nom, prenoms, sexe, date_naissance, email, mdp, numero_tel)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (nom.strip(), prenoms.strip(), sexe, birth.isoformat(), email,
                  hash_password(password), telephone))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
