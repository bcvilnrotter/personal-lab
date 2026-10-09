import requests, json, ssl
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class NotionTLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *a, **kw):
        kw['ssl_context'] = ssl.create_default_context()
        return super().init_poolmanager(*a, **kw)

def _build_session():
    s = requests.Session()
    retry = Retry(
        total=5, connect=5, read=3, backoff_factor=1.5,
        status_forcelist=(429,500,502,503,504),
        allowed_methods=frozenset(["GET","POST","PATCH"]),
        respect_retry_after_header=True,
    )
    adapter = NotionTLSAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://",adapter)
    return s

SESSION = _build_session()
TIMEOUT = (10,60)

def get_notion_database_info(headers,database_id,
                             url='https://api.notion.com/v1/databases/'):
    return requests.get(url+database_id,headers=headers)

def get_notion_page_data(headers,pageid):
    response = requests.get(
        f'https://api.notion.com/v1/pages/{pageid}',headers=headers)
    response.raise_for_status()
    return response.json()

def get_notion_page_name(headers,pageid):
    response = requests.get(
        f'https://api.notion.com/v1/pages/{pageid}',headers=headers)
    response.raise_for_status()
    return response.json().get(
        'properties').get(
            'Name').get('title')[0].get('text').get('content')

def get_notion_page_id(page_data):
    return page_data.get('id') if page_data else "empty"
    
def search_for_notion_page_by_title(
        headers,dbid,title,
        prop_name="Name",
        lower_case=False):
    query_url = f"https://api.notion.com/v1/databases/{dbid}/query"
    title_formatted = title.lower() if lower_case else title
    
    payload = {
        "filter": {
            "property": prop_name,
            "title": {
                "equals": title_formatted
            }
        }
    }

    response = requests.post(query_url,headers=headers,json=payload)
    if response.status_code == 200 and response.json()['results'] != []:
        return response.json()["results"][0]["id"]
    else:
        return False

def search_for_notion_page_by_property(
    headers, dbid, value,
    prop_name,prop_type
):
    query_url = f"https://api.notion.com/v1/databases/{dbid}/query"
    payload = {
        "filter": {
            "property": prop_name,
            prop_type: { "equals": value}
        }
    }
    
    response = requests.post(query_url,headers=headers,json=payload)
    if response.status_code == 200 and response.json()['results'] != []:
        return response.json()['results'][0]['id']
    else:
        return False

def search_for_notion_page_by_datetime(headers,dbid,datetime):
    query_url = f"https://api.notion.com/v1/databases/{dbid}/query"

    payload = {
        "filter": {
            "property": "datetime",
            "date": {
                "equals": datetime
            }
        }
    }

    response = requests.post(query_url,headers=headers,json=payload)
    if response.status_code == 200 and response.json()['results'] != []:
        return response.json()["results"][0]["id"]
    else:
        return False

def search_for_last_created_notion_page(
        headers,
        dbid,
        title,
        prop_name="Name"):
    query_url = f"https://api.notion.com/v1/databases/{dbid}/query"

    payload = {
        "filter": {
            "property": prop_name,
            "title": {
                "equals": title
            }
        },
        "sorts": [
            {
                "timestamp": "created_time", 
                "direction": "descending"
            }
        ]
    }

    response = requests.post(query_url,headers=headers,json=payload)
    if response.status_code == 200 and response.json()['results'] != []:
        return response.json()["results"][0]["id"]
    else:
        return False

def get_last_created_notion_page_date(headers,dbid):
    query_url = f"https://api.notion.com/v1/databases/{dbid}/query"

    payload = {
        "sorts": [
            {
                "timestamp": "created_time", 
                "direction": "descending"
            }
        ]
    }

    response = requests.post(query_url,headers=headers,json=payload)
    if response.status_code == 200 and response.json()['results'] != []:
        return response.json()["results"][0]["created_time"]
    else:
        return False

def archive_page_from_database(headers,page_id):
    response = requests.patch(
        f'https://api.notion.com/v1/pages/{page_id}',
        headers=headers,data={'archived':True})
    
    response.raise_for_status()
    return response

def update_entry_to_notion_database(headers,data,page_id):
    
    try:
        response = requests.patch(
            f'https://api.notion.com/v1/pages/{page_id}',
            headers=headers, json=data)

        response.raise_for_status()
        return response
    except Exception as e:
        print(json.dumps(data,indent=2))
        print(response.status_code)
        print(response.headers)
        print(response.json())

def get_new_empty_notion_page(dbid,title):
    return {
        'parent': {'database_id': dbid},
        'properties': {
            "Name": {
                "title":[{
                    "text":{
                        "content":title
                    }
            }]
        }
    }
}

def new_entry_to_notion_database(headers,data):
    try:
        response = requests.post(
            'https://api.notion.com/v1/pages',
            headers=headers, json=data)
        response.raise_for_status()
        name = response.json().get(
            'properties').get(
                'Name').get('title')[0].get('text').get('content')
        print(f' ... Created new page in database {data} with name "{name}"')
        return response
    except Exception as e:
        print(f"[!]: Error creating new page in database {data}. Error: {e}")

def get_records_from_notion_database(header,database_id,paginated=False):
    url = f'https://api.notion.com/v1/databases/{database_id}/query'
    # response = requests.post(url,headers=header,json={},timeout=TIMEOUT)
    response = SESSION.post(url,headers=header,json={},timeout=TIMEOUT)
    response.raise_for_status()
    if paginated:
        return request_paginated_data(url,header)
    return response

def request_paginated_data(url,header,page_size=1000):
    all_data, next_cursor = [], None

    while True:
        # payload = {'start_cursor':next_cursor} if next_cursor else {}
        payload = {"page_size": page_size}
        if next_cursor:
            payload['start_cursor'] = next_cursor
        r = SESSION.post(url,headers=header,json=payload,timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        all_data.extend(data.get('results',[]))
        # print(f'... Pulled {len(all_data)} records from paginated request.')
        if not data.get('has_more'):
            return all_data
        next_cursor = data.get('next_cursor')

def get_page_name(header,page_id):
    url = f'https://api.notion.com/v1/pages/{page_id}'
    response = requests.get(url,headers=header).json()
    return response.get(
        'properties').get('Name').get('title')[0].get('text').get('content')

def get_page_update_data(dbid,name,properties_dict,cover_image_url=None):
    data = {'parent':{'database_id':dbid}}
    if cover_image_url:
        data['cover']= {
            "type":"external",
            "external":{
                "url":cover_image_url
            }
        }
    data['properties'] = {
        "Name": {
            "title": [{"text": {"content": name}}]},**properties_dict}
    return data
