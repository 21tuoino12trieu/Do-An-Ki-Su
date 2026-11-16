import os
import json
import re
from typing import List, Dict

from beektnb.intents.mongodb import MongoStorage
from beegenerate.configs.db.mongo_config import MongoConfig

def extract_code(text):
    try:
        pattern = r'iss\.\s*\d+|tv.\s*\d+'
        pattern_num = r'\d+'
        match = re.search(pattern, text)

        if "iss" in text:
            cls = "iss"
        else:
            cls = "tv"

        if match:
            code = match.group()
            match_num = re.search(pattern_num, code)

            if match_num:
                try:
                    num = int(match_num.group())
                except:
                    num = match_num.group
                
                return cls + str(num), num
            else:
                return code, 0
        else:
            return text, 0
    except Exception as e:
        return text, 0
        

def filter_detect_by_brand(
    brand: str,
    mongo_db: 'MongoStorage',
    collection_name: str = "chunk_data"
) -> List[Dict]:
    """
        filter all dectect of brand or filter  all risk.
    """
    # To do
    query = {
        "metadata.CHI_NHANH": brand,
        "metadata.kind": "detect" 
    }

    docs = mongo_db.find(query=query, collection_name=collection_name)

    final_docs = []
        
    for doc in docs:
        brand = doc['metadata']['CHI_NHANH']
        headers = doc['metadata'].get("headers_list", [])

        headers_text = " ".join(headers)
        tmp = {
            'id': doc['chunk_id'],
            'doc': doc['doc_id'],
            'content': f"Phát hiện ở chi nhánh {brand}\n" + headers_text + "\n" + doc['llm_text'],
            'code': [extract_code(headers[-1].lower()) if headers else ""],
            'headers': [headers[-1] if headers else ""]
        }
        final_docs.append(tmp)
    
    try:
        final_docs_desc = sorted(final_docs, key=lambda x: (x['code'][0][1], x['code'][0][0]))
    except Exception as e:
        final_docs_desc = final_docs


    for i in range(len(final_docs)):
        print("After: ", final_docs[i]["headers"], final_docs[i]['code'])
        print("Before: ", final_docs_desc[i]["headers"], final_docs_desc[i]['code'])

        print("*" * 10)

    return {"docs": final_docs_desc}

def filter_advise_by_brand(
    brand: str,
    mongo_db: 'MongoStorage',
    collection_name: str = "chunk_data"
) -> List[Dict]:
    """
        filter all advise of brand or filter  all risk.
    """
    # To do
    query = {
        "metadata.CHI_NHANH": brand,
        "metadata.kind": "advise"
    }

    docs = mongo_db.find(query=query, collection_name=collection_name)

    final_docs = []

    for i, doc in enumerate(docs):
        headers = doc['metadata'].get("headers_list", [])

        headers_text = " ".join(headers)
        tmp = {
            'id': doc['chunk_id'],
            'doc': doc['doc_id'],
            'content': f"Tư vấn ở chi nhánh {brand}\n" + headers_text + "\n" + doc['llm_text'],
            'code': [extract_code(headers[-1].lower()) if headers else ""],
            'headers': [headers[-1] if headers else ""]
        }

        final_docs.append(tmp)
    try:
        final_docs_desc = sorted(final_docs, key=lambda x: (x['code'][0][1], x['code'][0][0]))
    except Exception as e:
        final_docs_desc = final_docs

    for i in range(len(final_docs)):
        print("After: ", final_docs[i]["headers"], final_docs[i]['code'])
        print("Before: ", final_docs_desc[i]["headers"], final_docs_desc[i]['code'])

        print("*" * 10)
    
    return {"docs": final_docs_desc}

if __name__=='__main__':
    mongo_db = MongoStorage(
        MongoConfig.default()
    )

    docs = filter_detect_by_brand(brand="Ninh Bình", kind="detect", mongo_db=mongo_db)

    for d in docs:
        print(d)

    