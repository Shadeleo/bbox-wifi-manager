# Politique de sécurité

## Portée

Cette application détient le **mot de passe administrateur de votre box** pour dialoguer
avec son API locale. Elle est conçue pour tourner sur votre réseau domestique, pas pour
être exposée sur Internet.

## Signaler une vulnérabilité

Ouvrez une *security advisory* privée via l'onglet **Security** du dépôt GitHub.
N'ouvrez pas d'issue publique pour une faille non corrigée.

## Bonnes pratiques de déploiement

| Point | Recommandation |
|---|---|
| `SECRET_KEY` | Obligatoire dès que `APP_ENV=production` : l'application refuse de démarrer sans. Générez-la avec `python -c "import secrets; print(secrets.token_hex(32))"`. |
| Exposition réseau | `PORT` écoute sur `0.0.0.0`. Ne redirigez jamais ce port depuis Internet. |
| HTTPS | Derrière un reverse-proxy TLS, positionnez `SESSION_COOKIE_SECURE=1`. |
| `BBOX_VERIFY_TLS` | Laissez à `1`. Le passer à `0` désactive la vérification du certificat lors de l'authentification auprès de `mabbox.bytel.fr`, où transite le mot de passe. |
| `LOG_LEVEL` | Gardez `INFO` en production. `DEBUG` écrit les corps de requêtes et les jetons CSRF dans les journaux. |
| Fichier `.env` | Ne le versionnez jamais. Il est déjà couvert par `.gitignore`. |

## Traitement du mot de passe

Le mot de passe de la box n'est **jamais** placé dans le cookie de session : les sessions
Flask sont signées mais pas chiffrées. Il est conservé côté serveur, en mémoire, dans un
magasin indexé par un identifiant opaque, lui seul stocké dans la session. Un redémarrage
du serveur vide ce magasin et force une reconnexion.
