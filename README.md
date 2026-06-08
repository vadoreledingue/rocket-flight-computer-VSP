# Rocket Flight Computer

Logiciel d'avionique pour une fusée modèle (exécuté sur Raspberry Pi). Ce dépôt contient
le contrôleur de vol (acquisition de capteurs, machine d'états, enregistrement SQLite),
et un tableau de bord web pour la supervision et les commandes.

## Structure du projet (aperçu)

- `flight/` : logique du contrôleur de vol (capteurs, état, logging)
- `dashboard/` : interface Flask, API et UI
- `db/` : schéma SQLite
- `config/` : fichiers systemd pour déploiement
- `scripts/` : scripts d'aide (ex: `deploy.sh`)
- `tests/` : tests unitaires

## Caractéristiques

- Acquisition BMP280 (pression/température) et MPU-6050 (IMU)
- Machine d'états de vol (IDLE → ARMED → ASCENT → APOGEE → DESCENT → LANDED)
- Enregistrement télémétrique en SQLite (WAL)
- Tableau de bord Flask + API REST + flux caméra MJPEG

## Prérequis

- Python 3.8+
- Dépendances listées dans `requirements.txt`
- Pour déployer sur Raspberry Pi: accès I2C, camera CSI, et paquets système (libcamera, smbus, etc.)

## Installation rapide (développement)

1. Cloner le dépôt

```bash
git clone <repo-url>
cd rocket-flight-computer-VSP
```

2. Créer et activer un environnement virtuel

```bash
python -m venv venv
venv\Scripts\activate    # Windows
source venv/bin/activate # Linux / macOS
```

3. Installer les dépendances

```bash
pip install -r requirements.txt
```

## Lancer le projet

- Démarrer le contrôleur de vol:

```bash
python -m flight.main
```

- Démarrer le tableau de bord (port 8080 par défaut):

```bash
python -m dashboard.app
```

## Tests

Lancer la suite de tests unitaires:

```bash
python -m pytest tests -v
```

## Déploiement sur Raspberry Pi (résumé)

Installer les dépendances système recommandées, créer un venv, puis :

```bash
pip install -r requirements.txt
bash scripts/deploy.sh
```

Les fichiers `config/rocket-flight.service` et `config/rocket-dashboard.service` sont fournis
pour systemd.

## Variables d'environnement utiles

- `ROCKET_DB` : chemin vers la base SQLite (défaut: `data/rocket.db` ou valeur dans `config`)
- `ROCKET_CAMERA_FRAME_FILE` : emplacement du fichier MJPEG pour le tableau de bord
