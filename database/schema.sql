CREATE TABLE Client(
    id INT AUTO_INCREMENT PRIMARY KEY,
    nom VARCHAR(50) NOT NULL,
    prenoms VARCHAR(50) NOT NULL,
    sexe ENUM('Masculin','Feminin') NOT NULL,
    date_naissance DATE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    mdp VARCHAR(255) NOT NULL,
    numero_tel VARCHAR(15)
    );
    
CREATE TABLE Produit(
     id INT AUTO_INCREMENT PRIMARY KEY,
     nom VARCHAR(100),
     categorie ENUM('Vêtements','Chaussures', 'Jeux & consoles', 'Ordinateurs & téléphones','Sacs & valises') NOT NULL,
     image VARCHAR(100),
     prix DECIMAL(10,2),
     stock INT
    );
    
CREATE TABLE DetailCommande (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date_commande TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    Ville_de_residence VARCHAR(255),
    commune VARCHAR(255),
    residence VARCHAR(255) NULL,
    montant_total DECIMAL(10,2)
);

    
CREATE TABLE Commande (
    commande_id INT,
    client_id INT,
    produit_id INT,
    nombre_article INT,
    prix_unitaire DECIMAL(10,2) NULL,
    FOREIGN KEY (client_id) REFERENCES Client(id),
    FOREIGN KEY (produit_id) REFERENCES Produit(id),
    FOREIGN KEY (commande_id) REFERENCES DetailCommande(id),
    PRIMARY KEY(client_id,produit_id,commande_id)
    );
    
CREATE TABLE Panier (
    client_id INT,
    produit_id INT,
    nombre_article INT,
    FOREIGN KEY (client_id) REFERENCES Client(id),
    FOREIGN KEY (produit_id) REFERENCES Produit(id),
    PRIMARY KEY(client_id,produit_id)
    );
    

INSERT INTO Produit (nom, categorie, image, prix, stock)
VALUES
    ('Xiaomi-Smartphone 14 Ultra, version globale, couleur blanche ', 'Ordinateurs & téléphones','xiaomi_blanc.png', 240100, 80),
 ('Xiaomi-Smartphone 14 Ultra, version globale, couleur noire ', 'Ordinateurs & téléphones','xiaomi_noir.jpg', 240100, 25),
    ('Costumes de soirée personnalisés pour hommes, veste et pantalon - orange, noire', 'Vêtements','veste_orange.jpg' ,27990, 13),
    ('Costumes de soirée personnalisés pour hommes, veste et pantalon - noire', 'Vêtements','veste_noire.png',33000 , 9),
    ('Ordinateur portable HP bon marché avec processeur Intel',  'Ordinateurs & téléphones','hp.png',220000, 55),
    ("Apple MacBook Pro 14'' 512 Go SSD 16 Go RAM Puce M1 Pro CPU 8 cœurs", 'Ordinateurs & téléphones', 'macbook2.png', 966000, 45),
    ("Apple MacBook Pro 14'' 512 Go SSD 16 Go RAM Puce M2 Pro CPU 8 cœurs GPU 14", 'Ordinateurs & téléphones','macbook1.png', 1255000, 16),
    ('Sac à bandoulière décontracté pour téléphone portable', 'Sacs & valises','bandouliere.png', 5000, 50),
    ('Sac à main dame en cuir, noir', 'Sacs & valises','sac_a_main.png', 25000, 53),
    ('American Tourister Valise, noire', 'Sacs & valises', 'valise_noire.png',40176, 24),
    ('Xbox Series X - 2 To édition spéciale Galaxy Black - 1 manette', 'Jeux & consoles', 'xbox_seriesX.png' ,513000, 7),
('Console Xbox 360 slim 4 Go + Caméra Kinect + cables et manette + jeux kinect - noire', 'Jeux & consoles', 'xbox_360_noire.png' ,99700, 23),
('Console Xbox 360 slim 4 Go + Caméra Kinect + cables et manette + jeux kinect - blanche', 'Jeux & consoles', 'xbox_360_blanche.jpg' ,77993, 29),
    ("Mocassins pour hommes à succès, chaussures d'affaires ", 'Chaussures', 'soulier_noir.png', 24500, 50),
    ("Apple-iPhone 13 Pro Max ", 'Ordinateurs & téléphones', 'iphone.png',419900, 33),
    ('Inateck 42L Sac à Dos Voyage Sac à Dos... Noir', 'Sacs & valises','sac_inateck.png', 23800, 80),
    ('Chemise manche longue marron avec col', 'Vêtements','chemise_marron.png', 9000, 65),
    ("Mocassins pour hommes à succès, chaussures d'affaires - marron",  'Chaussures', 'soulier_marron.png', 35000, 34),
    ('Ensemble valise blanche', 'Sacs & valises',"ensemble_valise_blanche.png", 382767, 23),
