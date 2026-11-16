import asyncio
import aiohttp
import logging
import argparse
import uuid
from typing import Dict, Any, List, Optional, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def get_documents_by_bot_id(
    session: aiohttp.ClientSession,
    base_url: str,
    bot_id: str,
    bearer_token: str,
    page: int = 0,
    size: int = 1000,
    sort: str = "createdAt,DESC"
) -> Dict[str, Any]:
    """
    Retrieve a list of documents by bot_id from the specified environment.
    """
    url = f"{base_url.rstrip('/')}/beegen-portal-be/document/all"
    
    params = {
        "page": str(page),
        "botId": bot_id,
        "sort": sort,
        "size": str(size)
    }
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en",
        "authorization": f"Bearer {bearer_token}",
        "clientmessageid": str(uuid.uuid4()),
        "priority": "u=1, i",
        "referer": f"{base_url.rstrip('/')}/chatbot/{bot_id}/documents",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
        ),
    }
    
    async with session.get(url, params=params, headers=headers, timeout=30) as response:
        response.raise_for_status()
        return await response.json()

async def get_chunk_by_document_id(
    session: aiohttp.ClientSession,
    base_url: str,
    document_id: str,
    bot_id: str,
    bearer_token: str,
    timeout: int = 30
):
    """
    Retrieve chunks (document data) by document_id + bot_id.
    """
    url = f"{base_url.rstrip('/')}/beegen-portal-be/document/data"
    
    params = {
        "documentId": document_id,
        "botId": bot_id,
    }
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en",
        "authorization": f"Bearer {bearer_token}",
        "clientmessageid": str(uuid.uuid4()),
        "priority": "u=1, i",
        "referer": f"{base_url.rstrip('/')}/chatbot/{bot_id}/documents/{document_id}",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    }
    
    async with session.get(url, params=params, headers=headers, timeout=timeout) as response:
        if response.status == 401:
            raise RuntimeError(f"❌ 401 Unauthorized on {base_url} – Token expired or insufficient permissions")
        
        response.raise_for_status()
        return await response.json()

