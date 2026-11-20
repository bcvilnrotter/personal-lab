import argparse
from utils.mal_functions import upload_mal_to_notion, MAL_LIST_TYPES

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--dry_run',action='store_true',default=False)
parser.add_argument('--mal_user',default='the_Fizzgig')
parser.add_argument('--mal_client_id',default='MAL_CLIENT_ID')
parser.add_argument('--notion_mal_records_dbid',default='NOTION_MAL_RECORDS_DBID')
parser.add_argument('--notion_mal_entries_dbid',default='NOTION_MAL_ENTRIES_DBID')
parser.add_argument('--date',default='today')
parser.add_argument('--list_types',nargs='+',choices=MAL_LIST_TYPES,default=list(MAL_LIST_TYPES))
args = parser.parse_args()

if __name__ == "__main__":
    upload_mal_to_notion(**vars(args))