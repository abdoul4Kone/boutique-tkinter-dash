"""Lanceur unique : python main.py --help."""

import argparse
from importlib import import_module

from app.navigation import ROUTES, normalize_return
from app.database import DatabaseError


def main(argv=None):
    parser = argparse.ArgumentParser(description="Boutique et tableau de bord du groupe 9")
    parser.add_argument("page", nargs="?", default="accueil", choices=ROUTES)
    parser.add_argument("--id", dest="product_id", type=int, help="Identifiant du produit")
    parser.add_argument("--retour", default="accueil", help="Page reprise après connexion")
    args = parser.parse_args(argv)
    if args.page in ("produit", "confirmation") and (args.product_id is None or args.product_id <= 0):
        parser.error("Cette page nécessite --id avec un identifiant positif.")
    try:
        if args.page in ('tableau-de-bord','generer-clients','generer-commandes'):
            module = import_module(ROUTES[args.page])
            module.main(product_id=args.product_id, return_to=normalize_return(args.retour))
        else:
            from app.runtime import launch
            target=args.page+(f':{args.product_id}' if args.product_id is not None and args.page in ('produit','confirmation') else '')
            launch(target,return_to=normalize_return(args.retour))
    except (ModuleNotFoundError, ImportError) as error:
        parser.exit(1, f"Dépendance indisponible : {error}\n"
                       "Installez les dépendances : python -m pip install -r requirements.txt\n")
    except (DatabaseError, ValueError) as error:
        parser.exit(1, f"Démarrage impossible : {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