('Ensemble valise noir', 'Sacs & valises',"ensemble_valise_noire.jpg", 353000,17);




CREATE TABLE ModePaiement (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type_paiement ENUM('Carte Bancaire', 'Wave', 'A la livraison') NOT NULL,
    description VARCHAR(255) DEFAULT NULL
);

INSERT INTO ModePaiement (type_paiement, description) VALUES
('Carte Bancaire', 'Paiement par carte bancaire'),
('Wave', 'Paiement via l\'application Wave'),
('A la livraison', 'Paiement effectué lors de la livraison');

CREATE TABLE Paiement (
    id INT AUTO_INCREMENT PRIMARY KEY,
    commande_id INT,
    mode_paiement_id INT,
    montant DECIMAL(10, 2) NOT NULL,
    details_paiement JSON DEFAULT NULL, 
    date_paiement TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (commande_id) REFERENCES DetailCommande(id),
    FOREIGN KEY (mode_paiement_id) REFERENCES ModePaiement(id)
);

CREATE TABLE Ville (
    city VARCHAR(255),
    lat DECIMAL(10, 7),
    lng DECIMAL(10, 7),
    country VARCHAR(255),
    iso2 VARCHAR(2),
    quartier VARCHAR(255),
    admin_name VARCHAR(255),
    capital VARCHAR(50),
    population INT,
    population_proper INT
);


