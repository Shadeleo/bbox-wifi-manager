"""Gestionnaire de clients WiFi Bbox Bouygues."""

import os
import sys

from dotenv import load_dotenv

from bbox_client import BboxClient

load_dotenv()


def display_hosts(hosts: list[dict]) -> None:
    print(f"\n{'#':<4} {'Nom':<30} {'IP':<18} {'MAC':<20} {'Signal'}")
    print("-" * 80)
    for i, host in enumerate(hosts, 1):
        name = host.get("hostname") or host.get("id", "Inconnu")
        ip = host.get("ipaddress", "?")
        mac = host.get("macaddress", "?")
        rssi = host.get("rssi", "?")
        print(f"{i:<4} {name:<30} {ip:<18} {mac:<20} {rssi}")


def display_blocked(rules: list[dict]) -> None:
    if not rules:
        print("\nAucun appareil bloqué.")
        return
    print(f"\n{'#':<4} {'Nom':<30} {'MAC':<20} {'ID règle'}")
    print("-" * 70)
    for i, rule in enumerate(rules, 1):
        name = rule.get("hostname", "Inconnu")
        mac = rule.get("mac", "?")
        rule_id = rule.get("id", "?")
        print(f"{i:<4} {name:<30} {mac:<20} {rule_id}")


def menu() -> str:
    print("\n=== Gestionnaire WiFi Bbox ===")
    print("1. Voir les appareils connectés")
    print("2. Bloquer un appareil")
    print("3. Voir les appareils bloqués")
    print("4. Débloquer un appareil")
    print("0. Quitter")
    return input("\nChoix : ").strip()


def main() -> None:
    host = os.getenv("BBOX_HOST", "192.168.1.254")
    password = os.getenv("BBOX_PASSWORD")

    if not password:
        print("Erreur : BBOX_PASSWORD manquant dans le fichier .env")
        sys.exit(1)

    client = BboxClient(host, password)

    try:
        client.login()
        print("Connexion à la Bbox réussie.")
    except Exception as e:
        print(f"Impossible de se connecter : {e}")
        sys.exit(1)

    while True:
        choice = menu()

        if choice == "0":
            print("Au revoir.")
            break

        elif choice == "1":
            try:
                hosts = client.get_connected_hosts()
                if not hosts:
                    print("\nAucun appareil WiFi connecté.")
                else:
                    display_hosts(hosts)
            except Exception as e:
                print(f"Erreur : {e}")

        elif choice == "2":
            try:
                hosts = client.get_connected_hosts()
                if not hosts:
                    print("\nAucun appareil WiFi connecté.")
                    continue
                display_hosts(hosts)
                idx = input("\nNuméro de l'appareil à bloquer (0 pour annuler) : ").strip()
                if idx == "0":
                    continue
                host_entry = hosts[int(idx) - 1]
                mac = host_entry.get("macaddress", "")
                name = host_entry.get("hostname") or host_entry.get("id", "")
                client.block_mac(mac, name)
                print(f"Appareil '{name}' ({mac}) bloqué avec succès.")
            except (ValueError, IndexError):
                print("Numéro invalide.")
            except Exception as e:
                print(f"Erreur : {e}")

        elif choice == "3":
            try:
                rules = client.get_acl_rules()
                display_blocked(rules)
            except Exception as e:
                print(f"Erreur : {e}")

        elif choice == "4":
            try:
                rules = client.get_acl_rules()
                if not rules:
                    continue
                display_blocked(rules)
                idx = input("\nNuméro de la règle à supprimer (0 pour annuler) : ").strip()
                if idx == "0":
                    continue
                rule = rules[int(idx) - 1]
                client.unblock_mac(rule["id"])
                print(f"Appareil '{rule.get('hostname', rule['mac'])}' débloqué.")
            except (ValueError, IndexError):
                print("Numéro invalide.")
            except Exception as e:
                print(f"Erreur : {e}")

        else:
            print("Choix invalide.")


if __name__ == "__main__":
    main()
