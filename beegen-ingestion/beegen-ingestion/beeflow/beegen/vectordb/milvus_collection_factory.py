from typing import (
    Dict, 
    List
)
from pymilvus import (
    Collection,
    DataType,
    FieldSchema,
    CollectionSchema
)
from pymilvus import utility
from beegen.loggings import LOGGER


class MilvusCollectionFactory:
    """
    Factory class responsible for creating Milvus collections.
    Follows the Factory design pattern to encapsulate complex object creation.
    """
    
    def __init__(self, alias: str):
        """
        Initialize the collection factory.
        
        :param alias: The Milvus connection alias to use
        """
        self.alias = alias
    
    def create(
        self, 
        collection_name: str, 
        fields: List[Dict], 
        **kwargs
    ) -> Collection:
        """
        Creates and returns a Milvus collection with the given name and field definitions.

        :param collection_name: Name of the collection
        :param fields: List of field definitions
        :param kwargs: Additional arguments for collection creation
        :return: The created Collection object or None if already exists
        """
        
        # Check if collection already exists
        if utility.has_collection(collection_name, using=self.alias):
            LOGGER.warning(f"Collection {collection_name} already exists")
            return None
            
        # Create field schemas from field definitions
        field_schemas = []
        for field in fields:
            field_schema = self._create_field_schema(field)
            field_schemas.append(field_schema)

        # Create the collection schema
        schema = CollectionSchema(
            fields=field_schemas, 
            description=kwargs.get("description", "")
        )

        # Build collection creation arguments
        collection_kwargs = {
            "name": collection_name,
            "schema": schema,
            "using": self.alias
        }
        
        # Add optional parameters if provided
        for param in ["shards_num", "consistency_level"]:
            if param in kwargs:
                collection_kwargs[param] = kwargs[param]
        
        # Create and return the collection
        collection = Collection(**collection_kwargs)
        LOGGER.info(f"Created collection: {collection_name}")
        
        return collection

    # Other methods remain unchanged as they don't involve async operations
    def _create_field_schema(self, field: Dict) -> FieldSchema:
        """
        Creates a FieldSchema based on the field definition.
        
        :param field: Field definition dictionary
        :return: A FieldSchema object
        """
        field_type = field.get('type')
        dtype = self._map_field_type_to_dtype(field_type)
        
        # Create field schema based on data type
        if self._is_vector_type(dtype):
            return self._create_vector_field_schema(field, dtype)
        elif self._is_string_type(dtype):
            return self._create_string_field_schema(field, dtype)
        elif dtype == DataType.ARRAY:
            return self._create_array_field_schema(field)
        else:
            return self._create_standard_field_schema(field, dtype)

    def _map_field_type_to_dtype(self, field_type: str) -> DataType:
        """
        Maps a string field type to the corresponding Milvus DataType.
        
        :param field_type: String representation of the field type
        :return: Milvus DataType enum value
        :raises ValueError: If the field type is not supported
        """
        type_mapping = {
            'bool': DataType.BOOL,
            'int8': DataType.INT8,
            'int16': DataType.INT16,
            'int32': DataType.INT32,
            'int64': DataType.INT64,
            'int': DataType.INT64,  # Alias for INT64
            'float': DataType.FLOAT,
            'double': DataType.DOUBLE,
            'string': DataType.STRING,
            'varchar': DataType.VARCHAR,
            'array': DataType.ARRAY,
            'json': DataType.JSON,
            'binary_vector': DataType.BINARY_VECTOR,
            'float_vector': DataType.FLOAT_VECTOR,
            'vector': DataType.FLOAT_VECTOR,  # Alias for FLOAT_VECTOR
            'float16_vector': DataType.FLOAT16_VECTOR,
            'bfloat16_vector': DataType.BFLOAT16_VECTOR,
            'sparse_float_vector': DataType.SPARSE_FLOAT_VECTOR
        }
        
        if field_type not in type_mapping:
            raise ValueError(f"Unsupported field type: {field_type}")
        
        return type_mapping[field_type]
    
    def _is_vector_type(self, dtype: DataType) -> bool:
        """
        Determines if a data type is a vector type.
        
        :param dtype: The Milvus DataType to check
        :return: True if vector type, False otherwise
        """
        return dtype in [
            DataType.FLOAT_VECTOR, 
            DataType.BINARY_VECTOR,
            DataType.FLOAT16_VECTOR, 
            DataType.BFLOAT16_VECTOR, 
            DataType.SPARSE_FLOAT_VECTOR
        ]
    
    def _is_string_type(self, dtype: DataType) -> bool:
        """
        Determines if a data type is a string type.
        
        :param dtype: The Milvus DataType to check
        :return: True if string type, False otherwise
        """
        return dtype in [DataType.VARCHAR, DataType.STRING]

    def _create_vector_field_schema(self, field: Dict, dtype: DataType) -> FieldSchema:
        """
        Creates a field schema for vector fields.
        
        :param field: Field definition dictionary
        :param dtype: The Milvus DataType for this field
        :return: A FieldSchema object
        :raises ValueError: If required parameters are missing
        """
        field_params = field.get('params', {})
        field_desc = field.get('description', '')
        is_primary = field.get('is_primary', False)
        
        if 'dim' not in field_params:
            raise ValueError(f"Vector field '{field['name']}' must have 'dim' parameter specified")
        
        dim = field_params.get('dim')
        
        # Special handling for sparse vector
        if dtype == DataType.SPARSE_FLOAT_VECTOR:
            if 'max_length' not in field_params:
                raise ValueError(f"Sparse vector field '{field['name']}' must have 'max_length' parameter specified")
            max_length = field_params.get('max_length')
            return FieldSchema(
                name=field['name'],
                dtype=dtype,
                is_primary=is_primary,
                description=field_desc,
                dim=dim,
                max_length=max_length
            )
        
        # Standard vector fields
        return FieldSchema(
            name=field['name'],
            dtype=dtype,
            is_primary=is_primary,
            description=field_desc,
            dim=dim
        )

    def _create_string_field_schema(self, field: Dict, dtype: DataType) -> FieldSchema:
        """
        Creates a field schema for string-like fields.
        
        :param field: Field definition dictionary
        :param dtype: The Milvus DataType for this field
        :return: A FieldSchema object
        """
        field_params = field.get('params', {})
        field_desc = field.get('description', '')
        is_primary = field.get('is_primary', False)
        
        max_length = field_params.get('max_length', 256)  # Default to 256 if not specified
        
        return FieldSchema(
            name=field['name'],
            dtype=dtype,
            is_primary=is_primary,
            description=field_desc,
            max_length=max_length
        )

    def _create_array_field_schema(self, field: Dict) -> FieldSchema:
        """
        Creates a field schema for ARRAY fields.
        
        :param field: Field definition dictionary
        :return: A FieldSchema object
        :raises ValueError: If required parameters are missing
        """
        field_params = field.get('params', {})
        field_desc = field.get('description', '')
        is_primary = field.get('is_primary', False)
        
        if 'element_type' not in field_params:
            raise ValueError(f"Array field '{field['name']}' must have 'element_type' parameter specified")
        
        element_type_str = field_params.get('element_type')
        max_capacity = field_params.get('max_capacity', 100)  # Default to 100 if not specified
        
        # Map the element_type string to DataType
        try:
            element_dtype = self._map_field_type_to_dtype(element_type_str)
        except ValueError:
            raise ValueError(f"Unsupported array element type: {element_type_str}")
        
        field_schema_args = {
            'name': field['name'],
            'dtype': DataType.ARRAY,
            'is_primary': is_primary,
            'description': field_desc,
            'element_type': element_dtype,
            'max_capacity': max_capacity
        }
        
        # If the element type is VARCHAR, add max_length
        if element_dtype == DataType.VARCHAR:
            element_max_length = field_params.get('element_max_length', 256)
            field_schema_args['max_length'] = element_max_length
            
        return FieldSchema(**field_schema_args)

    def _create_standard_field_schema(self, field: Dict, dtype: DataType) -> FieldSchema:
        """
        Creates a field schema for standard scalar fields.
        
        :param field: Field definition dictionary
        :param dtype: The Milvus DataType for this field
        :return: A FieldSchema object
        """
        field_desc = field.get('description', '')
        is_primary = field.get('is_primary', False)
        
        return FieldSchema(
            name=field['name'],
            dtype=dtype,
            is_primary=is_primary,
            description=field_desc
        )