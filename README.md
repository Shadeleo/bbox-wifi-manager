# Bbox WiFi Manager

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
- [Architecture](#architecture)
- [Référence API](#référence-api)
- [Comment fonctionne le blocage](#comment-fonctionne-le-blocage)
- [Sécurité](#sécurité)
- [Dépannage](#dépannage)
- [Avertissement](#avertissement)

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
| `SECRET_KEY` | aléatoire au démarrage | Clé de signature des sessions Flask |
| `PORT` | `5000` | Port d'écoute du serveur |

> **Sans `SECRET_KEY` fixe, une clé aléatoire est générée à chaque lancement : toutes les
> sessions ouvertes sont invalidées au redémarrage.** Définissez-la pour éviter d'avoir à
> vous reconnecter.

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

- Cookies de session `HttpOnly` + `SameSite=Lax`, durée de vie 8 h
- En-têtes `X-Content-Type-Options: nosniff` et `X-Frame-Options: SAMEORIGIN`
- Limitation des tentatives de connexion : **5 échecs par IP par tranche de 5 minutes**
- Validation de l'adresse IP saisie (rejet des adresses de bouclage)
- Échappement des données côté client pour prévenir les injections XSS
- Cache d'assets borné à 200 entrées

Points de vigilance :

- Le serveur écoute sur `0.0.0.0` — **toute machine du réseau local peut atteindre la page
  de connexion**. Passez `host="127.0.0.1"` dans [run.py](run.py) pour restreindre à la
  machine hôte.
- Le mot de passe de la box est conservé en session Flask et en mémoire du processus (pour
  le collecteur d'arrière-plan).
- Le trafic est en **HTTP en clair** : à réserver à un réseau domestique de confiance,
  jamais à exposer sur internet.
- La vérification TLS est désactivée sur les redirections vers Bytel (`verify=False`),
  la box présentant un certificat auto-signé.

---

## Dépannage

| Symptôme | Piste |
|---|---|
| « Authentification Bytel échouée » | Vérifiez le mot de passe admin et la connectivité internet de la box — l'étape 2 passe par le cloud Bytel. |
| « Pas de redirection vers Bytel reçue » | Firmware différent : la box n'utilise probablement pas le flux d'auth cloud. |
| Le blocage reste sans effet | Les chemins de contrôle parental varient d'un firmware à l'autre. Lancez avec les logs `DEBUG` (déjà actifs) pour voir les codes de retour. |
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
