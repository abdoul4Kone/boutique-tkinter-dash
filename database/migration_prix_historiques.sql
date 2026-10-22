-- À examiner puis à exécuter explicitement dans la base MySQL configurée.
-- L'application n'exécute jamais cette migration automatiquement.
-- ALTER TABLE provoque un commit implicite dans MySQL : prévoir une sauvegarde.
-- Réexécutable ; les données existantes ne sont ni supprimées ni recalculées.
-- NULL signifie « prix historique inconnu ». Le prix actuel n'est pas une preuve
-- du prix d'achat ; même montant_total peut comprendre des frais de livraison.

SET @group9_price_column_exists = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'Commande'
      AND COLUMN_NAME = 'prix_unitaire'
);
SET @group9_price_migration = IF(
    @group9_price_column_exists = 0,
    'ALTER TABLE Commande ADD COLUMN prix_unitaire DECIMAL(10,2) NULL',
    'SELECT ''La colonne Commande.prix_unitaire existe déjà.'' AS information'
);
PREPARE group9_price_statement FROM @group9_price_migration;
EXECUTE group9_price_statement;
DEALLOCATE PREPARE group9_price_statement;

-- Contrôle après migration ; cette requête ne modifie aucune donnée.
SELECT COUNT(*) AS lignes_sans_prix_historique
FROM Commande WHERE prix_unitaire IS NULL;
