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

MAL_LIST_TYPES = ('anime', 'manga')

# Fields that differ between the anime and manga list_status payloads.
# Everything else (status, score, updated_at) is shared.
MAL_LIST_FIELDS = {
    'anime': {
        'numbers': ['num_episodes_watched'],
        'repeat_flag': 'is_rewatching',
    },
    'manga': {
        'numbers': ['num_chapters_read', 'num_volumes_read'],
        'repeat_flag': 'is_rereading',
    },
}

def get_mal_display_title(mal_record):
    """Title used for Notion page names.

    Anime keep the raw MAL title (unchanged from before manga support).
    Manga get a ' (Manga)' suffix so an anime and its source manga never
    collide on the title-based MAL Entries lookup.
    """
    title = mal_record['node']['title']
    if mal_record.get('list_type') == 'manga':
        return f"{title} (Manga)"
    return title

def pull_records_from_mal_list(
        mal_user,headers,start_date,end_date,list_type='anime'):
    """Pull list entries updated in (start_date, end_date] from one MAL list.

    `list_type` is 'anime' or 'manga'. Each returned record is tagged with
    `record['list_type']` so downstream code can categorize it.
    """
    if list_type not in MAL_LIST_TYPES:
        raise ValueError(
            f"list_type must be one of {MAL_LIST_TYPES}, got {list_type!r}")

    start = _as_date(start_date)
    end = _as_date(end_date)
    if start > end:
        raise ValueError(f"start_date {start} is after end_date {end}")

    url = f'https://api.myanimelist.net/v2/users/{mal_user}/{list_type}list?fields=list_status&limit=100'

    print(f"[+]: Pulling {list_type} records from MAL for user {mal_user} between {start_date} and {end_date}")
    records = []
    while True:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            date_data = [
                {**n, 'list_type': list_type}
                for n in response.json()['data']
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
    print(f"[+]: Found {len(records)} {list_type} records updated between {start_date} and {end_date}")
    return records

def pull_todays_records_useranimelist_from_mal(
        mal_user,headers,start_date,end_date):
    """Backward-compatible wrapper: anime list only."""
    return pull_records_from_mal_list(
        mal_user,headers,start_date,end_date,list_type='anime')

def pull_todays_records_from_mal(
        mal_user,headers,start_date,end_date,list_types=MAL_LIST_TYPES):
    """Pull updated entries from every requested MAL list (anime + manga)."""
    records = []
    for list_type in list_types:
        records.extend(pull_records_from_mal_list(
            mal_user,headers,start_date,end_date,list_type=list_type))
    return records

def build_notion_mal_entries_new_page(mal_record,keychain):
    update_data = {
        "parent": {
            "database_id": keychain['NOTION_MAL_ENTRIES_DBID'],
        },
        "properties": {
            'Name': {
                'title': [{
                        'text': {
                            'content': get_mal_display_title(mal_record)
                        }
                }]
            }
        }
    }

    picture = (mal_record['node'].get('main_picture') or {}).get('medium')
    if picture:
        update_data['cover'] = {
            "type": "external",
            "external": {
                "url": picture
            }
        }

    return update_data

def build_notion_mal_record(mal_record,keychain,headers,date,dry_run=False):
    list_type = mal_record.get('list_type','anime')
    display_title = get_mal_display_title(mal_record)
    list_status = mal_record['list_status']
    update_data = {
        "parent": {
            "database_id": keychain['NOTION_MAL_RECORDS_DBID'],
        },
        "properties": {
            'Name': {
                'title': [{
                        'text': {
                            'content': f"{display_title}_{date}"
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
    for field in MAL_LIST_FIELDS[list_type]['numbers']:
        if list_status.get(field):
            update_data['properties'][
                f'list_status.{field}'] = format_notion_number(
                list_status[field])
    if mal_record['list_status']['updated_at']:
        update_data['properties'][
            'list_status.updated_at'] = format_notion_date(
                mal_record['list_status']['updated_at'])
    repeat_flag = MAL_LIST_FIELDS[list_type]['repeat_flag']
    if list_status.get(repeat_flag) is not None:
        update_data['properties'][
            f'list_status.{repeat_flag}'] = format_notion_checkbox(
            list_status[repeat_flag])
    update_data['properties']['list_type'] = format_notion_select(list_type)

    entries_page_id = search_for_notion_page_by_title(
        dbid=keychain['NOTION_MAL_ENTRIES_DBID'],
        headers=headers,
        title=display_title,)

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
        prop_name='node.title',
        # Keep anime and manga daily-delta chains separate. Records created
        # before manga support have no list_type, so anime matches "not manga"
        # (Notion's does_not_equal also matches empty selects).
        extra_filters=[{
            "property": "list_type",
            "select": (
                {"equals": "manga"} if list_type == 'manga'
                else {"does_not_equal": "manga"}
            )
        }])

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
        date='today',
        list_types=MAL_LIST_TYPES
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

    daily_useranimelist_records = pull_todays_records_from_mal(
        mal_user=mal_user,
        headers={'X-MAL-CLIENT-ID': keychain[mal_client_id]},
        start_date=start_date,
        end_date=end_date,
        list_types=list_types
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
            continue

        new_entry_to_notion_database(
            headers=headers,
            data=notion_record
        )
