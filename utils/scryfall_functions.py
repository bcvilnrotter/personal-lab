import requests
from utils.basic_functions import *
from utils.notion.database_functions import *
from utils.notion.property_formatting import *
from tqdm import tqdm
    
# --- helpers -------------------------------------------------------------

def _dig(data, path):
    """Walk a dotted path through nested dicts; None if any hop is missing."""
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _multi_select_strs(values):
    """multi_select, coercing ints (e.g. multiverse_ids) to str first."""
    if not values:
        return {"multi_select": []}
    return format_notion_multi_select([str(v) for v in values])


def _number_float(v):
    return format_notion_number(v, float=True)


# --- field map: scryfall path -> (notion property, formatter) ------------

SCRYFALL_FIELDS = [
    # identifiers / core
    ("id",                 "scryfall.id",                 format_notion_text),
    ("oracle_id",          "scryfall.oracle_id",          format_notion_text),
    ("resource_id",        "scryfall.resource_id",        format_notion_text),
    ("object",             "scryfall.object",             format_notion_select),
    ("lang",               "scryfall.lang",               format_notion_select),
    ("name",               "scryfall.name",               format_notion_text),
    ("layout",             "scryfall.layout",             format_notion_select),
    ("type_line",          "scryfall.type_line",          format_notion_text),
    ("oracle_text",        "scryfall.oracle_text",        format_notion_text),
    ("mana_cost",          "scryfall.mana_cost",          format_notion_text),
    ("power",              "scryfall.power",              format_notion_text),
    ("toughness",          "scryfall.toughness",          format_notion_text),
    ("cmc",                "scryfall.cmc",                _number_float),
    ("colors",             "scryfall.colors",             _multi_select_strs),
    ("color_identity",     "scryfall.color_identity",     _multi_select_strs),
    ("keywords",           "scryfall.keywords",           _multi_select_strs),

    # external ids
    ("arena_id",           "scryfall.arena_id",           format_notion_number),
    ("mtgo_id",            "scryfall.mtgo_id",            format_notion_number),
    ("tcgplayer_id",       "scryfall.tcgplayer_id",       format_notion_number),
    ("cardmarket_id",      "scryfall.cardmarket_id",      format_notion_number),
    ("multiverse_ids",     "scryfall.multiverse_ids",     _multi_select_strs),

    # art / printing
    ("artist",             "scryfall.artist",             format_notion_text),
    ("artist_ids",         "scryfall.artist_ids",         _multi_select_strs),
    ("illustration_id",    "scryfall.illustration_id",    format_notion_text),
    ("card_back_id",       "scryfall.card_back_id",       format_notion_text),
    ("border_color",       "scryfall.border_color",       format_notion_select),
    ("frame",              "scryfall.frame",              format_notion_select),
    ("rarity",             "scryfall.rarity",             format_notion_select),
    ("collector_number",   "scryfall.collector_number",   format_notion_text),
    ("finishes",           "scryfall.finishes",           _multi_select_strs),
    ("games",              "scryfall.games",              _multi_select_strs),
    ("image_status",       "scryfall.image_status",       format_notion_select),
    ("edhrec_rank",        "scryfall.edhrec_rank",        format_notion_number),
    ("penny_rank",         "scryfall.penny_rank",         format_notion_number),

    # set
    ("set",                "scryfall.set",                format_notion_text),
    ("set_id",             "scryfall.set_id",             format_notion_text),
    ("set_name",           "scryfall.set_name",           format_notion_text),
    ("set_type",           "scryfall.set_type",           format_notion_select),

    # urls
    ("uri",                "scryfall.uri",                format_notion_url),
    ("scryfall_uri",       "scryfall.scryfall_uri",       format_notion_url),
    ("set_uri",            "scryfall.set_uri",            format_notion_url),
    ("scryfall_set_uri",   "scryfall.scryfall_set_uri",   format_notion_url),
    ("set_search_uri",     "scryfall.set_search_uri",     format_notion_url),
    ("prints_search_uri",  "scryfall.prints_search_uri",  format_notion_url),
    ("rulings_uri",        "scryfall.rulings_uri",        format_notion_url),

    # image_uris.*  (Scryfall ships small/normal/large/png/art_crop/border_crop;
    # art/crop/display/grid/thumb exist in your schema and stay empty unless you
    # populate them from another source)
    ("image_uris.small",       "scryfall.uris.small",       format_notion_url),
    ("image_uris.normal",      "scryfall.uris.normal",      format_notion_url),
    ("image_uris.large",       "scryfall.uris.large",       format_notion_url),
    ("image_uris.png",         "scryfall.uris.png",         format_notion_url),
    ("image_uris.art_crop",    "scryfall.uris.art_crop",    format_notion_url),
    ("image_uris.border_crop", "scryfall.uris.border_crop", format_notion_url),

    # prices (Scryfall returns strings -> rich_text per your schema)
    ("prices.usd",         "scryfall.prices.usd",         format_notion_text),
    ("prices.usd_foil",    "scryfall.prices.usd_foil",    format_notion_text),
    ("prices.usd_etched",  "scryfall.prices.usd_etched",  format_notion_text),
    ("prices.eur",         "scryfall.prices.eur",         format_notion_text),
    ("prices.eur_foil",    "scryfall.prices.eur_foil",    format_notion_text),
    ("prices.tix",         "scryfall.prices.tix",         format_notion_text),

    # preview
    ("preview.source",      "scryfall.preview.source",     format_notion_text),
    ("preview.source_uri",  "scryfall.preview.source_uri", format_notion_url),
]

