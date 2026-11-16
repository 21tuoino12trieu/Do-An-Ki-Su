from beegenerate.configs import MilvusConfig
import re
from datetime import datetime
from typing import (
    Any, 
    Dict, 
    List, 
    Optional, 
    Tuple,
    Union
)
from pathlib import Path
from beegenerate.vectordb.base import (
    BaseVectorStore,
    VDBQuery,
    VDBResult,
    VDBStatus,
    VDBRecord
)
from pymilvus import (
    connections,
    Collection,
    utility,
    DataType
)


import numpy as np
import asyncio
from functools import lru_cache

from beegenerate.loggings import LOGGER
from beegenerate.const import BEEGEN_ROOT

from pydantic import Field


def l2_to_cosine(l2_distance, vector_norm=None):
    """
    Convert L2 (Euclidean) distance to Cosine similarity score.
    
    For normalized vectors (unit vectors):
    cosine_similarity = 1 - (l2_distance^2 / 2)
    
    For non-normalized vectors:
    Need to provide the vector_norm (magnitude of vectors)
    
    Args:
        l2_distance (float): L2 distance between vectors
        vector_norm (float, optional): Norm of the vectors if they're not normalized
        
    Returns:
        float: Cosine similarity score in range [-1, 1]
    """
    if vector_norm is None:
        # Assume normalized vectors (unit vectors)
        cosine_similarity = 1 - (l2_distance ** 2) / 2
        # Clip to [-1, 1] range to handle floating point errors
        return np.clip(cosine_similarity, -1.0, 1.0)
    else:
        # For non-normalized vectors
        cosine_similarity = 1 - (l2_distance ** 2) / (2 * (vector_norm ** 2))
        return np.clip(cosine_similarity, -1.0, 1.0)
    

