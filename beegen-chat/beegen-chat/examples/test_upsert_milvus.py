from beegenerate.vectordb.milvus_v2 import MilvusExecutor
from beegenerate.configs import MilvusConfig, MilvusOperation

async def test_upsert_operations():
    """A comprehensive test for Milvus upsert operations with randomly generated data."""
    import numpy as np
    import random
    import string
    import time
    import asyncio
    from datetime import datetime
    
    # Create MilvusExecutor instance
    milvus_exec = MilvusExecutor(MilvusConfig.default())
    
    # Test collection name with timestamp to ensure uniqueness
    timestamp = int(time.time())
    test_collection = f"upsert_test_collection_{timestamp}"
    vector_dim = 128
    
    print("\n" + "="*80)
    print(f"STARTING MILVUS UPSERT TEST SUITE ON COLLECTION: {test_collection}")
    print("="*80)
    
    # STEP 1: Create a test collection
    print("\n1. Creating test collection...")
    create_response = await milvus_exec.run(
        operation=MilvusOperation.CREATE_COLLECTION,
        params={
            "collection_name": test_collection,
            "fields": [
                {"name": "id", "type": "int", "is_primary": True},
                {"name": "vector", "type": "vector", "params": {"dim": vector_dim}},
                {"name": "text", "type": "varchar", "params": {"max_length": 512}},
                {"name": "score", "type": "float"},
                {"name": "timestamp", "type": "int64"},
                {"name": "category", "type": "varchar", "params": {"max_length": 64}},
                {"name": "is_valid", "type": "bool"}
            ],
            "description": "Test collection for Milvus upsert operations"
        }
    )
    if not create_response['success']:
        print(f"Failed to create collection: {create_response['error']}")
        return
    print(f"Collection created: {test_collection}")
    
    # STEP 2: Create index on vector field
    print("\n2. Creating index on vector field...")
    index_response = await milvus_exec.run(
        operation=MilvusOperation.CREATE_INDEX,
        params={
            "collection_name": test_collection,
            "field_name": "vector",
            "index_params": {
                "metric_type": "L2",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
        }
    )
    if not index_response['success']:
        print(f"Failed to create index: {index_response['error']}")
        return
    print("Index created successfully")
    
    # STEP 3: Load collection into memory
    print("\n3. Loading collection into memory...")
    load_response = await milvus_exec.run(
        operation=MilvusOperation.LOAD_COLLECTION,
        params={
            "collection_name": test_collection
        }
    )
    if not load_response['success']:
        print(f"Failed to load collection: {load_response['error']}")
        return
    print("Collection loaded successfully")
    
    # Helper function to generate random text
    def generate_random_text(length=10):
        return ''.join(random.choice(string.ascii_letters + string.digits + ' ') for _ in range(length))
    
    # Helper function to generate random category
    def generate_random_category():
        categories = ["electronics", "fashion", "books", "sports", "home", "beauty", "toys", "automotive", "grocery", "office"]
        return random.choice(categories)
    
    # STEP 4: Insert initial batch of data
    print("\n4. Inserting initial batch of data...")
    num_initial_entities = 50
    initial_ids = list(range(100, 100 + num_initial_entities))
    
    initial_data = [
        {
            "id": id_val,
            "vector": np.random.rand(vector_dim).tolist(),
            "text": f"Original text {id_val}: {generate_random_text(20)}",
            "score": float(np.random.random() * 100),
            "timestamp": int(time.time()),
            "category": generate_random_category(),
            "is_valid": random.choice([True, False])
        }
        for id_val in initial_ids
    ]
    
    insert_response = await milvus_exec.run(
        operation=MilvusOperation.INSERT,
        params={
            "collection_name": test_collection,
            "data": initial_data
        }
    )
    if not insert_response['success']:
        print(f"Failed to insert data: {insert_response['error']}")
        return
    print(f"Inserted {insert_response['result'].insert_count} entities")
    
    # STEP 5: Flush data to make it searchable
    print("\n5. Flushing collection...")
    flush_response = await milvus_exec.run(
        operation=MilvusOperation.FLUSH,
        params={
            "collection_name": test_collection
        }
    )
    if not flush_response['success']:
        print(f"Failed to flush collection: {flush_response['error']}")
        return
    print("Collection flushed successfully")
    
    # Wait for flush to complete
    await asyncio.sleep(2)
    
    # STEP 6: Check initial data
    print("\n6. Verifying initial data insertion...")
    initial_query_response = await milvus_exec.run(
        operation=MilvusOperation.QUERY,
        params={
            "collection_name": test_collection,
            "expr": f"id in {initial_ids[:5]}",  # Query a few records as sample
            "output_fields": ["id", "text", "score", "category", "is_valid"]
        }
    )
    if not initial_query_response['success']:
        print(f"Failed to query initial data: {initial_query_response['error']}")
        return
    print(f"Initial data verification: {len(initial_query_response['result'])} entities found")
    for entity in initial_query_response['result'][:3]:  # Display first 3 for brevity
        print(f"  ID={entity['id']}, Text={entity['text'][:30]}..., Category={entity['category']}")
    
    # STEP 7: Prepare upsert data - mix of updates and new records
    print("\n7. Preparing upsert data...")
    # Randomly select 50% of initial IDs to update
    update_ids = random.sample(initial_ids, len(initial_ids) // 2)
    
    # Generate new IDs (not in the initial set)
    new_ids = list(range(500, 550))
    
    # Combine both for upsert operation
    upsert_ids = update_ids + new_ids
    random.shuffle(upsert_ids)  # Shuffle to mix updates and inserts
    
    print(f"Preparing to upsert {len(upsert_ids)} entities ({len(update_ids)} updates, {len(new_ids)} inserts)")
    print(f"Sample update IDs: {update_ids[:5]}")
    print(f"Sample new IDs: {new_ids[:5]}")
    
    # Generate upsert data
    upsert_data = [
        {
            "id": id_val,
            "vector": np.random.rand(vector_dim).tolist(),
            "text": f"{'Updated' if id_val in update_ids else 'New'} text {id_val}: {generate_random_text(30)}",
            "score": float(np.random.random() * 200),  # Different range to clearly see changes
            "timestamp": int(time.time()),
            "category": generate_random_category(),
            "is_valid": random.choice([True, False])
        }
        for id_val in upsert_ids
    ]
    
    # STEP 8: Perform upsert operation
    print("\n8. Performing upsert operation...")
    upsert_response = await milvus_exec.run(
        operation=MilvusOperation.UPSERT,
        params={
            "collection_name": test_collection,
            "data": upsert_data
        }
    )
    if not upsert_response['success']:
        print(f"Failed to upsert data: {upsert_response['error']}")
        if 'traceback' in upsert_response:
            print(f"Error traceback: {upsert_response['traceback']}")
        return
    print(f"Upsert completed successfully - affected {upsert_response['result'].upsert_count} entities")
    
    # Flush again to ensure data is searchable
    await milvus_exec.run(
        operation=MilvusOperation.FLUSH,
        params={
            "collection_name": test_collection
        }
    )
    
    # Wait for flush to complete
    await asyncio.sleep(2)
    
    # STEP 9: Verify updated records
    print("\n9. Verifying updated records...")
    updated_query_response = await milvus_exec.run(
        operation=MilvusOperation.QUERY,
        params={
            "collection_name": test_collection,
            "expr": f"id in {update_ids[:10]}",  # Check a sample of updated records
            "output_fields": ["id", "text", "score", "category", "is_valid"]
        }
    )
    if not updated_query_response['success']:
        print(f"Failed to query updated data: {updated_query_response['error']}")
        return
    
    print(f"Updated records verification: {len(updated_query_response['result'])} entities found")
    for entity in updated_query_response['result'][:5]:  # Display first 5 for brevity
        print(f"  ID={entity['id']}, Text={entity['text'][:30]}..., Score={entity['score']:.2f}")
        # Verify text starts with "Updated"
        if not entity['text'].startswith("Updated"):
            print(f"  WARNING: Record ID={entity['id']} doesn't appear to be updated!")
    
    # STEP 10: Verify new records
    print("\n10. Verifying newly inserted records...")
    new_query_response = await milvus_exec.run(
        operation=MilvusOperation.QUERY,
        params={
            "collection_name": test_collection,
            "expr": f"id in {new_ids[:10]}",  # Check a sample of new records
            "output_fields": ["id", "text", "score", "category", "is_valid"]
        }
    )
    if not new_query_response['success']:
        print(f"Failed to query new data: {new_query_response['error']}")
        return
    
    print(f"New records verification: {len(new_query_response['result'])} entities found")
    for entity in new_query_response['result'][:5]:  # Display first 5 for brevity
        print(f"  ID={entity['id']}, Text={entity['text'][:30]}..., Score={entity['score']:.2f}")
        # Verify text starts with "New"
        if not entity['text'].startswith("New"):
            print(f"  WARNING: Record ID={entity['id']} doesn't appear to be a new record!")
    
    # STEP 11: Check total entity count
    print("\n11. Checking total entity count after upsert...")
    stats_response = await milvus_exec.run(
        operation=MilvusOperation.GET_COLLECTION_STATS,
        params={
            "collection_name": test_collection
        }
    )
    if not stats_response['success']:
        print(f"Failed to get collection stats: {stats_response['error']}")
        return
    
    total_entities = stats_response['result']['vector_count']
    expected_count = len(initial_ids) + len(new_ids)  # Updates don't change count
    print(f"Total entities in collection: {total_entities}")
    print(f"Expected entities: {expected_count}")
    print(f"Difference: {total_entities - expected_count}")
    
    # STEP 12: Perform search to verify vector updates
    print("\n12. Testing search functionality on updated vectors...")
    # Pick a random upserted item's vector for search
    random_upsert_item = random.choice(upsert_data)
    query_vector = random_upsert_item["vector"]
    query_id = random_upsert_item["id"]
    
    search_response = await milvus_exec.run(
        operation=MilvusOperation.SEARCH,
        params={
            "collection_name": test_collection,
            "query_vectors": [query_vector],
            "top_k": 5,
            "output_fields": ["id", "text", "score", "category"],
            "metric_type": "L2"
        }
    )
    if not search_response['success']:
        print(f"Failed to search: {search_response['error']}")
        return
    
    print(f"Search results for vector of ID {query_id}:")
    for i, hit in enumerate(search_response['result'][0]):
        print(f"  Result {i+1}: ID={hit['id']}, Distance={hit['distance']:.4f}")
        # The first result should be the exact vector we searched for
        if i == 0 and hit['id'] != query_id:
            print(f"  WARNING: First search result should be ID={query_id}, but got ID={hit['id']}")
    
    # STEP 13: Test batch upsert with mixed operations
    print("\n13. Testing batch upsert with mixed operations...")
    
    # Create a complex batch with:
    # - Some complete updates (all fields)
    # - Some partial updates (only some fields)
    # - Some new insertions
    
    # Complete updates
    complete_update_ids = random.sample(initial_ids, 10)
    
    # Partial updates - only update text and score
    partial_update_ids = random.sample([id for id in initial_ids if id not in complete_update_ids], 10)
    
    # New insertions
    new_batch_ids = list(range(1000, 1020))
    
    # Prepare complete updates
    complete_updates = [
        {
            "id": id_val,
            "vector": np.random.rand(vector_dim).tolist(),
            "text": f"Complete update {id_val}: {generate_random_text(25)}",
            "score": float(np.random.random() * 300),
            "timestamp": int(time.time()),
            "category": generate_random_category(),
            "is_valid": random.choice([True, False])
        }
        for id_val in complete_update_ids
    ]
    
    # Prepare partial updates - only include some fields
    partial_updates = [
        {
            "id": id_val,
            "vector": np.random.rand(vector_dim).tolist(),  # Vector field is required
            "text": f"Partial update {id_val}: {generate_random_text(25)}",
            "score": float(np.random.random() * 300),
            "timestamp": int(time.time()),  # Include timestamp field
            "category": generate_random_category(),  # Include category field
            "is_valid": random.choice([True, False])  # Include is_valid field
        }
        for id_val in partial_update_ids
    ]
    
    # Prepare new insertions
    new_insertions = [
        {
            "id": id_val,
            "vector": np.random.rand(vector_dim).tolist(),
            "text": f"Batch new {id_val}: {generate_random_text(25)}",
            "score": float(np.random.random() * 300),
            "timestamp": int(time.time()),
            "category": generate_random_category(),
            "is_valid": random.choice([True, False])
        }
        for id_val in new_batch_ids
    ]
    
    # Combine all for batch upsert
    batch_upsert_data = complete_updates + partial_updates + new_insertions
    random.shuffle(batch_upsert_data)  # Mix the operations
    
    print(f"Preparing batch upsert with {len(batch_upsert_data)} entities:")
    print(f"  - {len(complete_updates)} complete updates")
    print(f"  - {len(partial_updates)} partial updates")
    print(f"  - {len(new_insertions)} new insertions")
    
    # Perform batch upsert
    batch_upsert_response = await milvus_exec.run(
        operation=MilvusOperation.UPSERT,
        params={
            "collection_name": test_collection,
            "data": batch_upsert_data
        }
    )
    if not batch_upsert_response['success']:
        print(f"Failed to perform batch upsert: {batch_upsert_response['error']}")
        if 'traceback' in batch_upsert_response:
            print(f"Error traceback: {batch_upsert_response['traceback']}")
        return
    print(f"Batch upsert completed successfully - affected {batch_upsert_response['result'].upsert_count} entities")
    
    # Flush again
    await milvus_exec.run(
        operation=MilvusOperation.FLUSH,
        params={
            "collection_name": test_collection
        }
    )
    
    # Wait for flush to complete
    await asyncio.sleep(2)
    
    # STEP 14: Verify batch updates
    print("\n14. Verifying batch update results...")
    
    # Check partial updates
    partial_query_response = await milvus_exec.run(
        operation=MilvusOperation.QUERY,
        params={
            "collection_name": test_collection,
            "expr": f"id in {partial_update_ids[:5]}",
            "output_fields": ["id", "text", "score", "category", "is_valid"]
        }
    )
    if not partial_query_response['success']:
        print(f"Failed to query partial updates: {partial_query_response['error']}")
        return
    
    print(f"Partial update verification: {len(partial_query_response['result'])} entities found")
    for entity in partial_query_response['result']:
        print(f"  ID={entity['id']}, Text={entity['text'][:30]}..., Score={entity['score']:.2f}")
        # Verify text starts with "Partial update"
        if not entity['text'].startswith("Partial update"):
            print(f"  WARNING: Record ID={entity['id']} doesn't appear to be partially updated!")
    
    # STEP 15: Test upsert error handling
    print("\n15. Testing upsert error handling with invalid data...")
    
    # For a more controlled error test, try to upsert with an invalid collection name
    invalid_collection = f"{test_collection}_nonexistent"
    
    valid_data = [
        {
            "id": 2000,
            "vector": np.random.rand(vector_dim).tolist(),
            "text": "Valid entity data",
            "score": 99.9,
            "timestamp": int(time.time()),
            "category": "test",
            "is_valid": True
        }
    ]
    
    invalid_upsert_response = await milvus_exec.run(
        operation=MilvusOperation.UPSERT,
        params={
            "collection_name": invalid_collection,
            "data": valid_data
        }
    )
    
    if not invalid_upsert_response['success']:
        print(f"As expected, invalid upsert failed with error:")
        print(f"  {invalid_upsert_response['error']}")
    else:
        print(f"WARNING: Invalid upsert succeeded when it should have failed")
    
    # STEP 16: Clean up - drop test collection
    print("\n16. Cleaning up - dropping test collection...")
    await milvus_exec.run(
        operation=MilvusOperation.RELEASE_COLLECTION,
        params={
            "collection_name": test_collection
        }
    )
    
    drop_response = await milvus_exec.run(
        operation=MilvusOperation.DROP_COLLECTION,
        params={
            "collection_name": test_collection
        }
    )
    if not drop_response['success']:
        print(f"Failed to drop collection: {drop_response['error']}")
        return
    print(f"Collection {test_collection} dropped successfully")
    
    print("\n" + "="*80)
    print("MILVUS UPSERT TEST COMPLETED SUCCESSFULLY")
    print("="*80)


# Function to run performance test for upsert
async def test_upsert_performance():
    """Test the performance of upsert operations with varying batch sizes."""
    import numpy as np
    import random
    import time
    import asyncio
    from datetime import datetime
    
    # Create MilvusExecutor instance
    milvus_exec = MilvusExecutor(MilvusConfig.default())
    
    # Test collection name with timestamp
    timestamp = int(time.time())
    test_collection = f"upsert_perf_test_{timestamp}"
    vector_dim = 128
    
    print("\n" + "="*80)
    print(f"STARTING MILVUS UPSERT PERFORMANCE TEST ON COLLECTION: {test_collection}")
    print("="*80)
    
    # Create test collection
    create_response = await milvus_exec.run(
        operation=MilvusOperation.CREATE_COLLECTION,
        params={
            "collection_name": test_collection,
            "fields": [
                {"name": "id", "type": "int", "is_primary": True},
                {"name": "vector", "type": "vector", "params": {"dim": vector_dim}},
                {"name": "text", "type": "varchar", "params": {"max_length": 256}},
                {"name": "score", "type": "float"}
            ],
            "description": "Performance test collection for Milvus upsert operations"
        }
    )
    if not create_response['success']:
        print(f"Failed to create collection: {create_response['error']}")
        return
    
    # Create index
    await milvus_exec.run(
        operation=MilvusOperation.CREATE_INDEX,
        params={
            "collection_name": test_collection,
            "field_name": "vector",
            "index_params": {
                "metric_type": "L2",
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
        }
    )
    
    # Load collection
    await milvus_exec.run(
        operation=MilvusOperation.LOAD_COLLECTION,
        params={
            "collection_name": test_collection
        }
    )
    
    # Helper function to generate random entities
    def generate_entities(start_id, count):
        return [
            {
                "id": start_id + i,
                "vector": np.random.rand(vector_dim).tolist(),
                "text": f"Entity {start_id + i}",
                "score": float(np.random.random() * 100)
            }
            for i in range(count)
        ]
    
    # Initial data insertion
    initial_count = 1000
    print(f"\nInserting initial {initial_count} entities...")
    initial_data = generate_entities(1, initial_count)
    
    start_time = time.time()
    insert_response = await milvus_exec.run(
        operation=MilvusOperation.INSERT,
        params={
            "collection_name": test_collection,
            "data": initial_data
        }
    )
    insert_time = time.time() - start_time
    
    if not insert_response['success']:
        print(f"Failed to insert initial data: {insert_response['error']}")
        return
    
    print(f"Initial insert: {insert_time:.2f} seconds for {initial_count} entities")
    print(f"Rate: {initial_count/insert_time:.2f} entities per second")
    
    # Flush to make sure data is persisted
    await milvus_exec.run(
        operation=MilvusOperation.FLUSH,
        params={"collection_name": test_collection}
    )
    await asyncio.sleep(2)
    
    # Test upsert with different batch sizes
    batch_sizes = [10, 100, 500, 1000]
    
    for batch_size in batch_sizes:
        print(f"\nTesting upsert with batch size: {batch_size}")
        
        # Create batch with 50% updates and 50% new inserts
        update_count = batch_size // 2
        new_count = batch_size - update_count
        
        # Get random IDs to update
        update_ids = random.sample(range(1, initial_count + 1), update_count)
        
        # Generate new IDs
        new_start_id = initial_count + 1 + batch_size * batch_sizes.index(batch_size)
        
        # Prepare update data
        update_data = [
            {
                "id": id_val,
                "vector": np.random.rand(vector_dim).tolist(),
                "text": f"Updated entity {id_val}",
                "score": float(np.random.random() * 100)
            }
            for id_val in update_ids
        ]
        
        # Prepare new data
        new_data = generate_entities(new_start_id, new_count)
        
        # Combine for upsert
        upsert_data = update_data + new_data
        
        # Perform upsert and measure time
        start_time = time.time()
        upsert_response = await milvus_exec.run(
            operation=MilvusOperation.UPSERT,
            params={
                "collection_name": test_collection,
                "data": upsert_data
            }
        )
        upsert_time = time.time() - start_time
        
        if not upsert_response['success']:
            print(f"Failed to upsert batch: {upsert_response['error']}")
            continue
        
        print(f"Batch upsert: {upsert_time:.2f} seconds for {batch_size} entities")
        print(f"Rate: {batch_size/upsert_time:.2f} entities per second")
        print(f"Affected entities: {upsert_response['result'].upsert_count}")
        
        # Flush after each batch
        await milvus_exec.run(
            operation=MilvusOperation.FLUSH,
            params={"collection_name": test_collection}
        )
        await asyncio.sleep(1)
    
    # Clean up
    await milvus_exec.run(
        operation=MilvusOperation.RELEASE_COLLECTION,
        params={"collection_name": test_collection}
    )
    
    await milvus_exec.run(
        operation=MilvusOperation.DROP_COLLECTION,
        params={"collection_name": test_collection}
    )
    
    print("\n" + "="*80)
    print("MILVUS UPSERT PERFORMANCE TEST COMPLETED")
    print("="*80)


# Run both tests
if __name__ == "__main__":
    import asyncio
    print("Running comprehensive upsert test...")
    asyncio.run(test_upsert_operations())
    
    print("\n\nRunning upsert performance test...")
    asyncio.run(test_upsert_performance())