# dates need the pattern arg, so keep them separate
SCRYFALL_DATE_FIELDS = [
    ("released_at",          "scryfall.released_at"),
    ("image_updated_at",     "scryfall.image_updated_at"),
    ("preview.previewed_at", "scryfall.preview.previewed_at"),
]

# always written, even when False
SCRYFALL_BOOL_FIELDS = [
    ("booster",         "scryfall.booster"),
    ("digital",         "scryfall.digital"),
    ("foil",            "scryfall.foil"),
    ("nonfoil",         "scryfall.nonfoil"),
    ("full_art",        "scryfall.full_art"),
    ("textless",        "scryfall.textless"),
    ("oversized",       "scryfall.oversized"),
    ("promo",           "scryfall.promo"),
    ("reprint",         "scryfall.reprint"),
    ("reserved",        "scryfall.reserved"),
    ("variation",       "scryfall.variation"),
    ("story_spotlight", "scryfall.story_spotlight"),
    ("highres_image",   "scryfall.highres_image"),
    ("game_changer",    "scryfall.game_changer"),
]

LEGALITY_FORMATS = [
    "standard", "future", "historic", "timeless", "gladiator", "pioneer",
    "modern", "legacy", "pauper", "vintage", "penny", "commander",
    "oathbreaker", "standardbrawl", "brawl", "competitivebrawl", "alchemy",
    "paupercommander", "duel", "oldschool", "premodern", "predh", "tlr",
]


# --- the function --------------------------------------------------------

def enrich_card_primer(data, primer, keychain):
    props = primer.setdefault("properties", {})

    for src, dest, formatter in SCRYFALL_FIELDS:
        value = _dig(data, src)
        if value in (None, "", [], {}):
            continue
        props[dest] = formatter(value)

    for src, dest in SCRYFALL_DATE_FIELDS:
        value = _dig(data, src)
        if value:
            props[dest] = format_notion_date(value, patterns=["%Y-%m-%d"])

    for src, dest in SCRYFALL_BOOL_FIELDS:
        value = _dig(data, src)
        if value is not None:
            props[dest] = format_notion_checkbox(bool(value))

    legalities = data.get("legalities") or {}
    for fmt in LEGALITY_FORMATS:
        if legalities.get(fmt):
            props[f"scryfall.legalities.{fmt}"] = format_notion_select(legalities[fmt])

    if data.get("name") and "Name" not in props:
        props["Name"] = {"title": [{"text": {"content": data["name"]}}]}

    # ─── everything below is the new part ──────────────────────────────

    # Double-faced cards keep these on the front face, not the top level
    face = (data.get("card_faces") or [{}])[0]
    for key, dest in [("oracle_text", "scryfall.oracle_text"),
                      ("mana_cost",   "scryfall.mana_cost"),
                      ("power",       "scryfall.power"),
                      ("toughness",   "scryfall.toughness"),
                      ("artist",      "scryfall.artist")]:
        if dest not in props and face.get(key):
            props[dest] = format_notion_text(face[key])

    for size in ("small", "normal", "large", "png", "art_crop", "border_crop"):
        dest = f"scryfall.uris.{size}"
        if dest not in props:
            url = scryfall_image(data, size)
            if url:
                props[dest] = format_notion_url(url)

    png = scryfall_image(data, "png")
    if png:
        primer.setdefault("cover", {"type": "external", "external": {"url": png}})

    return primer