class MilvusStorage(BaseVectorStore):

    def __init__(self, config: MilvusConfig):
        self.config = config
        self._connect()
        
    @classmethod
    def from_path(cls, path: Union[str, Path]) -> 'MilvusStorage':
        """Create a MongoStorage instance from a config file path.
        
        Args:
            path: Path to the mongo config YAML file
            
        Returns:
            MongoStorage: A new instance initialized with the config
        """
        config = MilvusConfig.from_yaml_file(Path(path))
        return cls(config=config)
    
    def _connect(self) -> None:
        """Establish connection to Milvus server."""
        try:
            # Check if connection already exists
            if not connections.has_connection(self.config.alias):
                LOGGER.info(f"Making connect...")
                connections.connect(
                    alias=self.config.alias,
                    uri=self.config.uri,
                    user=self.config.username,
                    password=self.config.password,
                    db_name=self.config.db_name
                )
                LOGGER.info(f"Successfully connected to Milvus at {self.config.uri}")
            else:
                LOGGER.info("Using existing Milvus connection")
        except Exception as e:
            LOGGER.error(f"Failed to connect to Milvus: {str(e.with_traceback)}")
            raise
        
    def _disconnect(self) -> None:
        """Close the connection to Milvus server."""
        try:
            if connections.has_connection(self._connection_alias):
                connections.disconnect(self._connection_alias)
                LOGGER.info("Disconnected from Milvus server")
        except Exception as e:
            LOGGER.error(f"Error disconnecting from Milvus: {str(e)}")
            raise
    
    @lru_cache(maxsize=128)    
    def _load_collection(self, collection_name: str) -> Collection:
        """
        Get a collection by name and load it into memory.
        
        Args:
            collection_name (str): name of the collection
        
        Returns:
            Collection: Loaded collection object
        """
        # LOGGER.info(f"loading collection: {collection_name}")
        collection = Collection(collection_name, using=self.config.alias)
        collection.load()
        return collection

    @lru_cache(maxsize=128)
    def _collection_exists(self, collection_name: str) -> bool:
        return utility.has_collection(collection_name)
     
    def _delete_collection(self, collection_name: str) -> None:
        r"""Deletes an existing collection from the database.
        
        Args:
            collection (str): Name of the collection to be deleted.
        """
        if utility.has_collection(collection_name):
            return utility.drop_collection(collection_name)
        
    def _generate_collection_name(self) -> str:
        r"""Generates a unique name for a new collection based on the current
        timestamp. Milvus collection names can only contain alphanumeric
        characters and underscores.

        Returns:
            str: A unique, valid collection name.
        """
        timestamp = datetime.now().isoformat()
        transformed_name = re.sub(r'[^a-zA-Z0-9_]', '_', timestamp)
        valid_name = "Time" + transformed_name
        return valid_name
    
    @lru_cache(maxsize=128)
    def _verify_collection(self, collection_name: str):
        if not self._collection_exists(collection_name):
            error_msg = f"Not existed collection name: {collection_name}"
            LOGGER.error(error_msg)
            raise ValueError(error_msg)
    
    @lru_cache(maxsize=128)
    def _get_primary_and_vector_fields(self, collection_name: str) -> Tuple[str, str]:
        """Get primary key and indexed vector field names."""
        self._verify_collection(collection_name)
        
        collection = self._load_collection(collection_name)
        
        # Get indexed fields
        indexed_fields = {index.field_name for index in collection.indexes}
        
        pk_field = vector_field = None
        
        # Find fields
        for field in collection.schema.fields:
            if field.is_primary:
                pk_field = field.name
            elif field.dtype == DataType.FLOAT_VECTOR and field.name in indexed_fields:
                vector_field = field.name
                
            if pk_field and vector_field:
                break
        
        if not (pk_field and vector_field):
            raise Exception("Failed to find primary key or indexed vector field")
            
        return pk_field, vector_field
    
    @lru_cache(maxsize=128)
    def _get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """Retrieves details of an existing collection.

        Args:
            collection_name (str): Name of the collection to be checked.

        Returns:
            Dict[str, Any]: A dictionary containing details about the
                collection including:
                - id: the id of the collection
                - vector_count: the number of vectors in the collection
                - vector_dim: the dimension of the vectors
        """
        # Get collection instance
        collection = Collection(collection_name)
        
        # Get number of entities in the collection
        vector_count = collection.num_entities
        
        # Get collection schema information
        collection_schema = collection.schema
        
        
        dim_value = next(
            (
                field.params.get('dim')
                for field in collection_schema.fields
                if field.name == "vector"
            ),
            None,
        )

        return {
            "vector_count": vector_count,
            "vector_dim": dim_value,
        }

    def _convert_record_to_milvus_format(
        self,
        collection_name: str,
        records: List[VDBRecord]
    ) -> List[dict]:
        r"""Validates and converts VectorRecord instances to the format
        expected by Milvus.

        Args:
            records (List[VectorRecord]): List of vector records to validate
            and convert.

        Returns:
            List[dict]: A list of dictionaries formatted for Milvus insertion.
        """
        id_field_name, vector_field_name = self._get_primary_and_vector_fields(collection_name)
        validated_data = []
        
        for record in records:
            record_dict = {
                id_field_name: record.id,
                vector_field_name: record.vector
            }
            
            for field in record.payload:
                record_dict[field] = record.payload[field]            
            validated_data.append(record_dict)
        
        return validated_data
    
    def _convert_milvus_format_to_record(
        self,
        collection_name: str,
        results: List[Dict],
        output_fields: List[str]
    ) -> List[VDBRecord]:
        primary_field, vector_field = self._get_primary_and_vector_fields(collection_name)
        
        formatted_results = []
        for hit in results:
            # Create payload dict with all fields except id and vector
            payload = {}
            for field_name in output_fields:
                if field_name not in [primary_field, vector_field]:
                    field_value = getattr(hit, field_name, None)
                    if field_value is not None:
                        payload[field_name] = field_value
            
            # Create the result dictionary with the required structure                
            vector = None
            if vector_field in output_fields:
                vector = hit.vector
            
            score = hit.score
            
            if self.config.index_params['metric_type'] == "L2":
                score = l2_to_cosine(score)
            
            formatted_results.append(VDBResult.construct(
                similarity=score,
                id=hit.id,
                payload=payload,
                vector=vector
            ))
        
        return formatted_results
        
    def add(
        self,
        collection_name: str,
        records: List[VDBRecord],
        **kwargs
    ) -> None:
        r"""Adds a list of vectors to the specified collection.

        Args:
            records (List[VectorRecord]): List of vectors to be added.
            **kwargs (Any): Additional keyword arguments pass to insert.

        Raises:
            RuntimeError: If there was an error in the addition process.
        """
        self._verify_collection(collection_name)
        
        validated_records = self._convert_record_to_milvus_format(
            collection_name, 
            records
        )
        collection = self._load_collection(collection_name)
        op_info = collection.insert(
            validated_records, 
            **kwargs
        )
        LOGGER.debug(f"Successfully added vectors in Milvus: {op_info}")
        
    def delete(
        self,
        collection_name: str,
        ids: List[str],
        **kwargs: Any,
    ) -> None:
        r"""Deletes a list of vectors identified by their IDs from the
        storage. If unsure of ids you can first query the collection to grab
        the corresponding data.

        Args:
            ids (List[str]): List of unique identifiers for the vectors to be
                deleted.
            **kwargs (Any): Additional keyword arguments passed to delete.

        Raises:
            RuntimeError: If there is an error during the deletion process.
        """
        self._verify_collection(collection_name)
        collection = self._load_collection(collection_name)
        op_info = collection.delete(
            collection_name=collection_name, 
            pks=ids, 
            **kwargs
        )
        LOGGER.debug(f"Successfully deleted vectors in Milvus: {op_info}")
        
    @lru_cache(maxsize=128)
    def status(self, collection_name) -> VDBStatus:
        r"""Retrieves the current status of the Milvus collection. This method
        provides information about the collection, including its vector
        dimensionality and the total number of vectors stored.

        Returns:
            VectorDBStatus: An object containing information about the
                collection's status.
        """
        status = self._get_collection_info(collection_name)
        return VDBStatus(
            vector_dim=status["vector_dim"],
            vector_count=status["vector_count"],
        )
        
    async def search(
        self,
        query_vectors: List[List[float]],
        collection: str,
        top_k: int = Field(default=1, gt=0),
        threshold: float = Field(default=0.0, ge=0),
        output_fields: List[str] = [],
        **kwargs
    ):
        """Async version of _search()"""
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._search(
                query_vectors=query_vectors,
                collection=collection,
                top_k=top_k,
                threshold=threshold,
                output_fields=output_fields,
                **kwargs
            ),
        )
        
    def _search(
        self,
        query_vectors: List[List[float]],
        collection: str,
        top_k: int = Field(default=1, gt=0),
        threshold: float = Field(default=0.0, ge=0),
        output_fields: List[str] = [],
        **kwargs
    ):
        """This method is ported from _run(), but using the variables directly instead of VDBQuery"""
        self._verify_collection(collection)
        
        primary_field, vector_field = self._get_primary_and_vector_fields(collection)
        
        collection = self._load_collection(collection)
        
        # Get all field names from the collection
        field_names = [field.name for field in collection.schema.fields]
        
        if len(output_fields) == 0:
            output_fields = field_names
            
        # check if there are any invalid fields existed
        invalid_fields = [field for field in output_fields if field not in field_names]
        
        if len(invalid_fields) > 0:
            error_msg = f"There follow fields are not supported in output fields: {invalid_fields}"
            LOGGER.error(error_msg)
            raise ValueError(error_msg)
        
        # perform the search with top_k
        search_params = {
            'metric_type': self.config.index_params['metric_type'],
            'params': self.config.search_params
        }
        
        results = collection.search(
            data=query_vectors,
            anns_field=vector_field,
            param=search_params,
            limit=top_k,
            output_fields=output_fields,
            **kwargs
        )
        
        final_results = []
        
        for result in results:
        
            # filter with threshold
            if threshold > 0:
                filtered_result = [hit for hit in result if hit.distance >= threshold][:top_k]
            else:
                filtered_result = result[:top_k]
                    
            final_result = [
                {
                    "id": r.id,
                    "distance": r.distance,
                    **{field: getattr(r, field) for field in output_fields}
                }
                for r in filtered_result
            ]
            final_results.append(final_result)
            
        return final_results
    
    def _run(
        self,
        query: VDBQuery,
        **kwargs: Any
    ) -> List[VDBResult]:
        """Performs similarity search in a vector database collection.

        This method searches for vectors similar to the query vector in the specified
        collection. It validates the collection and requested output fields, applies
        search parameters, and returns formatted results.

        Args:
            query (VDBQuery): Input query object 
            **kwargs (Any): Additional keyword arguments passed directly to the 
                underlying search method

        Returns:
            List[VDBResult]: List of search results, where each result contains the
                requested output fields and similarity scores. Results are ordered
                by similarity to the query vector.
        """
        self._verify_collection(query.collection)
        
        primary_field, vector_field = self._get_primary_and_vector_fields(query.collection)
        
        collection = self._load_collection(query.collection)
        
        # Get all field names from the collection
        field_names = [field.name for field in collection.schema.fields]
        output_fields = query.output_fields
        
        if len(output_fields) == 0:
            output_fields = field_names
        
        # check if there are any invalid fields existed
        invalid_fields = [field for field in output_fields if field not in field_names]
        
        if len(invalid_fields) > 0:
            error_msg = f"These follow fields are not supported in output fields: {invalid_fields}"
            LOGGER.error(error_msg)
            raise ValueError(error_msg)
        
        # perform the search with top_k * 2
        search_params = {
            'metric_type': self.config.index_params['metric_type'],
            'params': self.config.search_params
        }
        
        results = collection.search(
            data=[query.query_vector],
            anns_field=vector_field,
            param=search_params,
            limit=2*query.top_k,
            output_fields=output_fields,
            **kwargs
        )
        
        if len(results) != 1:
            raise ValueError(f"Failed to query with vector: {query}")
        
        results = results[0]
        
        # filter the top_k with threshold
        if query.threshold > 0:
            # threshold existed, process filter
            filtered_results = []
            for hit in results:
                if hit.distance >= query.threshold:
                    filtered_results.append(hit)
            
            filtered_results = filtered_results[: query.top_k] 
        else:
            # no threshold, just trim the top_k
            filtered_results = results[: query.top_k]
                                
        formatted_results = self._convert_milvus_format_to_record(
            collection_name=query.collection,
            results=filtered_results,
            output_fields=output_fields
        )
                
        return formatted_results
    
    async def run(
        self,
        query: VDBQuery,
        **kwargs: Any
    ) -> List[VDBQuery]:
        """Asynchronously performs similarity search in a vector database collection.

        This method provides an asynchronous interface to search for vectors similar to
        the query vector in the specified collection. It handles collection validation,
        output field verification, and result formatting.

        Args:
            query (VDBQuery): Query object
            *kwargs (Any): Additional positional arguments passed to the underlying 
                async search method

        Returns:
            List[VDBQuery]: List of search results, where each result contains the
                requested output fields and similarity scores. Results are ordered
                by similarity to the query vector.
        """
        return await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._run(query=query, **kwargs),
        )
        

