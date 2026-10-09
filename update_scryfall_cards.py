import argparse
from utils.scryfall_functions import push_daily_scryfall_cards_to_notion

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--dry_run',action='store_true',default=False)
parser.add_argument('--scryfall_sets_db_uri',default='SCRYFALL_SETS_DB_URI')
parser.add_argument('--scryfall_app_page_id',default='SCRYFALL_APP_PAGE_ID')
parser.add_argument('--scryfall_cards_db_uri',default='SCRYFALL_CARDS_DB_URI')
args = parser.parse_args()

if __name__ == "__main__":
    push_daily_scryfall_cards_to_notion(debug = True,**vars(args))