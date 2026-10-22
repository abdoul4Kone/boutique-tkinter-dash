-- Base existante : corrections de données sans recréer les tables.
-- La colonne Ville.livraison est celle utilisée par l'application.
-- Recalcule les tarifs du jeu de démonstration fourni avec le projet.
START TRANSACTION;

UPDATE Produit SET image = 'xiaomi_noir.jpg' WHERE image = 'xiaomi_noire.jpg';
UPDATE Produit SET image = 'sac_inateck.png' WHERE image = 'sac_inacteck.png';
UPDATE Produit SET image = 'iphone.png' WHERE BINARY image = 'iPhone.png';

UPDATE Ville
SET livraison = CASE
    WHEN ABS(lat - 5.3167) < 0.1 AND ABS(lng + 4.0333) < 0.1 THEN 1000
    WHEN ABS(lat - 5.3167) < 0.5 AND ABS(lng + 4.0333) < 0.5 THEN 1500
    WHEN ABS(lat - 5.3167) < 1 AND ABS(lng + 4.0333) < 1 THEN 2500
    WHEN ABS(lat - 5.3167) < 2 AND ABS(lng + 4.0333) < 2 THEN 3500
    ELSE 5000
END;

COMMIT;
