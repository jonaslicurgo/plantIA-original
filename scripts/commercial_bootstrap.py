"""Grant the first commercial administrator offline on the intended database."""
import argparse

from sqlalchemy import text

from plantia import accounts, commercial
from plantia.database import init_database


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account_id", type=int)
    account_id = parser.parse_args().account_id
    init_database()
    accounts.initialize_accounts()
    commercial.init()
    with commercial.transaction() as db:
        if db.execute(text("SELECT 1 FROM accounts WHERE commercial_role='admin' AND suspended=0")).first():
            parser.error("An active commercial admin already exists")
        changed = db.execute(text("""UPDATE accounts SET commercial_role='admin'
            WHERE id=:id AND suspended=0"""), {"id": account_id})
        if not changed.rowcount:
            parser.error("Account not found or suspended")
        commercial.audit(db, account_id, "account.bootstrap", account_id, {"role": "admin"})


if __name__ == "__main__":
    main()