async def single_run():
    import numpy as np
    from time import time
    from typing import List
    from tqdm import tqdm
    

    searcher = MilvusStorage(MilvusConfig.default())
    
    # print(searcher._get_collection_info("bot_3457fc85_78a5_424e_881d_25835e88a9c3"))
    
    results = await searcher.search(
        query_vectors=[
            [-0.024514776, -0.021215761, -0.027467486, -0.06244433, 0.02289261, 0.024697043, -0.033828568, -0.060475856, 0.02289261, -0.001073091, -0.022418717, 0.015365023, -0.008329556, 0.050815757, -0.01447192, -0.033719208, 0.054278813, -0.0053950734, -0.045420684, -0.0015298952, 0.041629553, -0.008479926, 0.008958373, -0.012394087, 0.028178323, 0.0032215514, 0.003836699, -0.029144332, -0.009960837, 0.022181772, -0.014590393, 0.010152216, -0.02952709, -0.017406402, 0.0073544327, 0.0025631154, 0.03654433, -0.058871917, -0.06062167, -0.037729062, -0.006142364, 0.09302856, 0.02342118, -0.03184187, -0.0014695196, -0.0109086195, 0.011036206, -0.008315886, -0.019739408, -0.017461082, -0.004971305, -0.037164036, -0.015884481, 0.023658127, 0.012776846, 0.08005122, 0.0005382543, 0.0097421175, -0.026683742, -0.013688176, -0.024624135, -0.024915762, 0.063975364, 0.06368374, 0.01077192, 0.078301474, 0.030292608, -0.010790147, 0.014362561, -0.025225613, -0.06404827, 0.04432709, -0.06452216, -0.03269852, -0.032662068, -0.00538596, 0.06736551, -0.008420689, 0.008566502, 0.0022179494, 0.063647285, 0.015756896, -0.027595071, -0.0011972598, -0.020176845, 0.03638029, -0.01999458, 0.047389157, -0.0018841748, -0.010498521, 0.053622656, 0.00892192, 0.0050943345, -0.026902461, -0.06266305, -0.015911821, -0.03639852, 0.01607586, 0.023603447, -0.004235406, -0.009108743, -0.00999729, -0.0089766, -0.036799505, 0.022017732, 0.053513296, 0.03922364, 0.0097330045, -0.013888669, 0.004226293, -0.020176845, 0.0035108987, 0.026392115, 0.01817192, -0.04873793, -0.007664285, -0.0072541866, -0.017133003, 0.044946793, 0.02637389, 0.007851108, 0.0015093903, -0.015374136, -0.03907783, -0.014508373, -0.07152118, 0.031094579, -0.010061082, -0.036307387, 0.04228571, -0.027266992, 0.044618715, -0.021890147, -0.022236452, 0.031167485, -0.01157389, 0.0097421175, 0.019575369, 0.036690146, -0.03634384, 0.017552216, 0.051034477, 0.0022555417, 0.0065387925, -0.016786698, -0.018099014, 0.007846551, 0.03145911, -0.042103443, -0.0055363295, 0.0088672405, 0.029071426, -0.0046523395, 0.009851477, -0.023658127, -0.07604137, -0.022710342, -0.009459605, -0.055080783, 0.004347044, 0.015529063, 0.032607388, -0.011364285, 0.034794576, 0.00027382618, -0.028688667, -0.007855664, 0.017807387, -0.007869334, -0.009040393, -0.001921767, 0.008703201, 0.025790637, -0.0004881311, 0.02261921, 0.0213798, 0.07698916, 0.04910246, -0.0040440266, -0.008853571, -0.06590738, -0.0006037561, -0.035614774, -0.011418965, -0.044946793, 0.050961573, 0.023220688, -0.02303842, 0.025663052, 0.037109356, -0.0045452584, -0.009414039, 0.009341132, -0.02899852, 0.013241624, 0.03838522, 0.008694088, -0.03849458, -0.06084039, -0.018162806, -0.046988174, 0.01983054, 0.031823643, 0.016950738, -0.0035450736, 
-0.03269852, -0.019794088, -0.01941133, -0.040645316, -0.026610835, -0.006388423, -0.03350049, 0.07852019, 0.050998025, -0.04571231, -0.0060102213, 0.023913298, -0.006730172, 0.021197535, -0.03882266, -0.020869456, 0.020504924, -0.0038184726, -0.016741132, 0.012585467, 0.0034379924, 0.026665514, 0.021780787, -0.054205906, 0.005818842, 0.00542697, 0.02593645, -0.023111328, 0.013660836, 0.03278965, 0.026337435, -0.013369211, -0.027649751, 0.04571231, 0.0023045256, -0.08573792, 0.0027863914, 0.04902955, -0.034612313, -0.045748763, 0.03665369, -0.037619703, 0.04640492, 0.00980591, 0.05788768, 0.016859604, -0.00086462434, -0.001282697, -0.038348764, 0.06073103, 0.016066747, 0.010079309, -0.010006403, 0.019684728, 0.0069306646, 0.012503447, 0.027522165, 0.015100738, 0.043743838, -0.035468962, 0.022090638, -0.018190145, -0.015428816, -0.012193595, 0.030948766, -0.030055663, -0.0162399, 0.015966501, -0.01792586, 0.005786945, 0.02079655, 0.005773275, -0.018436205, -0.015620195, 0.032516252, 0.00049553567, 0.0065387925, 0.006105911, -0.0035997534, 0.02112463, 0.035560094, -0.08384236, -0.019648274, -0.029818717, 0.013141378, -0.01077192, 0.00032580047, 0.060402952, 0.019958127, 0.022236452, 0.024059111, -0.013970689, -0.12962757, 0.039150737, 0.008552832, 0.011510097, -0.010571428, -0.013715516, -0.0138066495, 0.007591379, -0.0143990135, -0.043598026, 0.04239507, -0.032024134, -0.0216532, 0.05274778, 0.03233399, -0.033646304, 0.016476845, 0.02739458, 0.024970442, -0.029891623, -0.026173396, -0.023220688, -0.012576354, -0.02888916, -0.006119581, -0.018828077, 0.053367484, 0.020942362, -0.03612512, 0.0015595134, 0.020286204, 0.06561576, -0.0041374383, 0.037309848, 0.043889653, 0.025407879, -0.009117857, -0.02256453, -0.025663052, -0.0023922413, -0.03504975, 0.009095073, 0.026793102, 0.002936761, 0.04892019, -0.01358793, 0.00899027, -0.016285466, -0.009281896, -0.021999506, -0.03907783, 0.029235465, -0.01961182, -0.010015517, -0.0011010005, -0.043488666, -0.0046523395, 0.016084975, 0.0048528323, -0.04512906, -0.017652461, 0.03237044, 0.023876846, 0.066271916, -0.0027795564, 0.0067073884, 0.018490884, -0.021634974, 0.024587683, 0.028743347, 0.0026451352, -0.06707389, 0.026136944, -0.031076351, 0.014891132, 0.032935467, 0.028816253, -0.026355663, 0.0180899, -0.09208078, -0.054315265, 0.009377586, -0.009906157, 0.07330738, 0.020122165, 0.012038669, -0.0026451352, 0.0077098515, 0.02433251, 0.20953299, -0.018773397, -0.0145266, 0.04491034, 0.0649596, -0.017369948, -0.01088128, -0.015401476, -0.025571918, -0.007910344, -0.037018225, -0.012084235, 0.020814776, 
0.017998766, -0.020650737, -0.032498028, -0.03585172, -0.01151921, 0.043999013, -0.031878322, 0.034120195, 0.026228076, -0.0028547412, -0.0052902703, 0.018718718, -0.062699504, 0.019848768, 0.05912709, -0.006716502, 0.06423054, -0.041520193, -0.048482753, -0.010234236, 0.0062016007, -0.012020443, -0.02593645, 0.012384974, -0.022199998, 0.016413053, 0.022491625, -0.029071426, -0.043926105, 0.027358126, 0.008917363, 0.03853103, 0.043379307, -0.001991256, 0.0057231523, -0.025189161, -0.00074501225, -0.023731032, 0.026246304, -0.039916255, 0.00900394, -0.0016415331, -0.021926599, 0.005048768, 0.00013185806, 0.008484482, -0.0074820193, 0.028451722, 0.0322064, -0.00037222134, 0.040499505, -0.013469457, 0.0054360833, -0.019794088, 0.005572783, -0.008657635, -0.034393594, 0.049649257, 0.004157943, 0.020596057, 0.042212803, 0.06546994, 0.027102953, 0.029727584, 0.021562068, -0.0042513544, -0.005759605, -0.016495073, 0.014125614, -0.036781278, 0.00986059, -0.020650737, -0.028761573, -0.037164036, 0.050305415, -0.037801966, 0.0033468592, 0.045420684, -0.031058125, 0.027212312, 0.043452214, 0.05267487, -0.029034972, 0.0809261, -0.002804618, -0.02927192, 0.0111911325, 0.06696453, -0.024204925, -0.0005596136, -0.0029390391, -0.027795564, 0.08741477, 0.026884234, 0.039733987, 0.025280293, 0.0006675492, -0.010279802, 0.0005917949, -0.064813785, 0.03463054, 0.012220935, 0.03226108, -0.041738912, 0.0129499985, 0.026082264, 0.012439654, -0.024150245, -0.0149822645, -0.076333, -0.012685713, 0.016495073, 0.0138066495, -0.017561328, 0.0016859605, -0.0028980293, 0.029381279, -0.03656256, 
-0.00091189955, -0.019976353, -0.028433494, 0.024879308, -0.022218226, 0.0036726599, 0.018490884, -0.05278423, 0.03634384, 0.025262067, -0.06583448, -0.0043926104, 0.0015196428, -0.019958127, -0.02593645, 0.013733743, 0.008830788, 0.025772411, 0.009035837, -0.018882757, -0.02347586, -0.049867976, -0.014007142, -0.03206059, -0.0022600982, -0.008438916, -0.021671427, 0.08581083, -0.0387133, -0.034484725, -0.019283742, 0.0035792484, 0.031768963, 0.0019673335, 0.060366496, -0.0060330043, 0.06896945, 0.04454581, -0.028451722, 0.030073889, -0.040900487, -0.041301474, 0.009614531, 0.049539898, 0.042796057, -0.003807081, -0.01353325, -0.01897389, -0.016713792, 0.008388792, 0.012293842, -0.006775738, 0.062189158, 0.01643128, 0.05128965, 0.057632506, -0.021780787, 0.014070935, 0.014754432, 0.019393101, 0.047243346, 0.008671304, 0.0063656396, -0.0031349752, 0.008648521, -0.09208078, -0.036744826, 0.014854679, -0.022309357, 0.04935763, -0.054533985, 0.017242363, -0.032516252, 0.061678812, 0.015000491, -0.008334112, -0.013132265, 0.028779801, -0.005841625, -0.02159852, 0.022582756, 0.03322709, -0.04512906, -0.016331034, -0.012512561, -0.011883743, -0.005272044, 0.050268963, -0.004394889, 
-0.008621181, 0.02068719, 0.013259851, -0.067985214, -0.017451968, -0.008520936, -0.023494087, -0.03269852, 0.054205906, 0.012694826, 0.018718718, 0.013159605, -0.028287683, -0.034266006, -0.033299997, 0.008785221, -0.0066435956, 0.00824298, -0.007040024, -0.022418717, -0.00035769702, 0.018791623, 0.020814776, 0.039260097, -0.012202708, 0.03178719, -0.016804924, 0.030401967, 0.0085756155, 0.020559603, -0.009933497, 0.00076893467, 0.015137191, -0.03709113, -0.07163054, -0.044181276, -0.015866255, -0.008912807, -0.036854185, 0.002980049, -0.046988174, -0.015365023, -0.04684236, 0.0027499383, 
-0.0586532, -0.00041864222, 0.033682756, -0.0018260775, -0.021853693, -0.03634384, 0.01264926, -0.01460862, -0.032078814, -0.045530044, -0.041046303, 0.017524876, -0.01935665, -0.048154674, -0.043561574, 0.03639852, -0.016139654, -0.0056548025, 0.0021837745, 0.008502709, -0.01908325, -0.0006390701, 0.03911428, 0.015957387, -0.025079802, -0.0048254924, -0.03543251, 0.038676843, -0.025025122, 0.026392115, -9.3838506e-05, -0.020085713, -0.07283349, 0.012968225, -0.043598026, 0.0111911325, -0.028761573, 0.027832018, -0.07932216, 0.008028817, -0.005504433, 0.07024531, -0.034193102, -0.004171613, 0.054606892, 0.02723054, -0.009468718, -0.01720591, 0.004087315, -0.02803251, 0.0180899, 0.026793102, -0.013733743, 0.0047662556, 0.019429555, -0.010434728, -0.013214285, 0.005130788, -0.0009529094, -0.0003633928, 0.03227931, -0.03510443, -0.0024765392, -0.030438421, 0.010562315, 0.016312806, -0.03860394, -0.011355171, -0.0011733373, -0.021689653, -0.012822413, 0.0035610218, 0.024788175, -0.011892856, 0.045530044, -0.009769457, 0.011218472, 0.005504433, 0.016440393, -0.011592117, 0.031805415, -0.008616625, 0.020322658, 0.018153694, 0.052383248, -0.007586822, 0.012293842, 0.00723596, -0.0009341132, -0.043889653, -0.024533004, -0.0018807573, -0.011555664, 0.02927192, 0.012685713, -0.03333645, -0.025553692, -0.013341871, 0.016932512, 0.0029322042, 0.02941773, -0.023074875, -0.021233989, 
-0.037656154, -0.052237432, -0.050451227, 0.008083497, 0.006875985, -0.0649596, 0.0054497533, -0.018773397, 0.04228571, 0.004636391, -0.04206699, 0.010972413, -0.0026041253, -0.025553692, -0.03654433, -0.017096551, -0.051799994, 0.025371427, -0.006570689, -0.008762438, -0.037984233, 0.018664038, -0.015647536, 0.008452586, -0.013916009, -0.03827586, 0.012457881, -0.11307782, -0.023238914, 0.05263842, -0.02728522, -0.05344039, -0.029363051, 0.035359602, 0.03537783, 0.009304679, -0.011856403, -0.028743347, -0.006192487, -0.030310836, 0.008994827, -0.0120660085, -0.0144081265, 0.01551995, -0.020614283, -0.026136944, 0.007769088, -0.047899503, 0.004595381, -0.012494334, -0.009236329, 0.08311329, -0.031331524, 0.025717732, 0.06178817, -0.030237928, -0.02117931, -0.017934974, 0.030529555, 0.023566993, 0.026574383, 0.004128325, -0.020723643, -0.00018639545, 0.0140982745, -0.00039557417, -0.024314284, 0.060402952, 0.022528077, 0.004636391, -0.07257832, -0.013970689, 0.01819926, 0.011391625, -0.009568965, -0.055919208, -0.006834975, -0.018044334, 0.02921724, -0.029946303, -0.04888374, 0.013323644, -0.046915267, 0.016932512, 0.03783842, 0.030474875, 0.030584235, -0.013305417, 0.0055636694, 0.009623645, -0.010671674, -0.018190145, 0.019976353, -0.046915267, -0.033464037, -0.044728074, 0.0032716745, 0.036635466, -0.025262067, 0.031823643, -0.035778813, 0.024132017, 0.023275368, 0.04840985, -0.009505171, -0.0078100977, 0.002588177, -0.02267389, 0.017060097, -0.021981278, 0.038676843, -0.013542363, -0.011182019, 0.022965515, -0.060913295, 0.03537783, 0.0161032, -0.025553692, -0.033354677, 0.015255664, 0.021744333, -0.052128073, 0.021361575, -0.03977044, -0.032625612, -0.040754676, -0.026975367, -0.031058125, -0.024132017, -0.025571918, 0.003371921, -9.163138e-05, -0.004212623, -0.010498521, -0.03145911, 0.012995565, 0.034193102, 0.028870933, 0.0046249996, 0.01063522, 0.00025047336, 0.028050736, 0.023913298, -0.007732635, -0.011619457, -0.014845565, -0.0043584355, 0.0063519697, 0.024095565, -0.029873397, -0.027667979, -0.0015412868, 0.044800982, 0.0025767854, 0.028287683, 0.034685217, -0.056903444, 0.024478324, -0.053258125, -0.047462065, -0.00016574813, -0.0024309726, 0.0145266, 0.025043348, 0.033846796, -0.018044334, -0.030784726, 0.010097536, -0.009760344, -0.021744333, -0.011008866, -0.0025858989, 0.016030295, -0.055554677, -0.032133494, -0.038786203, 0.01549261, 0.020577831, 0.003752401, -0.017032757, -0.027740885, 0.08828965, -0.0031121918, -0.022983741, 0.024933988, 0.02593645, 0.034502953, 0.030511327, -0.041666005, -0.02888916, -0.047498517, 0.018736944, 0.009368472, -0.010872167, -0.026009357, -0.026537929, -0.016367486, 0.002882081, -0.033901475, -0.023822166, 0.052018713, -0.004593103, -0.011455418, 0.026902461, 0.012986452, 0.028962066, -0.008115393, 0.024113791, 0.015939161, 0.0040417486, 0.0054998766, 0.017998766, 0.015228324, -0.033427585, -0.0027772782, 0.0066800485, -0.0129499985, 0.0129408855, -0.0068942113, 0.07137536, 0.0054862066, 0.0100337425, 0.017142117, 0.009906157, 0.04352512, -0.06448571, 0.053804923, -0.03233399, -0.028469948, -0.01983054, -0.04421773, 0.030894086, 0.0006339439, 0.018408865, -0.03692709, -0.007231403, 0.044582263, -0.016440393, -0.011583004, -0.011245812, 0.0073954426, 0.001086761, 0.04192118, 0.016932512, 0.0062152706, 0.055882756, -0.029435959, -0.009117857, 0.016012067, -0.018600244, -0.02079655, 0.0069169947, 0.0062016007, 0.016166994, 0.027266992, -0.012922659, -0.024733495, -0.008411576, 0.041848272, -0.023986205, 0.05263842, 0.03548719, -0.023639899, 0.01366995, -0.011911083, -0.031714283, -0.053768467, -0.0040349136, 0.03300837, -0.009231772, -0.041155662],
            [-1, -1, -1, -1, 0.02289261, 0.024697043, -0.033828568, -0.060475856, 0.02289261, -0.001073091, -0.022418717, 0.015365023, -0.008329556, 0.050815757, -0.01447192, -0.033719208, 0.054278813, -0.0053950734, -0.045420684, -0.0015298952, 0.041629553, -0.008479926, 0.008958373, -0.012394087, 0.028178323, 0.0032215514, 0.003836699, -0.029144332, -0.009960837, 0.022181772, -0.014590393, 0.010152216, -0.02952709, -0.017406402, 0.0073544327, 0.0025631154, 0.03654433, -0.058871917, -0.06062167, -0.037729062, -0.006142364, 0.09302856, 0.02342118, -0.03184187, -0.0014695196, -0.0109086195, 0.011036206, -0.008315886, -0.019739408, -0.017461082, -0.004971305, -0.037164036, -0.015884481, 0.023658127, 0.012776846, 0.08005122, 0.0005382543, 0.0097421175, -0.026683742, -0.013688176, -0.024624135, -0.024915762, 0.063975364, 0.06368374, 0.01077192, 0.078301474, 0.030292608, -0.010790147, 0.014362561, -0.025225613, -0.06404827, 0.04432709, -0.06452216, -0.03269852, -0.032662068, -0.00538596, 0.06736551, -0.008420689, 0.008566502, 0.0022179494, 0.063647285, 0.015756896, -0.027595071, -0.0011972598, -0.020176845, 0.03638029, -0.01999458, 0.047389157, -0.0018841748, -0.010498521, 0.053622656, 0.00892192, 0.0050943345, -0.026902461, -0.06266305, -0.015911821, -0.03639852, 0.01607586, 0.023603447, -0.004235406, -0.009108743, -0.00999729, -0.0089766, -0.036799505, 0.022017732, 0.053513296, 0.03922364, 0.0097330045, -0.013888669, 0.004226293, -0.020176845, 0.0035108987, 0.026392115, 0.01817192, -0.04873793, -0.007664285, -0.0072541866, -0.017133003, 0.044946793, 0.02637389, 0.007851108, 0.0015093903, -0.015374136, -0.03907783, -0.014508373, -0.07152118, 0.031094579, -0.010061082, -0.036307387, 0.04228571, -0.027266992, 0.044618715, -0.021890147, -0.022236452, 0.031167485, -0.01157389, 0.0097421175, 0.019575369, 0.036690146, -0.03634384, 0.017552216, 0.051034477, 0.0022555417, 0.0065387925, -0.016786698, -0.018099014, 0.007846551, 0.03145911, -0.042103443, -0.0055363295, 0.0088672405, 0.029071426, -0.0046523395, 0.009851477, -0.023658127, -0.07604137, -0.022710342, -0.009459605, -0.055080783, 0.004347044, 0.015529063, 0.032607388, -0.011364285, 0.034794576, 0.00027382618, -0.028688667, -0.007855664, 0.017807387, -0.007869334, -0.009040393, -0.001921767, 0.008703201, 0.025790637, -0.0004881311, 0.02261921, 0.0213798, 0.07698916, 0.04910246, -0.0040440266, -0.008853571, -0.06590738, -0.0006037561, -0.035614774, -0.011418965, -0.044946793, 0.050961573, 0.023220688, -0.02303842, 0.025663052, 0.037109356, -0.0045452584, -0.009414039, 0.009341132, -0.02899852, 0.013241624, 0.03838522, 0.008694088, -0.03849458, -0.06084039, -0.018162806, -0.046988174, 0.01983054, 0.031823643, 0.016950738, -0.0035450736, 
-0.03269852, -0.019794088, -0.01941133, -0.040645316, -0.026610835, -0.006388423, -0.03350049, 0.07852019, 0.050998025, -0.04571231, -0.0060102213, 0.023913298, -0.006730172, 0.021197535, -0.03882266, -0.020869456, 0.020504924, -0.0038184726, -0.016741132, 0.012585467, 0.0034379924, 0.026665514, 0.021780787, -0.054205906, 0.005818842, 0.00542697, 0.02593645, -0.023111328, 0.013660836, 0.03278965, 0.026337435, -0.013369211, -0.027649751, 0.04571231, 0.0023045256, -0.08573792, 0.0027863914, 0.04902955, -0.034612313, -0.045748763, 0.03665369, -0.037619703, 0.04640492, 0.00980591, 0.05788768, 0.016859604, -0.00086462434, -0.001282697, -0.038348764, 0.06073103, 0.016066747, 0.010079309, -0.010006403, 0.019684728, 0.0069306646, 0.012503447, 0.027522165, 0.015100738, 0.043743838, -0.035468962, 0.022090638, -0.018190145, -0.015428816, -0.012193595, 0.030948766, -0.030055663, -0.0162399, 0.015966501, -0.01792586, 0.005786945, 0.02079655, 0.005773275, -0.018436205, -0.015620195, 0.032516252, 0.00049553567, 0.0065387925, 0.006105911, -0.0035997534, 0.02112463, 0.035560094, -0.08384236, -0.019648274, -0.029818717, 0.013141378, -0.01077192, 0.00032580047, 0.060402952, 0.019958127, 0.022236452, 0.024059111, -0.013970689, -0.12962757, 0.039150737, 0.008552832, 0.011510097, -0.010571428, -0.013715516, -0.0138066495, 0.007591379, -0.0143990135, -0.043598026, 0.04239507, -0.032024134, -0.0216532, 0.05274778, 0.03233399, -0.033646304, 0.016476845, 0.02739458, 0.024970442, -0.029891623, -0.026173396, -0.023220688, -0.012576354, -0.02888916, -0.006119581, -0.018828077, 0.053367484, 0.020942362, -0.03612512, 0.0015595134, 0.020286204, 0.06561576, -0.0041374383, 0.037309848, 0.043889653, 0.025407879, -0.009117857, -0.02256453, -0.025663052, -0.0023922413, -0.03504975, 0.009095073, 0.026793102, 0.002936761, 0.04892019, -0.01358793, 0.00899027, -0.016285466, -0.009281896, -0.021999506, -0.03907783, 0.029235465, -0.01961182, -0.010015517, -0.0011010005, -0.043488666, -0.0046523395, 0.016084975, 0.0048528323, -0.04512906, -0.017652461, 0.03237044, 0.023876846, 0.066271916, -0.0027795564, 0.0067073884, 0.018490884, -0.021634974, 0.024587683, 0.028743347, 0.0026451352, -0.06707389, 0.026136944, -0.031076351, 0.014891132, 0.032935467, 0.028816253, -0.026355663, 0.0180899, -0.09208078, -0.054315265, 0.009377586, -0.009906157, 0.07330738, 0.020122165, 0.012038669, -0.0026451352, 0.0077098515, 0.02433251, 0.20953299, -0.018773397, -0.0145266, 0.04491034, 0.0649596, -0.017369948, -0.01088128, -0.015401476, -0.025571918, -0.007910344, -0.037018225, -0.012084235, 0.020814776, 
0.017998766, -0.020650737, -0.032498028, -0.03585172, -0.01151921, 0.043999013, -0.031878322, 0.034120195, 0.026228076, -0.0028547412, -0.0052902703, 0.018718718, -0.062699504, 0.019848768, 0.05912709, -0.006716502, 0.06423054, -0.041520193, -0.048482753, -0.010234236, 0.0062016007, -0.012020443, -0.02593645, 0.012384974, -0.022199998, 0.016413053, 0.022491625, -0.029071426, -0.043926105, 0.027358126, 0.008917363, 0.03853103, 0.043379307, -0.001991256, 0.0057231523, -0.025189161, -0.00074501225, -0.023731032, 0.026246304, -0.039916255, 0.00900394, -0.0016415331, -0.021926599, 0.005048768, 0.00013185806, 0.008484482, -0.0074820193, 0.028451722, 0.0322064, -0.00037222134, 0.040499505, -0.013469457, 0.0054360833, -0.019794088, 0.005572783, -0.008657635, -0.034393594, 0.049649257, 0.004157943, 0.020596057, 0.042212803, 0.06546994, 0.027102953, 0.029727584, 0.021562068, -0.0042513544, -0.005759605, -0.016495073, 0.014125614, -0.036781278, 0.00986059, -0.020650737, -0.028761573, -0.037164036, 0.050305415, -0.037801966, 0.0033468592, 0.045420684, -0.031058125, 0.027212312, 0.043452214, 0.05267487, -0.029034972, 0.0809261, -0.002804618, -0.02927192, 0.0111911325, 0.06696453, -0.024204925, -0.0005596136, -0.0029390391, -0.027795564, 0.08741477, 0.026884234, 0.039733987, 0.025280293, 0.0006675492, -0.010279802, 0.0005917949, -0.064813785, 0.03463054, 0.012220935, 0.03226108, -0.041738912, 0.0129499985, 0.026082264, 0.012439654, -0.024150245, -0.0149822645, -0.076333, -0.012685713, 0.016495073, 0.0138066495, -0.017561328, 0.0016859605, -0.0028980293, 0.029381279, -0.03656256, 
-0.00091189955, -0.019976353, -0.028433494, 0.024879308, -0.022218226, 0.0036726599, 0.018490884, -0.05278423, 0.03634384, 0.025262067, -0.06583448, -0.0043926104, 0.0015196428, -0.019958127, -0.02593645, 0.013733743, 0.008830788, 0.025772411, 0.009035837, -0.018882757, -0.02347586, -0.049867976, -0.014007142, -0.03206059, -0.0022600982, -0.008438916, -0.021671427, 0.08581083, -0.0387133, -0.034484725, -0.019283742, 0.0035792484, 0.031768963, 0.0019673335, 0.060366496, -0.0060330043, 0.06896945, 0.04454581, -0.028451722, 0.030073889, -0.040900487, -0.041301474, 0.009614531, 0.049539898, 0.042796057, -0.003807081, -0.01353325, -0.01897389, -0.016713792, 0.008388792, 0.012293842, -0.006775738, 0.062189158, 0.01643128, 0.05128965, 0.057632506, -0.021780787, 0.014070935, 0.014754432, 0.019393101, 0.047243346, 0.008671304, 0.0063656396, -0.0031349752, 0.008648521, -0.09208078, -0.036744826, 0.014854679, -0.022309357, 0.04935763, -0.054533985, 0.017242363, -0.032516252, 0.061678812, 0.015000491, -0.008334112, -0.013132265, 0.028779801, -0.005841625, -0.02159852, 0.022582756, 0.03322709, -0.04512906, -0.016331034, -0.012512561, -0.011883743, -0.005272044, 0.050268963, -0.004394889, 
-0.008621181, 0.02068719, 0.013259851, -0.067985214, -0.017451968, -0.008520936, -0.023494087, -0.03269852, 0.054205906, 0.012694826, 0.018718718, 0.013159605, -0.028287683, -0.034266006, -0.033299997, 0.008785221, -0.0066435956, 0.00824298, -0.007040024, -0.022418717, -0.00035769702, 0.018791623, 0.020814776, 0.039260097, -0.012202708, 0.03178719, -0.016804924, 0.030401967, 0.0085756155, 0.020559603, -0.009933497, 0.00076893467, 0.015137191, -0.03709113, -0.07163054, -0.044181276, -0.015866255, -0.008912807, -0.036854185, 0.002980049, -0.046988174, -0.015365023, -0.04684236, 0.0027499383, 
-0.0586532, -0.00041864222, 0.033682756, -0.0018260775, -0.021853693, -0.03634384, 0.01264926, -0.01460862, -0.032078814, -0.045530044, -0.041046303, 0.017524876, -0.01935665, -0.048154674, -0.043561574, 0.03639852, -0.016139654, -0.0056548025, 0.0021837745, 0.008502709, -0.01908325, -0.0006390701, 0.03911428, 0.015957387, -0.025079802, -0.0048254924, -0.03543251, 0.038676843, -0.025025122, 0.026392115, -9.3838506e-05, -0.020085713, -0.07283349, 0.012968225, -0.043598026, 0.0111911325, -0.028761573, 0.027832018, -0.07932216, 0.008028817, -0.005504433, 0.07024531, -0.034193102, -0.004171613, 0.054606892, 0.02723054, -0.009468718, -0.01720591, 0.004087315, -0.02803251, 0.0180899, 0.026793102, -0.013733743, 0.0047662556, 0.019429555, -0.010434728, -0.013214285, 0.005130788, -0.0009529094, -0.0003633928, 0.03227931, -0.03510443, -0.0024765392, -0.030438421, 0.010562315, 0.016312806, -0.03860394, -0.011355171, -0.0011733373, -0.021689653, -0.012822413, 0.0035610218, 0.024788175, -0.011892856, 0.045530044, -0.009769457, 0.011218472, 0.005504433, 0.016440393, -0.011592117, 0.031805415, -0.008616625, 0.020322658, 0.018153694, 0.052383248, -0.007586822, 0.012293842, 0.00723596, -0.0009341132, -0.043889653, -0.024533004, -0.0018807573, -0.011555664, 0.02927192, 0.012685713, -0.03333645, -0.025553692, -0.013341871, 0.016932512, 0.0029322042, 0.02941773, -0.023074875, -0.021233989, 
-0.037656154, -0.052237432, -0.050451227, 0.008083497, 0.006875985, -0.0649596, 0.0054497533, -0.018773397, 0.04228571, 0.004636391, -0.04206699, 0.010972413, -0.0026041253, -0.025553692, -0.03654433, -0.017096551, -0.051799994, 0.025371427, -0.006570689, -0.008762438, -0.037984233, 0.018664038, -0.015647536, 0.008452586, -0.013916009, -0.03827586, 0.012457881, -0.11307782, -0.023238914, 0.05263842, -0.02728522, -0.05344039, -0.029363051, 0.035359602, 0.03537783, 0.009304679, -0.011856403, -0.028743347, -0.006192487, -0.030310836, 0.008994827, -0.0120660085, -0.0144081265, 0.01551995, -0.020614283, -0.026136944, 0.007769088, -0.047899503, 0.004595381, -0.012494334, -0.009236329, 0.08311329, -0.031331524, 0.025717732, 0.06178817, -0.030237928, -0.02117931, -0.017934974, 0.030529555, 0.023566993, 0.026574383, 0.004128325, -0.020723643, -0.00018639545, 0.0140982745, -0.00039557417, -0.024314284, 0.060402952, 0.022528077, 0.004636391, -0.07257832, -0.013970689, 0.01819926, 0.011391625, -0.009568965, -0.055919208, -0.006834975, -0.018044334, 0.02921724, -0.029946303, -0.04888374, 0.013323644, -0.046915267, 0.016932512, 0.03783842, 0.030474875, 0.030584235, -0.013305417, 0.0055636694, 0.009623645, -0.010671674, -0.018190145, 0.019976353, -0.046915267, -0.033464037, -0.044728074, 0.0032716745, 0.036635466, -0.025262067, 0.031823643, -0.035778813, 0.024132017, 0.023275368, 0.04840985, -0.009505171, -0.0078100977, 0.002588177, -0.02267389, 0.017060097, -0.021981278, 0.038676843, -0.013542363, -0.011182019, 0.022965515, -0.060913295, 0.03537783, 0.0161032, -0.025553692, -0.033354677, 0.015255664, 0.021744333, -0.052128073, 0.021361575, -0.03977044, -0.032625612, -0.040754676, -0.026975367, -0.031058125, -0.024132017, -0.025571918, 0.003371921, -9.163138e-05, -0.004212623, -0.010498521, -0.03145911, 0.012995565, 0.034193102, 0.028870933, 0.0046249996, 0.01063522, 0.00025047336, 0.028050736, 0.023913298, -0.007732635, -0.011619457, -0.014845565, -0.0043584355, 0.0063519697, 0.024095565, -0.029873397, -0.027667979, -0.0015412868, 0.044800982, 0.0025767854, 0.028287683, 0.034685217, -0.056903444, 0.024478324, -0.053258125, -0.047462065, -0.00016574813, -0.0024309726, 0.0145266, 0.025043348, 0.033846796, -0.018044334, -0.030784726, 0.010097536, -0.009760344, -0.021744333, -0.011008866, -0.0025858989, 0.016030295, -0.055554677, -0.032133494, -0.038786203, 0.01549261, 0.020577831, 0.003752401, -0.017032757, -0.027740885, 0.08828965, -0.0031121918, -0.022983741, 0.024933988, 0.02593645, 0.034502953, 0.030511327, -0.041666005, -0.02888916, -0.047498517, 0.018736944, 0.009368472, -0.010872167, -0.026009357, -0.026537929, -0.016367486, 0.002882081, -0.033901475, -0.023822166, 0.052018713, -0.004593103, -0.011455418, 0.026902461, 0.012986452, 0.028962066, -0.008115393, 0.024113791, 0.015939161, 0.0040417486, 0.0054998766, 0.017998766, 0.015228324, -0.033427585, -0.0027772782, 0.0066800485, -0.0129499985, 0.0129408855, -0.0068942113, 0.07137536, 0.0054862066, 0.0100337425, 0.017142117, 0.009906157, 0.04352512, -0.06448571, 0.053804923, -0.03233399, -0.028469948, -0.01983054, -0.04421773, 0.030894086, 0.0006339439, 0.018408865, -0.03692709, -0.007231403, 0.044582263, -0.016440393, -0.011583004, -0.011245812, 0.0073954426, 0.001086761, 0.04192118, 0.016932512, 0.0062152706, 0.055882756, -0.029435959, -0.009117857, 0.016012067, -0.018600244, -0.02079655, 0.0069169947, 0.0062016007, 0.016166994, 0.027266992, -0.012922659, -0.024733495, -0.008411576, 0.041848272, -0.023986205, 0.05263842, 0.03548719, -0.023639899, 0.01366995, -0.011911083, -0.031714283, -0.053768467, -0.0040349136, 0.03300837, -0.009231772, -0.041155662]
        ],
        collection="bot_semantic_search_go_live",
        output_fields=["chunk_id", "role"],
        top_k=5,
        threshold=0.0,
        partition_names=['QA']
    )
    for r in results:
        print(r)

        