def scryfall_image(card, size="normal"):
    """Image URL, falling back to the front face on double-faced cards."""
    uris = card.get("image_uris")
    if not uris:
        uris = (card.get("card_faces") or [{}])[0].get("image_uris") or {}
    return uris.get(size)

def build_card_primer(data, page_ids, keychain):
    primer = {
        'parent': {"database_id": keychain['SCRYFALL_CARD_DBID']},
        "properties": {
            "Name": {'title': [{'text': {'content': data.get('name')}}]},
            'enriched_by': format_notion_single_relation(keychain['SCRYFALL_APP_PAGE_ID']),
            'physical_card_relation': format_notion_multi_relation(page_ids),
        }
    }
    cover = scryfall_image(data, "art_crop")
    if cover:
        primer["cover"] = {"type": "external", "external": {"url": cover}}
    return primer

def notion_functions(scry_id, response, page_ids, header, keychain):
    card = response.json()

    page_id = search_for_notion_page_by_property(
        headers=header,
        dbid=keychain['SCRYFALL_CARD_DBID'],
        value=scry_id,
        prop_name='scryfall.id',
        prop_type='rich_text'
    )

    if page_id == False:
        new_entry_to_notion_database(
            headers=header,
            data=enrich_card_primer(
                card,
                build_card_primer(card, page_ids, keychain),
                keychain
            )
        ) 
        
    else:
        update_entry_to_notion_database(
            headers=header,
            data=enrich_card_primer(
                data=card,
                primer={'properties': {}},
                keychain=keychain
            ),
            page_id=page_id
        )

def push_daily_scryfall_cards_to_notion(debug=False, **kwargs):

    """
    argparse arguments
    dry_run: bool, default=False
    scryfall_coll_db_uri': 'SCRYFALL_COLL_DB_URI'
    scryfall_card_db_uri': 'SCRYFALL_CARD_DB_URI'
    scryfall_app_page_id': 'SCRYFALL_APP_PAGE_ID'
    """

    # Get unique sets from notion database

    dry_run = kwargs.get('dry_run')
    key_list = [v for k, v in kwargs.items() if k != 'dry_run']
    keychain = get_keychain(['NOTION_TOKEN',*key_list])

    coll_dbid, coll_viewid = pull_dbid_viewid_from_notion_uri(
        notion_uri=keychain['SCRYFALL_COLL_DB_URI'])
    card_dbid, card_viewid = pull_dbid_viewid_from_notion_uri(
        notion_uri=keychain['SCRYFALL_CARD_DB_URI'])
    
    keychain.update({
        'SCRYFALL_COLL_DBID': coll_dbid,
        'SCRYFALL_COLL_VIEWID': coll_viewid,
        'SCRYFALL_CARD_DBID': card_dbid,
        'SCRYFALL_CARD_VIEWID': card_viewid
    })

    if debug:
        print(f"[DEBUG]: sets_dbid: {coll_dbid}, sets_viewid: {coll_viewid}")
        print(f"[DEBUG]: cards_dbid: {card_dbid}, cards_viewid: {card_viewid}")

    headers = get_notion_header_scalable(
        notion_token=keychain['NOTION_TOKEN'])

    coll_records = get_records_from_notion_database(
        header=headers,
        database_id=coll_dbid,
        paginated=True
    ) # leave this alone, will need this later

    mtg_scryfall_ids = {
        r
        .get('properties')
        .get('Scryfall ID')
        .get('rich_text')[0]
        .get('text')
        .get('content')
        for r in coll_records
    }

    scryfall_header = {
        'User-Agent': 'personal_lab/0.2',
        'Accept': 'application/json'    
    }
    
    output = [
        notion_functions(m,
            requests.get(
                f'https://api.scryfall.com/cards/{m}',
                headers=scryfall_header
            ),
            [
                c.get('id')
                for c in coll_records
                if c.get(
                    'properties').get(
                        'Scryfall ID').get(
                        'rich_text')[0].get(
                            'text').get('content') == m
            ],
            headers,
            keychain
        )
        for m in tqdm(
            mtg_scryfall_ids,
            total=len(mtg_scryfall_ids),
            desc='... pulling card data and pushing to notion')
    ]
