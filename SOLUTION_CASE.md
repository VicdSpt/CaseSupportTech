

# Feature 1: sync status endpoint

## 1. Problem
Le problème est le suivant, le client ne voit pas les contacts importé depuis son compte Odoo se demandant si c'est le connexion qui a raté, et un deuxième problème, le client ne sait pas si ses données ont été synchronisées, ni si elles sont encore à jour.
- I just connected my Odoo account and `/contacts` returns nothing. Did the connection fail?
- Nothing I change in Odoo shows up in your API since yesterday.

Résultat : le client ouvre un ticket. L'équipe support doit investiguer, comprendre si le problème est reproductible de son côté, voir si cela vient du client, de l'API ou d'un autre endroit, pour permettre d'appliquer la solution adéquate. Pour cela, elle doit aller lire les logs du serveur.

## 2. Cause
Le souci vient de l'état "sync" qui ne s'enregistre nulle part. Les erreurs sont seulement affichées
dans le terminal du cron, côté serveur et les clients n'ont pas accès à cette partie.

## 3. Solution 
On doit construire un nouveau end point pour voir l'état des données des clients.
Celui-ci sera présent ici: http://127.0.0.1:7991/docs sous le nom: "GET/{external_id}/status"

Cela permettra au support de savoir plusieurs choses: 
- when the last sync started and finished;
- whether it succeeded, failed, or is still running;
- the error message when it failed, without leaking credentials or internal details;
- the number of synced records per object (contacts, journals, journal entries);
- the date of the last **successful** sync.

## 4. Conception

La première étape que j'ai réaliser c'est le setup du case, installer ce dont j'avais besoin et la
création du compte Odoo (v20). Et prendre ensuite connaissance de comment le swagger fonctionnait.

En laçant: "python3 update_all_accounts.py" je suis tombé sur un premier souci; dans odoo_client.py la ligne: 
CONTACT_FIELDS = ['website', 'email', 'is_company', 'title'] 
posait un problème et faisait échouer toute les synchronisation. Le compte démo de Odoo tourne en V20 et le code a été écrit pour Odoo 18, pour résoudre ce soucis j'ai du modifier la ligne en retirant "title" => 
CONTACT_FIELDS = ['website', 'email', 'is_company']

Ce qui a été fait pour résoudre ce souci est ajouté 'function' à CONTACT_FIELDS et la ligne ""job_title": infos["function"] if infos["function"] is not False else None" dans services/account_updater.py


Un fois ce souci résolu, j'ai créé le fichier .txt dans migration (202611230000_add_sync_status_accounts) pour ajouter des informations à la table "Accounts":
ALTER TABLE accounts 
ADD COLUMN `last_sync_status` VARCHAR(50) NULL,
ADD COLUMN `last_sync_started_at` datetime NULL,
ADD COLUMN `last_sync_finished_at` datetime NULL,
ADD COLUMN `last_sync_successful_at` datetime NULL,
ADD COLUMN `last_sync_error` VARCHAR(250) NULL

Ensuite j'ai commencé à coder les différentes fonctions dans models/accounts.py:
- def set_last_sync_started
- def set_success_update
- def set_fail_update
- def get_counts_for_account_id

Ensuite, j'ai du placer les fonctions au bon endroit dans service/account_updater.py et créer une fonction get_safe_error_message.

Pour vérifier le cas d'échec liè à "title", j'ai remis temporairement title dans CONTACT_FIELDS, l'enregistrement a planté : Data too long for column 'last_sync_error'. Le message brut d'Odoo était trop long et contenait des chemins internes du serveur. Le cron s'est arrêté, et le statut est resté sur running. J'ai donc créé get_safe_error_message

- def get_safe_error_message: permet de traduire une erreur technique en message court pour le client. Elle regarde le type d'erreur via isinstance et en fonction de l'erreur renvoi un message:
- identifiants Odoo refusés -> Odoo authentication failed for the provided credentials
- Odoo a refusé la requête (le cas title) -> Odoo rejected the request. Please contact support.
- Odoo injoignable (URL fausse, réseau) -> Could not reach the Odoo instance. Please check the URL
- erreur chez Chift (MySQL, bug) -> An internal error occurred during the sync... 

Pendant une scynchronisation voilà ce qui se passe:
- set_last_sync_started : au début, une fois le compte vérifié. Le statut passe à running.
- set_success_update : à la toute fin, après la sync des écritures. On ne marque success que si toutes les étapes ont réussi.
- set_fail_update : dans le except qui entoure chaque compte, là où arrivent toutes les erreurs, quelle que soit l'étape.
- get_safe_error_message : dans ce même except. Le message complet reste dans les logs pour le support, et une version courte et sûre est enregistrée pour le client.

A nouveau un test avec "title", le cron continue, le statut passe à failed avec le message court, et le dernier succès est conservé. Sans title, il repasse à success et l'erreur est effacée.

Ensuite, j'ai ajouté une fonction def get_counts_for_account_id, toujours dans service/account_updater.py, qui permet de compter les contacts, journals & journals_entries.

J'ai ensuite testé tous les cas de figures possible pour arriver au résultats souhaité pour le case.

---

## Cas 1 : never_synced (compte neuf)

Terminal 1: python run.py
Terminal 2: python -c "from db.mysql_connection import open_connection; c = open_connection(); conn = c.__enter__(); conn.cursor().execute('UPDATE accounts SET last_sync_status = NULL, last_sync_started_at = NULL, last_sync_finished_at = NULL, last_sync_successful_at = NULL, last_sync_error = NULL WHERE id = %s', [1]); c.__exit__(None, None, None); print('ok')"

Regarder le swagger pour le statut: never_synced
-> C'est le cas du ticket, compte connecté mais le /contact est vide

## Cas 2 : success (sync normale)

Terminal 1: python run.py
Terminal 2: python update_all_accounts.py

## Cas 3 : failed (panne)

Terminal 1: stop python run.py
Terminal 2: stop aussi
-> Dans services/odoo_client.py, remets 'title' dans CONTACT_FIELDS
-> Relancer les 2 terminaux
-> Check swagger

## Cas 4 : retour à success
Juste retirer "title" de CONTACT_FIELDS

## Cas 5 : external_id inconnu
-> changer le external_id dans le swagger

---

Avec plus de temps:
- Features 2 et 3 pour comprendre comment elles fonctionnent seules et toutes ensemble.
- Une nouvelle ligne dans l'affichage du swagger pour le GET STATUS quand c'est success pour avoir un message qui confirme bien que tout est en ordre au niveau des counts