INSERT INTO Ville (city, lat, lng, country, iso2, quartier, admin_name, capital, population, population_proper) 
VALUES
('Abidjan', 5.3167, -4.0333, 'Côte d’Ivoire', 'CI', 'Abidjan', 'Abidjan', 'primary', 4980000, 4980000),
('Abidjan', 5.3167, -4.0667, 'Côte d’Ivoire', 'CI', 'Yopougon', 'Abidjan', NULL, 1571065, 1571065),
('Abidjan', 5.35, -3.9667, 'Côte d’Ivoire', 'CI', 'Cocody', 'Abidjan', NULL, 692583, 692583),
('Bouaké', 7.6833, -5.0167, 'Côte d’Ivoire', 'CI', 'Bouaké', 'Vallée du Bandama', 'admin', 659233, 659233),
('Abidjan', 5.2667, -3.9, 'Côte d’Ivoire', 'CI', 'Port-Bouët', 'Abidjan', NULL, 618795, 618795),
('Daloa', 6.8833, -6.45, 'Côte d’Ivoire', 'CI', 'Daloa', 'Sassandra-Marahoué', 'admin', 421871, 421871),
('Abidjan', 5.3, -3.95, 'Côte d’Ivoire', 'CI', 'Koumassi', 'Abidjan', NULL, 412282, 412282),
('San-Pédro', 4.75, -6.6333, 'Côte d’Ivoire', 'CI', 'San-Pédro', 'Bas-Sassandra', 'admin', 390654, 390654),
('Abidjan', 5.3333, -4.0333, 'Côte d’Ivoire', 'CI', 'Attiecoubé', 'Abidjan', NULL, 313135, 313135),
('Korhogo', 9.4167, -5.6167, 'Côte d’Ivoire', 'CI', 'Korhogo', 'Savanes', 'admin', 286071, 286071),
('Gagnoa', 6.1333, -5.9333, 'Côte d’Ivoire', 'CI', 'Gagnoa', 'Gôh-Djiboua', 'admin', 277044, 277044),
('Soubré', 5.7833, -6.6, 'Côte d’Ivoire', 'CI', 'Soubré', 'Bas-Sassandra', 'minor', 272773, 272773),
('Oumé', 6.3833, -5.4167, 'Côte d’Ivoire', 'CI', 'Oumé', 'Gôh-Djiboua', 'minor', 260786, 260786),
('Man', 7.4, -7.55, 'Côte d’Ivoire', 'CI', 'Man', 'Montagnes', 'admin', 241969, 241969),
('Duekoué', 6.7333, -7.35, 'Côte d’Ivoire', 'CI', 'Duekoué', 'Montagnes', 'minor', 220953, 220953),
('Bingerville', 5.35, -3.9, 'Côte d’Ivoire', 'CI', 'Bingerville', 'Abidjan', 'minor', 204656, 204656),
('Divo', 5.8333, -5.3667, 'Côte d’Ivoire', 'CI', 'Divo', 'Gôh-Djiboua', 'minor', 179455, 179455),
('Abengourou', 6.7333, -3.4833, 'Côte d’Ivoire', 'CI', 'Abengourou', 'Comoé', 'admin', 164424, 164424),
('Ferkessédougou', 9.5833, -5.2, 'Côte d’Ivoire', 'CI', 'Ferkessédougou', 'Savanes', 'minor', 160267, 160267),
('Adzopé', 6.1667, -3.9833, 'Côte d’Ivoire', 'CI', 'Adzopé', 'Lagunes', 'minor', 156488, 156488),
('Bondoukou', 8.0333, -2.8, 'Côte d’Ivoire', 'CI', 'Bondoukou', 'Zanzan', 'admin', 141568, 141568),
('Dabou', 5.3167, -4.3833, 'Côte d’Ivoire', 'CI', 'Dabou', 'Lagunes', 'admin', 138083, 138083),
('Sinfra', 6.85, -5.9167, 'Côte d’Ivoire', 'CI', 'Sinfra', 'Sassandra-Marahoué', 'minor', 137210, 137210),
('Agboville', 5.9333, -4.2167, 'Côte d’Ivoire', 'CI', 'Agboville', 'Lagunes', 'minor', 135082, 135082),
('Grand-Bassam', 5.2, -3.7333, 'Côte d’Ivoire', 'CI', 'Grand-Bassam', 'Comoé', 'minor', 124567, 124567),
('Daoukro', 7.05, -3.9667, 'Côte d’Ivoire', 'CI', 'Daoukro', 'Lacs', 'minor', 101136, 101136),
('Aboisso', 5.4667, -3.2, 'Côte d’Ivoire', 'CI', 'Aboisso', 'Comoé', 'minor', 100903, 100903),
('Odienné', 9.5, -7.5667, 'Côte d’Ivoire', 'CI', 'Odienné', 'Denguélé', 'admin', 86279, 86279),
('Dimbokro', 6.65, -4.7, 'Côte d’Ivoire', 'CI', 'Dimbokro', 'Lacs', 'admin', 70198, 70198),
('Séguéla', 7.9667, -6.6667, 'Côte d’Ivoire', 'CI', 'Séguéla', 'Woroba', 'admin', 67240, 67240),
('Yamoussoukro', 6.8161, -5.2742, 'Côte d’Ivoire', 'CI', 'Yamoussoukro', 'Yamoussoukro', 'primary', 37253, 37253),
('Bangolo', 7.0123, -7.4864, 'Côte d’Ivoire', 'CI', 'Bangolo', 'Montagnes', 'admin', NULL, NULL),
('Abidjan', 5.4946, -4.0518, 'Côte d’Ivoire', 'CI', 'Anyama', 'Abidjan', 'minor', NULL, NULL),
('Méagui', 5.4048, -6.5584, 'Côte d’Ivoire', 'CI', 'Méagui', 'Bas-Sassandra', 'minor', NULL, NULL);

ALTER TABLE Ville
ADD COLUMN livraison INT;

UPDATE Ville
SET livraison = CASE
    WHEN ABS(lat - 5.3167) < 0.1 AND ABS(lng + 4.0333) < 0.1 THEN 1000   -- Abidjan ou proche
    WHEN ABS(lat - 5.3167) < 0.5 AND ABS(lng + 4.0333) < 0.5 THEN 1500  -- Proche (moins de 50 km)
    WHEN ABS(lat - 5.3167) < 1 AND ABS(lng + 4.0333) < 1 THEN 2500     -- Moyennement éloigné (100-200 km)
    WHEN ABS(lat - 5.3167) < 2 AND ABS(lng + 4.0333) < 2 THEN 3500     -- Assez éloigné (200-300 km)
    ELSE 5000                                                           -- Très éloigné (plus de 300 km)
END;


-- Les comptes clients sont créés via le formulaire ou le générateur explicite.
-- Les identifiants administrateur sont configurés dans .env, hors de cette table.