async def target_delete_chunk(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    base_url: str,
    bot_id: str,
    documents_data_id: str,
    bearer_token: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    Delete a chunk (document data) by documentsDataId on the target environment.
    """
    url = f"{base_url.rstrip('/')}/beegen-portal-be/document/delete-data"
    
    params = {
        "botId": bot_id,
    }
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en",
        "authorization": f"Bearer {bearer_token}",
        "content-type": "application/json",
        "origin": base_url.rstrip('/'),
        "clientmessageid": str(uuid.uuid4()),
        "priority": "u=1, i",
        "referer": f"{base_url.rstrip('/')}/chatbot/{bot_id}/documents",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "user-agent": "Mozilla/5.0",
    }
    
    payload = {
        "documentsDataId": documents_data_id
    }
    
    # Acquire semaphore to limit concurrency
    async with sem:
        async with session.delete(url, params=params, headers=headers, json=payload, timeout=timeout) as response:
            if response.status == 401:
                raise RuntimeError("❌ 401 Unauthorized – Token expired or missing BOT permissions")
            if response.status == 403:
                raise RuntimeError("❌ 403 Forbidden – Missing role BOT_ADMIN / DATA_WORKER")
            
            response.raise_for_status()
            return await response.json()

async def target_create_chunk(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    base_url: str,
    bot_id: str,
    document_id: str,
    content: str,
    index: int,
    bearer_token: str,
):
    """
    Create a single chunk (document data) for a document on the target environment.
    """
    url = f"{base_url.rstrip('/')}/beegen-portal-be/document/create-data"
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en",
        "authorization": f"Bearer {bearer_token}",
        "clientmessageid": str(uuid.uuid4()),
        "content-type": "application/json",
        "origin": base_url.rstrip('/'),
        "referer": f"{base_url.rstrip('/')}/chatbot/{bot_id}/documents/{document_id}",
        "user-agent": "Mozilla/5.0"
    }
    
    payload = {
        "botId": bot_id,
        "documentId": document_id,
        "content": content,
        "index": index
    }
    
    # Acquire semaphore to limit concurrency
    async with sem:
        async with session.post(url, headers=headers, json=payload, timeout=30) as response:
            response.raise_for_status()
            return await response.json()

async def sync_single_document(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    source_base_url: str,
    target_base_url: str,
    source_bot_id: str,
    target_bot_id: str,
    source_token: str,
    target_token: str,
    source_doc: Dict[str, Any],
    target_doc: Dict[str, Any],
    dry_run: bool
):
    """
    Logic to sync chunks for ONE specific document pair.
    """
    doc_name = source_doc.get('docName')
    mode_str = "[DRY-RUN]" if dry_run else "[APPLY]"
    
    logger.info(f"{mode_str} Processing document: '{doc_name}' (Target Doc ID: {target_doc['id']})")
    
    # 1. Get Chunks (Data) - Fetch both source and target concurrently
    try:
        target_task = get_chunk_by_document_id(
            session, target_base_url, target_doc['id'], target_bot_id, target_token
        )
        source_task = get_chunk_by_document_id(
            session, source_base_url, source_doc['id'], source_bot_id, source_token
        )
        
        target_chunks_resp, source_chunks_resp = await asyncio.gather(target_task, source_task)
        
        target_chunks = target_chunks_resp.get('data', {}).get('documentsDataList', [])
        source_chunks = source_chunks_resp.get('data', {}).get('documentsDataList', [])
        
        logger.info(f"   -> Source has {len(source_chunks)} chunks.")
        logger.info(f"   -> Target has {len(target_chunks)} chunks.")
    except Exception as e:
        logger.error(f"   -> Error fetching chunks for '{doc_name}': {e}")
        return

    # 2. Delete existing chunks in Target
    logger.info(f"   {mode_str} Deleting {len(target_chunks)} chunks in target...")
    
    delete_tasks = []
    for chunk in target_chunks:
        if dry_run:
            logger.info(f"     [DRY-RUN] Would delete chunk ID: {chunk['id']}")
        else:
            delete_tasks.append(
                target_delete_chunk(
                    session, sem, target_base_url, target_bot_id, chunk['id'], target_token
                )
            )
            
    if not dry_run and delete_tasks:
        try:
            results = await asyncio.gather(*delete_tasks, return_exceptions=True)
            for chunk, res in zip(target_chunks, results):
                if isinstance(res, Exception):
                    logger.error(f"     [ERROR] Failed to delete chunk {chunk['id']}: {res}")
                else:
                    logger.info(f"     [APPLY] Deleted chunk ID: {chunk['id']}")
        except Exception as e:
            logger.error(f"     [ERROR] Bulk delete failed: {e}")

    # 3. Create new chunks in Target from Source
    logger.info(f"   {mode_str} Creating {len(source_chunks)} new chunks in target...")
    
    create_tasks = []
    for i, chunk in enumerate(source_chunks):
        new_content = chunk.get('content', '')
        
        if dry_run:
            logger.info(f"     [DRY-RUN] Would create chunk index {i}: '{new_content[:50]}...'")
        else:
            create_tasks.append(
                target_create_chunk(
                    session, sem, target_base_url, target_bot_id, target_doc['id'], 
                    new_content, i, target_token
                )
            )
            
    if not dry_run and create_tasks:
        try:
            results = await asyncio.gather(*create_tasks, return_exceptions=True)
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    logger.error(f"     [ERROR] Failed to create chunk index {i}: {res}")
                else:
                    logger.info(f"     [APPLY] Created chunk index {i}")
        except Exception as e:
            logger.error(f"     [ERROR] Bulk create failed: {e}")
            
    logger.info(f"   {mode_str} Finished processing document '{doc_name}'.\n")

async def sync_manager(
    source_base_url: str,
    target_base_url: str,
    source_bot_id: str,
    target_bot_id: str,
    source_token: str,
    target_token: str,
    doc_name: str,
    dry_run: bool = True,
    concurrency: int = 10
):
    """
    Manager function to identify which documents to sync and then call sync_single_document.
    """
    logger.info(f"--- Starting Sync Process (Async) ---")
    logger.info(f"Source: {source_base_url} (Bot: {source_bot_id})")
    logger.info(f"Target: {target_base_url} (Bot: {target_bot_id})")
    
    # Initialize shared Semaphore and Session
    sem = asyncio.Semaphore(concurrency)
    
    async with aiohttp.ClientSession() as session:
        # 1. Get All Source Documents
        try:
            response_source = await get_documents_by_bot_id(session, source_base_url, source_bot_id, source_token)
            source_docs = response_source.get('data', {}).get('content', [])
            logger.info(f"Fetched {len(source_docs)} source documents.")
        except Exception as e:
            logger.error(f"Failed to fetch source documents: {e}")
            return

        # 2. Get All Target Documents
        try:
            response_target = await get_documents_by_bot_id(session, target_base_url, target_bot_id, target_token)
            target_docs = response_target.get('data', {}).get('content', [])
            logger.info(f"Fetched {len(target_docs)} target documents.")
        except Exception as e:
            logger.error(f"Failed to fetch target documents: {e}")
            return

        # 3. Identify Documents to Sync
        docs_to_process = [] # List of tuples (source_doc, target_doc)
        
        if doc_name:
            # Filter for a specific document
            logger.info(f"Filter applied: Searching for document '{doc_name}'...")
            target_document = next((doc for doc in target_docs if doc.get('docName') == doc_name), None)
            source_document = next((doc for doc in source_docs if doc.get('docName') == doc_name), None)
            
            if not target_document:
                logger.warning(f"Document '{doc_name}' not found in Target Bot.")
            elif not source_document:
                logger.warning(f"Document '{doc_name}' not found in Source Bot.")
            else:
                docs_to_process.append((source_document, target_document))
        else:
            # Filter for ALL matching documents
            logger.info("No doc_name provided. Matching ALL documents common to Source and Target...")
            
            target_map = {doc.get('docName'): doc for doc in target_docs if doc.get('docName')}
            matched_names = set()

            for s_doc in source_docs:
                name = s_doc.get('docName')
                if name and name in target_map:
                    t_doc = target_map[name]
                    docs_to_process.append((s_doc, t_doc))
                    matched_names.add(name)

            # --- LOGGING UNSYNCED DOCUMENTS ---
            
            # 1. Documents present in Source but MISSING in Target
            source_names = {doc.get('docName') for doc in source_docs if doc.get('docName')}
            missing_in_target = source_names - matched_names
            if missing_in_target:
                logger.warning(f"⚠️ [SKIP] {len(missing_in_target)} documents found in Source but MISSING in Target: {', '.join(sorted(missing_in_target))}")

            # 2. Documents present in Target but MISSING in Source (Extra context)
            target_names = set(target_map.keys())
            missing_in_source = target_names - matched_names
            if missing_in_source:
                logger.info(f"ℹ️ [SKIP] {len(missing_in_source)} documents found in Target but MISSING in Source: {', '.join(sorted(missing_in_source))}")

        if not docs_to_process:
            logger.warning("No matching documents found to sync.")
            return

        logger.info(f"Found {len(docs_to_process)} document(s) common to both bots to sync.")
        logger.info("------------------------------------------------")

        # 4. Iterate and Sync
        for s_doc, t_doc in docs_to_process:
            await sync_single_document(
                session,
                sem,
                source_base_url, target_base_url,
                source_bot_id, target_bot_id,
                source_token, target_token,
                s_doc, t_doc,
                dry_run
            )

async def main():
    # Define arguments
    parser = argparse.ArgumentParser(description="Sync document chunks between bots (Async).")
    
    # Default values (from original script)
    #FIXME
    DEFAULT_SOURCE_BOT = 'dfb5a874-b980-4275-bd34-0ddbd1acefdf'
    DEFAULT_TARGET_BOT = 'b8c30970-c720-43c7-9dc5-11bbd326d135'
    
    # (Tokens kept truncated for brevity, ensure you use the full tokens from your original script)
    #FIXME
    DEFAULT_SOURCE_TOKEN = "REPLACE_WITH_LOCAL_SECRET" 
    DEFAULT_TARGET_TOKEN = "REPLACE_WITH_LOCAL_SECRET"
    
    #FIXME
    DEFAULT_SOURCE_URL = "https://beegen-portal-dev.mbbank.com.vn"
    DEFAULT_TARGET_URL = "https://beegen-portal.mbbank.com.vn"
    
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_BOT, help="Source Bot ID")
    parser.add_argument("--target-id", default=DEFAULT_TARGET_BOT, help="Target Bot ID")
    parser.add_argument("--source-token", required=False, default=DEFAULT_SOURCE_TOKEN, help="Source Bearer Token")
    parser.add_argument("--target-token", required=False, default=DEFAULT_TARGET_TOKEN, help="Target Bearer Token")
    
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL, help="Source Environment Base URL")
    parser.add_argument("--target-url", default=DEFAULT_TARGET_URL, help="Target Environment Base URL")
    
    parser.add_argument("--doc-name", default="", help="Document name to sync. Leave empty to sync all matching documents.")
    
    parser.add_argument("--apply", action="store_true", help="Execute the changes (Apply). If omitted, runs in Dry-Run mode.")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent chunk operations.")

    args = parser.parse_args()
    
    is_dry_run = not args.apply
    
    await sync_manager(
        source_base_url=args.source_url,
        target_base_url=args.target_url,
        source_bot_id=args.source_id,
        target_bot_id=args.target_id,
        source_token=args.source_token,
        target_token=args.target_token,
        doc_name=args.doc_name,
        dry_run=is_dry_run,
        concurrency=args.concurrency
    )

if __name__ == "__main__":
    asyncio.run(main())
