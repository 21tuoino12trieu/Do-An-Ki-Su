
import asyncio
import base64
import hashlib
import io
import os
import tempfile
import mimetypes
from typing import Dict, Any, Union, Optional

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError
from botocore.client import Config as BotoConfig
from beegen.configs.storage.s3_config import S3Config, S3Operation
from beegen.loggings import LOGGER


class S3Engine:
    """
    Unified S3 engine for all S3 operations using aioboto3.
    
    Supports both in-memory operations (read/write bytes) and file operations 
    (download/upload files to disk).
    """
    
    def __init__(self, config: S3Config):
        """
        Initialize S3Engine with configuration.
        
        Args:
            config: S3Config instance containing all necessary settings.
        """
        self.config = config
        self.session = aioboto3.Session()
        self.bucket = config.bucket
        # Operation mapping
        self.operation_map = {
            S3Operation.READ: self._read,
            S3Operation.WRITE: self._write,
            S3Operation.DELETE: self._delete,
            S3Operation.LIST_PATHS: self._list_paths,
            S3Operation.DOWNLOAD_FILE: self._download_file,
            S3Operation.UPLOAD_FILE: self._upload_file,
        }
        
    async def _get_client(self):
        return self.session.client(
            "s3",
            aws_access_key_id=self.config.access_key,
            aws_secret_access_key=self.config.secret_key,
            region_name=self.config.region,
            endpoint_url=self.config.endpoint_url,
            config=self.config.get_boto_config()
        )
        
    async def _list_paths(self, **params) -> Dict[str, Any]:
        """
        List all object paths under the specified S3 prefix.

        Args:
            params (dict): Operation parameters. Must include "prefix" (str) to specify the S3 key prefix.

        Returns:
            dict: A dictionary with the following keys:
                - "status" (str): "success" or "error"
                - "paths" (List[str]): List of matching S3 object keys
                - "count" (int): Number of matching paths
        """
        prefix = params.get("prefix", "")
        bucket = params.get("bucket", "")
        if self.bucket is not None:
            bucket = self.bucket

        async with await self._get_client() as s3:
            response = await s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
            contents = response.get("Contents", [])
            keys = [item["Key"] for item in contents]
            return {"status": "success", "paths": keys, "count": len(keys)}
    
    async def _read(self, **params) -> Dict[str, Any]:
        """
        Read a file from S3 by key.

        Args:
            params (dict): Parameters for the operation. Must include:
                - key (str): The S3 object key to read.

        Returns:
            dict: A dictionary with the following keys:
                - status (str): "success" if the read succeeded, "error" otherwise.
                - document_bytes (bytes): The content of the S3 object (if successful).
                - document_path (str): Full S3 path to the object (only if succeeded).
                - content_type (str): The MIME type of the object, if available.
        """
        key = params["key"]
        bucket = params.get("bucket", "")
        if self.bucket is not None:
            bucket = self.bucket

        async with await self._get_client() as s3:
            obj = await s3.get_object(Bucket=bucket, Key=key)
            content = await obj["Body"].read()
            content_type = obj.get("ContentType", "application/octet-stream")
            return {
                "status": "success",
                "document_bytes": content,
                "document_path": f"s3://{bucket}/{key}",
                "content_type": content_type,
            }
        
    async def _write(self, **params) -> Dict[str, Any]:
        """
        Upload a file to S3 under the specified key.

        Args:
            params (dict): Parameters for the write operation. Must include:
                - key (str): The S3 object key to write to.
                - content (bytes or io.BytesIO): The content to upload.
                - content_type (str, optional): The MIME type of the content. 
                  If not provided, it will be inferred from the key extension or default to 'application/octet-stream'.

        Returns:
            dict: A dictionary containing:
                - status (str): "success" if the upload succeeded.
                - document_path (str): Full S3 path to the uploaded object (only if succeeded).
        """
        key = params["key"]
        data = params["content"]
        bucket = params.get("bucket", "")
        if self.bucket is not None:
            bucket = self.bucket

        if isinstance(data, bytes):
            data_stream = data
        elif isinstance(data, io.BytesIO):
            data_stream = data.getvalue()
        else:
            raise ValueError("`content` must be bytes or io.BytesIO")

        guessed_type, _ = mimetypes.guess_type(key)
        default_type = guessed_type or "application/octet-stream"
        content_type = params.get("content_type", default_type)

        if not isinstance(content_type, str):
            raise ValueError("`content_type` must be a string")

        async with await self._get_client() as s3:
            await s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=data_stream,
                ContentType=content_type,
                ChecksumSHA256=base64.b64encode(hashlib.sha256(data_stream).digest()).decode() 
            )

        return {
            "status": "success",
            "document_path": f"s3://{bucket}/{key}"
        }
        
    async def _delete(self, **params) -> Dict[str, Any]:
        """
        Delete a file from S3 using a specified key.

        Args:
            params (dict): Parameters for the delete operation. Must include:
                - key (str): The S3 object key to delete.

        Returns:
            dict: A dictionary with the following keys:
                - status (str): "success" if the delete succeeded.
                - document_path (str): Full S3 path to the deleted object (only if succeeded).
        """
        key = params["key"]
        bucket = params.get("bucket", "")
        if self.bucket is not None:
            bucket = self.bucket

        async with await self._get_client() as s3:
            await s3.delete_object(Bucket=bucket, Key=key)
            return {
                "status": "success",
                "document_path": f"s3://{bucket}/{key}"
            }

    async def _download_file(self, **params) -> Dict[str, Any]:
        """
        Download a file from S3 to local disk.

        Args:
            params (dict): Parameters for the download operation. Must include:
                - s3_file_path (str): The S3 object key to download.
                - local_dir (str, optional): Local directory to download to. 
                  If not provided, uses temporary directory.

        Returns:
            dict: A dictionary with the following keys:
                - status (str): "success" if the download succeeded.
                - local_file_path (str): Local path where file was downloaded.
                - document_path (str): Full S3 path of the object.
        """
        key = params["key"]
        local_dir = params.get("local_dir")

        bucket = params.get("bucket", "")
        if self.bucket is not None:
            bucket = self.bucket
        
        # Create local directory if not provided
        if local_dir is None:
            local_dir = tempfile.mkdtemp()
        else:
            # Ensure local directory exists
            os.makedirs(local_dir, exist_ok=True)
        
        # Generate local file path using original filename
        local_file_path = os.path.join(local_dir, os.path.basename(key))
        
        # Download file from S3 to local file
        async with await self._get_client() as s3:
            await s3.download_file(
                bucket,
                key,
                local_file_path
            )
        
        return {
            "status": "success",
            "local_file_path": local_file_path,
            "document_path": f"s3://{bucket}/{key}"
        }

    async def _upload_file(self, **params) -> Dict[str, Any]:
        """
        Upload a local file to S3.

        Args:
            params (dict): Parameters for the upload operation. Must include:
                - local_file_path (str): Local file path to upload.
                - s3_file_path (str): S3 destination path.
                - content_type (str, optional): MIME type of the file.
                  If not provided, it will be inferred from the file extension.

        Returns:
            dict: A dictionary with the following keys:
                - status (str): "success" if the upload succeeded.
                - document_path (str): Full S3 path of the uploaded object.
        """
        local_file_path = params["local_file_path"]
        key = params["key"]
        bucket = params.get("bucket", "")
        if self.bucket is not None:
            bucket = self.bucket
        
        # Verify local file exists
        if not os.path.exists(local_file_path):
            raise FileNotFoundError(f"Local file not found: {local_file_path}")
        
        # Determine content type
        guessed_type, _ = mimetypes.guess_type(local_file_path)
        default_type = guessed_type or "application/octet-stream"
        content_type = params.get("content_type", default_type)
        
        # Read file data
        with open(local_file_path, 'rb') as file:
            data = file.read()
        
        # Upload file to S3
        async with await self._get_client() as s3:
            await s3.put_object(
                Body=data,
                Bucket=bucket,
                Key=key,
                ContentType=content_type,
                ChecksumSHA256=base64.b64encode(hashlib.sha256(data).digest()).decode() 
            )
        
        return {
            "status": "success",
            "document_path": f"s3://{bucket}/{key}"
        }

    async def run(self, operation: S3Operation, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an S3 operation.

        Args:
            operation: The S3Operation enum value.
            params: Parameters needed for the operation.

        Returns:
            A dictionary with result or error.
        """
        try:
            if operation not in self.operation_map:
                raise ValueError(f"Unsupported operation: {operation}")
            
            result = await self.operation_map[operation](**params)
            
            # Add operation success message if not present
            if 'message' not in result:
                op_name = operation.name.lower().replace('_', ' ')
                result['message'] = f"Operation {op_name} completed successfully"
                
            return result
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            return {
                "status": "error", 
                "message": str(error_traceback)
            }
    
    
# Example usage
async def main():
    config = S3Config.default()
    executor = S3Engine(config=config)

    test_list_path = await executor.run(
        operation=S3Operation.LIST_PATHS,
        params={"prefix" : "nlp"}
    )
    print(f"Test list path: {test_list_path}")

    test_write = await executor.run(
        operation=S3Operation.WRITE,
        params={"key": "rnd/thaivd/work/flash-sale-bot/data/product_profile/test.csv",
                "content" : io.BytesIO(b"name,age\nAlice,30\nBob,25"),
                "content_type": "text/csv"}
    )
    print(f"Test write: {test_write}")

    test_read = await executor.run(
        operation=S3Operation.READ,
        params={"key": "rnd/thaivd/work/flash-sale-bot/data/product_profile/test.csv"}
    )
    print(f"Test read: {test_read}")

    test_delete = await executor.run(
        operation=S3Operation.DELETE,
        params={"key": "rnd/thaivd/work/flash-sale-bot/data/product_profile/test.csv"}
    )
    print(f"Test delete: {test_delete}")
    

async def main2():
    config = S3Config.default()
    executor = S3Engine(config=config)

    # Test 1: write -> read -> delete
    print("Test 1: write -> read -> delete")
    test_write = await executor.run(
        operation=S3Operation.WRITE,
        params={"bucket": "ai-knowledge-working",
                "key": "rnd/test/sample.csv",
                "content": io.BytesIO(b"name,age\nAlice,30\nBob,25"),
                "content_type": "text/csv"}
    )
    print(f"Write: {test_write}")

    test_read = await executor.run(
        operation=S3Operation.READ,
        params={"bucket": "ai-knowledge-working",
                "key": "rnd/test/sample.csv"}
    )
    print(f"Read: {test_read}")

    test_delete = await executor.run(
        operation=S3Operation.DELETE,
        params={"bucket": "ai-knowledge-working",
                "key": "rnd/test/sample.csv"}
    )
    print(f"Delete: {test_delete}")
    
    # Test 2: upload -> download -> delete
    print("\nTest 2: upload -> download -> delete")
    
    # Create temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello World!")
        temp_file = f.name

    test_upload = await executor.run(
        operation=S3Operation.UPLOAD_FILE,
        params={"local_file_path": temp_file,
                "key": "rnd/test/uploaded.txt"}
    )
    print(f"Upload: {test_upload}")

    test_download = await executor.run(
        operation=S3Operation.DOWNLOAD_FILE,
        params={"key": "rnd/test/uploaded.txt"}
    )
    print(f"Download: {test_download}")

    test_delete_file = await executor.run(
        operation=S3Operation.DELETE,
        params={"key": "rnd/test/uploaded.txt"}
    )
    print(f"Delete file: {test_delete_file}")

    # Cleanup
    os.unlink(temp_file)



if __name__ == "__main__":
    asyncio.run(main2())