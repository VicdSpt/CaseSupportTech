import time

import schedule

from services.account_updater import AccountUpdater

# Every run updates all the data of every account: contacts, journals and journal entries
schedule.every(5).minutes.do(AccountUpdater.update_all_accounts)

if __name__ == "__main__":
    # Sync right away on start-up, then every 5 minutes
    schedule.run_all()
    while True:
        schedule.run_pending()
        time.sleep(10)
        print("slept 10 seconds")