async def ccu():
    import numpy as np
    from time import time
    from typing import List
    from tqdm import tqdm

    searcher = MilvusStorage(MilvusConfig.default())
    searcher._load_collection("bot_semantic_search_go_live")
    print("Starting concurrent searches...")
    
    total_time = 0
    all_results = []
    concurrent_requests = 100
    num_loops = 10
    
    for loop in range(num_loops):
        # Generate 50 random vectors for concurrent requests
        vectors = []
        for _ in tqdm(range(concurrent_requests)):
            random_vector = np.random.uniform(-1, 1, 1024)
            random_vector = random_vector / np.linalg.norm(random_vector)
            vectors.append(random_vector.tolist())
        
        # Time the batch of concurrent requests
        start_time = time()
        tasks = [
            searcher.run(
                VDBQuery(
                    query_vector=vector,
                    collection="bot_semantic_search_go_live",
                    output_fields=["chunk_id"],
                    top_k=10
                )
            )
            for vector in vectors
        ]
        
        batch_results = await asyncio.gather(*tasks)
        end_time = time()
        
        batch_time = end_time - start_time
        total_time += batch_time
        all_results.extend(batch_results)
        
        # Print progress
        total_searches = (loop + 1) * concurrent_requests
        avg_time_per_search = batch_time / concurrent_requests
        print(f"\nLoop {loop + 1}/{num_loops} completed:")
        print(f"Batch time: {batch_time:.2f}s")
        print(f"Avg time per search in batch: {avg_time_per_search:.4f}s")
        print(f"Total searches completed: {total_searches}")
    
    # Print final statistics
    total_searches = num_loops * concurrent_requests
    print("\nFinal Statistics:")
    print(f"Total searches performed: {total_searches}")
    print(f"Total time elapsed: {total_time:.2f}s")
    print(f"Overall average time per search: {total_time/total_searches:.4f}s")
    print(f"Overall searches per second: {total_searches/total_time:.2f}")
    
    print(len(all_results))
    # Print sample result
    print("\nSample results from first search:")
    for doc in all_results[0]:
        print(doc)


if __name__ == "__main__":
    asyncio.run(single_run())