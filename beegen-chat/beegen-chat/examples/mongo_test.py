if __name__ == "__main__":
    from beegenerate.configs import InfraConfig
    infra_conf = InfraConfig.default()
    from beegenerate.storage.mongodb import MongoStorage
    print(infra_conf.mongo.uri)
    mongodb = MongoStorage(config=infra_conf.mongo)
    records = mongodb.find(collection_name="botinfo", query = {"metadata": {"$exists": True}}) 
    
    for r in records:
        print(r['metadata'])
        print()