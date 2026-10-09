import requests, json
from utils.basic_functions import *
from utils.notion.database_functions import *

def push_daily_scryfall_cards_to_notion(debug=False, **kwargs):

    """
    argparse arguments
    dry_run: bool, default=False
    scryfall_sets_db_uri: str, default='SCRYFALL_SETS_DB_URI'
    scryfall_cards_db_uri: str, default='SCRYFALL_CARDS_DB_URI'
    scryfall_app_page_id: str, default='SCRYFALL_APP_PAGE_ID'
    """

    # Get unique sets from notion database
    #TODO: pull physical card data from notion database
    #TODO: pull unique sets codes from physical card data

    dry_run = kwargs.get('dry_run')
    key_list = [v for k, v in kwargs.items() if k != 'dry_run']
    keychain = get_keychain(['NOTION_TOKEN',*key_list])

    sets_dbid, sets_viewid = pull_dbid_viewid_from_notion_uri(
        notion_uri=keychain['SCRYFALL_SETS_DB_URI'])
    cards_dbid, cards_viewid = pull_dbid_viewid_from_notion_uri(
        notion_uri=keychain['SCRYFALL_CARDS_DB_URI'])

    if debug:
        print(f"[DEBUG]: sets_dbid: {sets_dbid}, sets_viewid: {sets_viewid}")
        print(f"[DEBUG]: cards_dbid: {cards_dbid}, cards_viewid: {cards_viewid}")

    headers = get_notion_header_scalable(
        notion_token=keychain['NOTION_TOKEN'])

    card_records = get_records_from_notion_database(
        header=headers,
        database_id=cards_viewid,
        paginated=True
    )

    print(card_records.json())

    # Pull set information from scryfall api for each set

    # Push all data to notion per set
    #TODO: Check if page exists for the current set
    #TODO: If page exists, update the page with new data
    #TODO: If page does not exist, push a new page to the notion database
    #TODO: Pull all cards for the set and push to new database daily
    #TODO: For each card, filter pulled cards for scryfall id and connect through relation