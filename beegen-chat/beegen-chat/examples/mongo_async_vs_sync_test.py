import asyncio
import time
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import statistics
from urllib.parse import quote_plus

class MongoConfig:
    def __init__(self):
        self.username = "nlpdev"
        self.password = "REPLACE_WITH_LOCAL_SECRET"
        self.host = "10.215.107.53"
        self.port = "27017"
        self.auth_source = "aicenter_chatbot"
        self.direct_connection = True
        self.app_name = "MongoDBCompass"
        
    @property
    def uri(self) -> str:
        return (
            f"mongodb://{quote_plus(self.username)}:{quote_plus(self.password)}"
            f"@{self.host}:{self.port}"
            f"/?authSource={self.auth_source}"
            f"&directConnection={str(self.direct_connection).lower()}"
            f"&appName={quote_plus(self.app_name)}"
        )

class PerformanceComparison:
    def __init__(self):
        self.config = MongoConfig()
        self.db_name = "aicenter_chatbot"
        self.collection_name = "performance_test"
        
        # Sync client
        self.sync_client = MongoClient(
            self.config.uri,
            maxPoolSize=100,
            minPoolSize=20
        )
        self.sync_db = self.sync_client[self.db_name]
        self.sync_collection = self.sync_db[self.collection_name]
        
        # Async client
        self.async_client = AsyncIOMotorClient(
            self.config.uri,
            maxPoolSize=100,
            minPoolSize=20
        )
        self.async_db = self.async_client[self.db_name]
        self.async_collection = self.async_db[self.collection_name]

    def sync_insert_many(self, num_docs):
        docs = [{"index": i, "value": f"test_{i}", "timestamp": time.time()} for i in range(num_docs)]
        start_time = time.time()
        self.sync_collection.insert_many(docs)
        end_time = time.time()
        return end_time - start_time

    async def async_insert_many(self, num_docs):
        docs = [{"index": i, "value": f"test_{i}", "timestamp": time.time()} for i in range(num_docs)]
        start_time = time.time()
        await self.async_collection.insert_many(docs)
        end_time = time.time()
        return end_time - start_time

    def sync_find_many(self, num_queries):
        start_time = time.time()
        for i in range(num_queries):
            list(self.sync_collection.find({"index": {"$lt": 100}}).limit(100))
        end_time = time.time()
        return end_time - start_time

    async def async_find_many(self, num_queries):
        start_time = time.time()
        tasks = []
        for i in range(num_queries):
            task = self.async_collection.find({"index": {"$lt": 100}}).limit(100).to_list(length=100)
            tasks.append(task)
        await asyncio.gather(*tasks)
        end_time = time.time()
        return end_time - start_time

    async def run_benchmark(self):
        try:
            print("Connecting to MongoDB...")
            # Test connection
            await self.async_client.server_info()
            print("Successfully connected to MongoDB")
            
            # Clean up before starting
            await self.async_collection.delete_many({})
            
            # Test parameters
            num_docs = 1000  # Number of documents to insert
            num_queries = 100  # Number of queries to perform
            num_iterations = 5  # Number of times to repeat each test
            
            print(f"\nRunning benchmark with {num_docs} documents and {num_queries} queries...")
            print(f"Each test will be run {num_iterations} times.")
            
            # Insert benchmarks
            sync_insert_times = []
            async_insert_times = []
            
            for i in range(num_iterations):
                print(f"\nIteration {i+1}/{num_iterations}")
                
                # Clean up
                await self.async_collection.delete_many({})
                
                # Sync insert
                print("Running sync insert test...")
                sync_time = self.sync_insert_many(num_docs)
                sync_insert_times.append(sync_time)
                print(f"Sync insert time: {sync_time:.3f}s")
                
                # Clean up
                await self.async_collection.delete_many({})
                
                # Async insert
                print("Running async insert test...")
                async_time = await self.async_insert_many(num_docs)
                async_insert_times.append(async_time)
                print(f"Async insert time: {async_time:.3f}s")
            
            # Query benchmarks
            # First insert test data
            await self.async_collection.delete_many({})
            await self.async_insert_many(num_docs)
            
            sync_query_times = []
            async_query_times = []
            
            for i in range(num_iterations):
                print(f"\nIteration {i+1}/{num_iterations}")
                
                # Sync queries
                print("Running sync query test...")
                sync_time = self.sync_find_many(num_queries)
                sync_query_times.append(sync_time)
                print(f"Sync query time: {sync_time:.3f}s")
                
                # Async queries
                print("Running async query test...")
                async_time = await self.async_find_many(num_queries)
                async_query_times.append(async_time)
                print(f"Async query time: {async_time:.3f}s")
            
            # Print results
            print("\nFinal Results:")
            print("\nInsert Operations:")
            print(f"Sync Average: {statistics.mean(sync_insert_times):.3f}s")
            print(f"Sync Min: {min(sync_insert_times):.3f}s")
            print(f"Sync Max: {max(sync_insert_times):.3f}s")
            print(f"Async Average: {statistics.mean(async_insert_times):.3f}s")
            print(f"Async Min: {min(async_insert_times):.3f}s")
            print(f"Async Max: {max(async_insert_times):.3f}s")
            print(f"Improvement: {(statistics.mean(sync_insert_times)/statistics.mean(async_insert_times)-1)*100:.1f}%")
            
            print("\nQuery Operations:")
            print(f"Sync Average: {statistics.mean(sync_query_times):.3f}s")
            print(f"Sync Min: {min(sync_query_times):.3f}s")
            print(f"Sync Max: {max(sync_query_times):.3f}s")
            print(f"Async Average: {statistics.mean(async_query_times):.3f}s")
            print(f"Async Min: {min(async_query_times):.3f}s")
            print(f"Async Max: {max(async_query_times):.3f}s")
            print(f"Improvement: {(statistics.mean(sync_query_times)/statistics.mean(async_query_times)-1)*100:.1f}%")

        except Exception as e:
            print(f"Error during benchmark: {str(e)}")
        finally:
            # Cleanup
            try:
                await self.async_collection.delete_many({})
                self.sync_client.close()
                self.async_client.close()
            except Exception as e:
                print(f"Error during cleanup: {str(e)}")

# Run the benchmark
if __name__ == "__main__":
    comparison = PerformanceComparison()
    asyncio.run(comparison.run_benchmark())