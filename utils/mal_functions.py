from datetime import date, datetime as dt
from utils.basic_functions import *
from utils.notion.basic_functions import *
from utils.notion.database_functions import *
from utils.notion.property_formatting import *
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

DEFAULT_LOOKBACK_DAYS = 3

def _as_datetime(value):
    """Return a timezone-aware UTC datetime.

    Accepts a datetime, a date (treated as midnight UTC), or an ISO-8601 /
    RFC3339 string. Naive values are assumed to be UTC. Comparisons in this
    module use full timestamps, never calendar days, so nothing updated later
    on the same day as the window start is silently dropped.
    """
    if isinstance(value, _dt):
        parsed = value
    elif isinstance(value, date):
        parsed = _dt(value.year, value.month, value.day)
    else:
        parsed = _dt.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_tz.utc)
    return parsed.astimezone(_tz.utc)

def resolve_mal_window(start_date=None, end_date='today',
                       lookback_days=DEFAULT_LOOKBACK_DAYS):
    """Return the (start, end] window of MAL updates to consider.

    The window is a fixed look-back from `end_date`, not "since the newest
    Notion record". Overlapping runs are safe because already-recorded
    updates are skipped (see `mal_record_already_logged`), so manual runs,
    delayed schedules, or crashes can no longer open gaps. Pass `start_date`
    to widen the window for a backfill.
    """
    end = _dt.now(_tz.utc) if end_date in (None, 'today') else _as_datetime(end_date)
    start = (_as_datetime(start_date) if start_date
             else end - _td(days=float(lookback_days)))
    if start > end:
        raise ValueError(f"start_date {start} is after end_date {end}")
    return start, end

def _list_type_filter(list_type):
    # Records created before manga support have no list_type, so anime
    # matches "not manga" (Notion's does_not_equal also matches empty selects).
    return {
        "property": "list_type",
        "select": (
            {"equals": "manga"} if list_type == 'manga'
            else {"does_not_equal": "manga"}
        )
    }

def mal_record_already_logged(mal_record, keychain, headers):
    """True if this exact MAL update (node.id + list_type + updated_at) is
    already in the records DB. This is what makes overlapping windows safe."""
    list_type = mal_record.get('list_type', 'anime')
    # Notion keeps date properties at minute precision, so compare to the minute.
    updated_at = _as_datetime(
        mal_record['list_status']['updated_at']).replace(second=0, microsecond=0)
    payload = {
        "filter": {"and": [
            {"property": "node.id",
             "rich_text": {"equals": str(mal_record['node']['id'])}},
            _list_type_filter(list_type),
        ]},
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
    }
    results = query_notion_database(
        headers, keychain['NOTION_MAL_RECORDS_DBID'], payload,
        f"node.id=={mal_record['node']['id']} ({list_type})")
    for page in results:
        logged = (page.get('properties', {})
                      .get('list_status.updated_at', {})
                      .get('date') or {}).get('start')
        if logged and _as_datetime(logged).replace(
                second=0, microsecond=0) == updated_at:
            return True
    return False

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

    start = _as_datetime(start_date)
    end = _as_datetime(end_date)
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
                if start < _as_datetime(n["list_status"]["updated_at"]) <= end
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
        # Keep anime and manga daily-delta chains separate.
        extra_filters=[_list_type_filter(list_type)])

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
        list_types=MAL_LIST_TYPES,
        start_date=None,
        lookback_days=DEFAULT_LOOKBACK_DAYS
    ):
    """Push MAL anime/manga list updates in (start, end] to Notion.

    `date` is the window end ('today' = now, UTC). `start_date` overrides the
    default `lookback_days` look-back, e.g. for a backfill.
    """
    start, end = resolve_mal_window(
        start_date=start_date, end_date=date, lookback_days=lookback_days)

    keychain = get_keychain([
        'NOTION_TOKEN',
        notion_mal_entries_dbid,
        notion_mal_records_dbid,
        mal_app_page_id,
        mal_client_id])

    headers = get_notion_header_scalable(
        notion_token=keychain['NOTION_TOKEN'])

    print(f"[+]: Window: {start.isoformat()} -> {end.isoformat()} "
          f"({'start_date override' if start_date else f'{lookback_days}-day look-back'})")

    mal_records = pull_todays_records_from_mal(
        mal_user=mal_user,
        headers={'X-MAL-CLIENT-ID': keychain[mal_client_id]},
        start_date=start,
        end_date=end,
        list_types=list_types
    )

    if len(mal_records) == 0:
        print(f"[!]: No records found updated between {start.isoformat()} and {end.isoformat()}. Exiting.")
        return

    record_date = end.date().isoformat()
    created = skipped = 0
    for record in mal_records:
        label = f"{record['node']['title']} ({record.get('list_type','anime')})"
        if mal_record_already_logged(record, keychain, headers):
            print(f"[=]: Already logged {label} @ {record['list_status']['updated_at']}; skipping")
            skipped += 1
            continue

        notion_record = build_notion_mal_record(
            record,
            keychain,
            headers,
            record_date,
            dry_run=dry_run
        )

        if dry_run:
            print(f"[DRY RUN]: {notion_record}")
            created += 1
            continue

        new_entry_to_notion_database(
            headers=headers,
            data=notion_record
        )
        created += 1

    print(f"[+]: {'Would create' if dry_run else 'Created'} {created} record(s); skipped {skipped} already logged.")
