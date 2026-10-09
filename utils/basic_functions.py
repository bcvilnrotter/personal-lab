import os, re
from pathlib import Path
from utils.notion.property_formatting import *
from utils.notion.basic_functions import *
from utils.notion.database_functions import *
from dotenv import load_dotenv
from pandas.api.types import *

def get_secret(secret_key):
    if not os.getenv(secret_key):
        print(f"Loading .env for {secret_key}")
        env_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','.gitignore','.env'))
        #env_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','.gitignore','.env'))
        #env_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','..','.gitignore','.env'))
        load_dotenv(dotenv_path=env_path)

    value = os.getenv(secret_key)
    print("".join(['*'])*len(value)) if value else print(f"{secret_key} wasn't pulled.")
    if value is None:
        ValueError(f"Secret '{secret_key} not found.")
    return value

def get_keychain(keys):
    return {key:get_secret(key) for key in keys}

def print_json_to_file(data,filename,return_value=False):
    with open(Path(__file__).parent.parent / "tmp" / filename,"w") as f:
        json.dump(data,f)
    if return_value:
        return True

def print_data_to_file(data,filename,return_value=False):
    with open(Path(__file__).parent.parent / "tmp" / filename,"w") as f:
        f.write(data)
    if return_value:
        return True

def pull_dbid_viewid_from_notion_uri(
        notion_uri, 
        pattern = r'https://app\.notion\.com/p/(?P<dbid>[0-9a-zA-Z]+)\?v=(?P<viewid>[0-9a-zA-Z]+)&source=copy_link'
    ):
    """
    Pulls the database id and view id from a notion uri.
    """
    return (m.groups() if (m := re.fullmatch(pattern,notion_uri.strip())) else (None,None))