from datetime import date, datetime as dt
from utils.basic_functions import *
from utils.notion.basic_functions import *
from utils.notion.database_functions import *
from utils.notion.property_formatting import *

def _as_date(value):
    """Accept a date, or a 'YYYY-MM-DD' / RFC3339 string, and return a date."""

    if isinstance(value, date) and not isinstance(value, datetime):
        print(f"[+]: Value is already a date: {value}")
        return value
    if isinstance(value, datetime):
        print(f"[+]: Converting datetime to date: {value}")
        return value.date()

    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()

def pull_todays_records_useranimelist_from_mal(
        mal_user,headers,start_date,end_date):

    start = _as_date(start_date)
    end = _as_date(end_date)
    if start > end:
        raise ValueError(f"start_date {start} is after end_date {end}")

    url = f'https://api.myanimelist.net/v2/users/{mal_user}/animelist?fields=list_status&limit=100'

    print(f"[+]: Pulling records from MAL for user {mal_user} between {start_date} and {end_date}")
    records = []
    while True:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            date_data = [
                n for n in response.json()['data'] 
                if start < _as_date(n["list_status"]["updated_at"]) <= end
            ]
            records.extend(date_data)

            if 'next' in response.json()['paging']:
                url = response.json()['paging']['next']

            else:
                break
        except Exception as e:
            print(f"[!]: {e}")
            break
    print(f"[+]: Found {len(records)} records updated between {start_date} and {end_date}")
    return records

def build_notion_mal_entries_new_page(mal_record,keychain):
    update_data = {
        "parent": {
            "database_id": keychain['NOTION_MAL_ENTRIES_DBID'],
        },
        "cover": {
            "type": "external",
            "external": {
                "url": mal_record['node']['main_picture']['medium']
            }
        },
        "properties": {
            'Name': {
                'title': [{
                        'text': {
                            'content': mal_record['node']['title']
                        }
                }]
            }
        }
    }

    return update_data

def build_notion_mal_record(mal_record,keychain,headers,date,dry_run=False):
    update_data = {
        "parent": {
            "database_id": keychain['NOTION_MAL_RECORDS_DBID'],
        },
        "properties": {
            'Name': {
                'title': [{
                        'text': {
                            'content': f"{mal_record['node']['title']}_{date}"
                        }
                }]
            }
        }
    }

    if mal_record['node']['id']:
        update_data['properties']['node.id'] = format_notion_text(
            str(mal_record['node']['id']))
    if mal_record['node']['title']:
        update_data['properties']['node.title'] = format_notion_text(
            mal_record['node']['title'])
    if mal_record['list_status']['status']:
        update_data['properties']['list_status.status'] = format_notion_select(
            mal_record['list_status']['status'])
    if mal_record['list_status']['score']:
        update_data['properties']['list_status.score'] = format_notion_number(
            mal_record['list_status']['score'])
    if mal_record['list_status']['num_episodes_watched']:
        update_data['properties'][
            'list_status.num_episodes_watched'] = format_notion_number(
            mal_record['list_status']['num_episodes_watched'])
    if mal_record['list_status']['updated_at']:
        update_data['properties'][
            'list_status.updated_at'] = format_notion_date(
                mal_record['list_status']['updated_at'])
    if mal_record['list_status']['is_rewatching'] is not None:
        update_data['properties'][
            'list_status.is_rewatching'] = format_notion_checkbox(
            mal_record['list_status']['is_rewatching'])

    entries_page_id = search_for_notion_page_by_title(
        dbid=keychain['NOTION_MAL_ENTRIES_DBID'],
        headers=headers,
        title=mal_record['node']['title'],)

    print(
        f"[+]: Found MAL Entries page for {mal_record['node']['title']}: {entries_page_id}"
    ) if entries_page_id else print(
        f"[!]: No MAL Entries page found for {mal_record['node']['title']}")

    if entries_page_id:
        update_data['properties'][
            'MAL Entries'] = format_notion_single_relation(entries_page_id)
        print(f"[+]: Linking to existing MAL Entries page for {mal_record['node']['title']}")
    else:
        if dry_run:
            print(f"[DRY RUN]: Would create new page in MAL Entries database for {mal_record['node']['title']}")
        else:

            print(f"[+]: Creating new page in MAL Entries database for {mal_record['node']['title']}")

            update_data['properties'][
                'MAL Entries'] = format_notion_single_relation(
                    new_entry_to_notion_database(
                        headers,
                        build_notion_mal_entries_new_page(mal_record,keychain)
                    )
                )

    last_page_id = search_for_last_created_notion_page(
        dbid=keychain['NOTION_MAL_RECORDS_DBID'],
        headers=headers,
        title=mal_record['node']['title'],
        prop_name='node.title')

    if last_page_id:
        update_data['properties'][
            '(Relation) Last Record'] = format_notion_single_relation(last_page_id)
        print(
            f"[+]: Linking to last created record for {mal_record['node']['title']}")
    else:
        update_data['properties'][
            '(Check) No Last Record'] = format_notion_checkbox(True)

    update_data['properties'][
        '🌦️ App Ecosystem Database'] = format_notion_single_relation(
            keychain['MAL_APP_PAGE_ID'])

    return update_data

def upload_mal_to_notion(
        dry_run=False,
        mal_user='MAL_USER',
        mal_client_id='MAL_CLIENT_ID',
        notion_mal_entries_dbid='NOTION_MAL_ENTRIES_DBID',
        notion_mal_records_dbid='NOTION_MAL_RECORDS_DBID',
        mal_app_page_id='MAL_APP_PAGE_ID',
        date='today'
    ):
    if date == 'today':
        end_date = dt.now().strftime('%Y-%m-%dT%H:%M:%S%z')

    keychain = get_keychain([
        'NOTION_TOKEN',
        notion_mal_entries_dbid,
        notion_mal_records_dbid,
        mal_app_page_id,
        mal_client_id])

    headers = get_notion_header_scalable(
        notion_token=keychain['NOTION_TOKEN'])

    start_date = get_last_created_notion_page_date(
        headers=headers,
        dbid=keychain[notion_mal_records_dbid]
    )

    print(f"[+]: Last created record in Notion database {notion_mal_records_dbid} was on {start_date}")

    daily_useranimelist_records = pull_todays_records_useranimelist_from_mal(
        mal_user=mal_user,
        headers={'X-MAL-CLIENT-ID': keychain[mal_client_id]},
        start_date=start_date,
        end_date=end_date
    )

    if len(daily_useranimelist_records) == 0:
        print(f"[!]: No records found updated between {start_date} and {end_date}. Exiting.")
        return

    for record in daily_useranimelist_records:
        notion_record = build_notion_mal_record(
            record,
            keychain,
            headers,
            dt.fromisoformat(
                str(end_date).replace("Z", "+00:00")).date().isoformat(),
            dry_run=dry_run
        )

        if dry_run:
            print(f"[DRY RUN]: {notion_record}")
            return

        new_entry_to_notion_database(
            headers=headers,
            data=notion_record
        )
