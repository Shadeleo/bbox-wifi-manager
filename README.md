# Bbox WiFi Manager

<img width="987" height="1227" alt="image" src="https://github.com/user-attachments/assets/48ff3b7f-471d-4558-a769-cffd72d9c491" />

Interface web locale pour piloter les appareils connectés à une **Bbox Bouygues Telecom**
(testé sur *F@st5688b*, firmware 25.x).

Elle interroge l'API locale de la box, garde un historique des appareils vus, permet de
les **déconnecter** ou de les **bloquer**, affiche une **vue réseau animée** et suit la
**consommation de bande passante** en temps réel — le tout depuis votre navigateur, sans
rien envoyer à l'extérieur.

```
┌──────────────┐      HTTP local       ┌──────────────┐
│  Navigateur  │ ──────────────────▶  │  Flask (vous) │
└──────────────┘   localhost:5000      └──────┬───────┘
                                              │ API v1 + auth Bytel
                                              ▼
                                       ┌──────────────┐
                                       │     Bbox     │
                                       │192.168.1.254 │
                                       └──────────────┘
```

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
  - [En production](#en-production)
  - [Développement](#développement)
- [Architecture](#architecture)
- [Référence API](#référence-api)
- [Comment fonctionne le blocage](#comment-fonctionne-le-blocage)
- [Sécurité](#sécurité)
- [Dépannage](#dépannage)
- [Avertissement](#avertissement)
- [Licence](#licence)

---

## Fonctionnalités

### 📡 En direct
Tableau de tous les appareils connus de la Bbox : nom, IP, MAC, type de lien
(Ethernet / WiFi 2,4 – 5 – 6 GHz), force du signal (RSSI), première et dernière
connexion, statut. Tri par colonne et recherche instantanée par nom, IP ou MAC.

### 🕓 Historique
Tous les appareils jamais détectés, conservés en base SQLite locale — même ceux qui ne
sont plus connectés. La date de première connexion est préservée dans le temps.

### 🌐 Vue réseau
Représentation animée du réseau en canvas 2D : la Bbox au centre, les appareils en
orbite, des particules qui circulent sur les liens actifs. Code couleur par état
(actif / inactif / bloqué), survol pour le détail, clic pour ouvrir un panneau
latéral avec les actions.

### 📊 Consommation
- Débit **temps réel** (fenêtre glissante de 60 s, rafraîchie toutes les 2 s)
- Historique de bande passante sur **24 h** (relevé toutes les 5 min par un thread
  d'arrière-plan, rétention 30 jours)
- Volume total échangé depuis le dernier redémarrage de la box, pic de débit observé
- **Top 3 envoi / téléchargement** par appareil
- Bascule d'unité **Mb/s ↔ Mo/s**

### 🚫 Actions sur un appareil
| Action | Effet |
|---|---|
| **Déconnecter** | Expulse l'appareil du WiFi (il peut se reconnecter) |
| **Bloquer** | Coupe son accès internet via le contrôle parental de la Bbox |
| **Débloquer** | Retire le blocage et nettoie les règles créées |
| **Kick & bloquer** | Expulse puis bloque, en une seule opération |

### 🪟 Interface Bbox intégrée
Un onglet affiche l'interface d'administration native de la Bbox dans un iframe, via un
proxy qui réécrit les URL et réutilise la session déjà authentifiée — plus besoin de
retaper le mot de passe.

### 🎨 Confort
Thème sombre par défaut, mode clair mémorisé dans le navigateur, interface responsive
(mobile → grand écran), ouverture automatique du navigateur au démarrage.

---

## Prérequis

- **Python 3.10+** (le code utilise la syntaxe `int | None`)
- Une **Bbox Bouygues Telecom** accessible sur le réseau local
- Le **mot de passe administrateur** de la box

---

## Installation

```bash
git clone https://github.com/Shadeleo/delete-app-from-box.git
cd delete-app-from-box

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Dépendances : `flask`, `requests`, `python-dotenv`.

---

## Configuration

Copiez `.env.example` en `.env` et renseignez vos valeurs :

```dotenv
BBOX_HOST=192.168.1.254
BBOX_PASSWORD=ton_mot_de_passe_admin
```

| Variable | Défaut | Rôle |
|---|---|---|
| `BBOX_HOST` | `192.168.1.254` | IP locale de la box |
| `BBOX_PASSWORD` | *(vide)* | Mot de passe admin, utilisé par le collecteur d'arrière-plan |
| `APP_ENV` | `development` | `production` active le serveur waitress et rend `SECRET_KEY` obligatoire |
| `SECRET_KEY` | aléatoire au démarrage | Clé de signature des sessions Flask |
| `PORT` | `5000` | Port d'écoute du serveur |
| `LOG_LEVEL` | `INFO` | `DEBUG` journalise les corps de requêtes et les jetons CSRF |
| `BBOX_VERIFY_TLS` | `1` | Vérification du certificat lors de l'authentification Bytel |
| `SESSION_COOKIE_SECURE` | `0` | À passer à `1` uniquement derrière un reverse-proxy HTTPS |
| `ENABLE_POLLER` | `1` | Collecte périodique de la consommation WAN |

> **Sans `SECRET_KEY` fixe, une clé aléatoire est générée à chaque lancement : toutes les
> sessions ouvertes sont invalidées au redémarrage.** Définissez-la pour éviter d'avoir à
> vous reconnecter. En `APP_ENV=production`, son absence empêche le démarrage.

Générer une clé :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Le fichier `.env` est ignoré par Git — il ne doit jamais être commité.

---

## Utilisation

```bash
python run.py
```

Le navigateur s'ouvre automatiquement sur <http://localhost:5000>. Connectez-vous avec le
mot de passe admin de la box (l'IP est pré-remplie, modifiable si votre box est ailleurs).

Le serveur écoute sur `0.0.0.0` : l'interface est donc **accessible depuis tout votre
réseau local**, pas seulement depuis la machine hôte. Voir [Sécurité](#sécurité).

### En production

Passez `APP_ENV=production` : `run.py` sert alors l'application avec **waitress** au lieu
du serveur de développement Werkzeug, qui n'est pas prévu pour ça.

```dotenv
APP_ENV=production
SECRET_KEY=<votre clé>
LOG_LEVEL=INFO
```

```bash
python run.py
```

En conteneur, la box doit rester joignable sur le réseau local :

```bash
docker build -t bbox-wifi-manager .
docker run --rm --network host --env-file .env -v "$PWD/data:/app/data" bbox-wifi-manager
```

### Développement

```bash
pip install -r requirements-dev.txt

pytest                        # tests Python
ruff check .                  # lint
node tests/escaping.test.mjs  # échappement côté client
```

---

## Architecture

```
.
├── run.py                    Point d'entrée : charge .env, lance Flask, ouvre le navigateur
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py           Fabrique l'app Flask : session, en-têtes de sécurité, blueprint
│   ├── bbox.py               Client de l'API Bbox (auth Bytel, jeton CSRF, écritures)
│   ├── db.py                 Persistance SQLite : appareils + relevés réseau
│   ├── routes.py             Routes web, API JSON, proxy Bbox, collecteur d'arrière-plan
│   ├── templates/
│   │   ├── login.html        Page de connexion
│   │   └── index.html        Tableau de bord (4 onglets + vue Bbox intégrée)
│   └── static/
│       ├── app.js            Rendu des tableaux, graphiques Chart.js, vue réseau canvas
│       └── style.css         Thème clair / sombre
└── data/
    └── history.db            Base SQLite créée au premier lancement (ignorée par Git)
```

### Base de données

| Table | Contenu |
|---|---|
| `devices` | `mac` (clé), `hostname`, `ip`, `first_seen`, `last_seen`, `is_blocked` |
| `network_stats` | Relevés WAN horodatés : octets et débit RX/TX — purgés au-delà de 30 jours |

### Authentification à la Bbox

Les firmwares récents ne valident plus le mot de passe localement. `BboxClient.login()`
reproduit donc le parcours du portail officiel :

1. `POST /api/v1/login` sur la box → réponse **302** vers le service cloud Bytel
2. `POST` sur l'URL Bytel avec le même corps → dépôt du cookie de session `BBOX_ID`

Les écritures (`PUT` / `POST` / `DELETE`) suivent le même schéma : la box répond **302**
vers `https://mabbox.bytel.fr/api/v1/<path>?btoken=…`, et la requête doit être **rejouée**
sur cette URL pour être réellement appliquée. Un jeton CSRF (`btoken`) est récupéré avant
chaque écriture, avec réessais. En cas de `401`, la session est renégociée
automatiquement.

---

## Référence API

Toutes les routes exigent une session authentifiée. Les appels `/api/*` non authentifiés
renvoient `401` avec une consigne de redirection.

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/login` | Page de connexion |
| `POST` | `/login` | Authentification (limitée à 5 tentatives / 5 min / IP) |
| `POST` | `/logout` | Fermeture de session |
| `GET` | `/` | Tableau de bord |
| `GET` | `/api/devices` | Appareils actuels + compteur de bloqués |
| `GET` | `/api/history` | Tous les appareils connus en base |
| `GET` | `/api/network-stats` | Historique 24 h, total, pic, activité par appareil |
| `GET` | `/api/network-stats/live` | Débit instantané RX/TX + activité (cache 5 s) |
| `POST` | `/api/disconnect` | `{"mac": "…"}` — expulse l'appareil |
| `POST` | `/api/block` | `{"mac": "…", "hostname": "…"}` — bloque l'accès internet |
| `DELETE` | `/api/block?mac=…` | Débloque l'appareil |
| `POST` | `/api/kick-and-block` | Expulse puis bloque |
| `*` | `/proxy/bbox/<path>` | Proxy vers l'interface native de la box |
| `*` | `/api/v1/<path>` | Proxy des appels API de l'interface native |
| `GET` | `/medias/<path>`, `/static/media/<file>` | Ressources statiques de la box |

Le proxy réécrit les URL du HTML et du CSS, injecte un intercepteur `fetch` /
`XMLHttpRequest` côté client, retire les en-têtes `X-Frame-Options` et CSP qui
empêcheraient l'affichage en iframe, et met en cache les ressources statiques
(200 entrées max) pour ne pas saturer la box.

---

## Comment fonctionne le blocage

L'API `wireless/acl` de la box s'est révélée peu fiable pour couper un appareil. La
méthode retenue, vérifiée sur firmware 25.1.22, passe par le **contrôle parental** :

**Bloquer**
1. `PUT /parentalcontrol` → active le planificateur
2. `POST /parentalcontrol/scheduler/rule` → règle `block_<mac>` couvrant `00:00–24:00`, 7 j/7
3. `PUT /parentalcontrol/hosts` → rattache la MAC au contrôle parental

**Débloquer** — les mêmes étapes en sens inverse : détachement de la MAC, suppression des
règles `block_<mac>`, puis désactivation du planificateur s'il ne reste aucune règle
active.

**Déconnecter** procède par tentatives successives : d'abord `DELETE /hosts/{id}` (qui
peut émettre des trames de désauthentification), et à défaut un cycle
extinction / rallumage de la radio de la bande concernée (2,4 / 5 / 6 GHz) — cette
seconde méthode **coupe brièvement le WiFi de toute la bande**, pas seulement de
l'appareil visé.

---

## Sécurité

Mesures en place :

- **Le mot de passe de la box ne transite jamais dans le cookie de session.** Les sessions
  Flask sont signées mais *non chiffrées* : le mot de passe est conservé côté serveur, dans
  un magasin en mémoire indexé par un identifiant opaque, seul présent dans le cookie. Un
  redémarrage vide ce magasin et force une reconnexion.
- `SECRET_KEY` obligatoire en `APP_ENV=production` : refus de démarrer sans.
- Vérification TLS **active par défaut** sur l'authentification Bytel, où transite le mot
  de passe (`BBOX_VERIFY_TLS`).
- Cookies de session `HttpOnly` + `SameSite=Lax`, durée de vie 8 h, `Secure` activable
- En-têtes `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`,
  `Referrer-Policy: same-origin`
- Limitation des tentatives de connexion : **5 échecs par IP par tranche de 5 minutes**
- Validation de l'adresse IP saisie (rejet des adresses de bouclage)
- Échappement des données côté client, adapté au contexte d'insertion (texte HTML *vs*
  littéral JS dans un attribut), vérifié par `tests/escaping.test.mjs`
- Proxy vers la box : rejet des chemins de traversée et des URL absolues
- Cache d'assets borné à 200 entrées, avec expiration au bout d'une heure
- Messages d'erreur d'API génériques en production (les détails restent dans les journaux)

Points de vigilance :

- Le serveur écoute sur `0.0.0.0` — **toute machine du réseau local peut atteindre la page
  de connexion**. Passez `host="127.0.0.1"` dans [run.py](run.py) pour restreindre à la
  machine hôte.
- Le mot de passe reste en mémoire du processus, y compris pour le collecteur
  d'arrière-plan qui tourne hors de toute session HTTP.
- Le trafic est en **HTTP en clair** : à réserver à un réseau domestique de confiance,
  jamais à exposer sur internet.
- Le magasin de mots de passe et la limitation de tentatives sont **par processus** : avec
  plusieurs workers, chacun a les siens.
- **« Déconnecter » peut couper toute une bande WiFi.** Si l'expulsion ciblée échoue, le
  repli éteint puis rallume la radio de la bande concernée, ce qui déconnecte brièvement
  *tous* les appareils qui y sont rattachés.

---

## Dépannage

| Symptôme | Piste |
|---|---|
| « Authentification Bytel échouée » | Vérifiez le mot de passe admin et la connectivité internet de la box — l'étape 2 passe par le cloud Bytel. |
| « Pas de redirection vers Bytel reçue » | Firmware différent : la box n'utilise probablement pas le flux d'auth cloud. |
| Le blocage reste sans effet | Les chemins de contrôle parental varient d'un firmware à l'autre. Lancez avec `LOG_LEVEL=DEBUG` pour voir les codes de retour. |
| Onglet « Interface Bbox » vide | Ouvrez la console du navigateur : une ressource peut échapper à la réécriture d'URL du proxy. |
| Graphique de consommation vide | Le collecteur relève un point toutes les 5 min — comptez un premier délai avant l'apparition des données. |
| Reconnexion demandée à chaque redémarrage | Définissez `SECRET_KEY` dans `.env`. |

---

## Avertissement

Projet **non officiel**, sans aucun lien avec Bouygues Telecom. Il s'appuie sur des
endpoints non documentés de l'API locale de la Bbox, susceptibles de changer à chaque
mise à jour du firmware.

À n'utiliser que sur **votre propre box**, pour administrer **votre propre réseau**.
Fourni tel quel, sans garantie.

---

## Licence

[MIT](LICENSE) — © 2026 Leo Nouhaud.

Vulnérabilité à signaler : voir [SECURITY.md](SECURITY.md).
