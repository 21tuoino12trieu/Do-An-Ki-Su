from beeflow.nodes import END, INPUT, OUTPUT, START, BranchNode, CodeNode, KafkaNode, MongoNode, S3Node
from beeflow.nodes.flow.for_loop_node import ForLoopNode
from beeflow.workflow import WorkflowEngine
from beegen.configs.event_streaming.kafka_config import KafkaOperation
from beegen.configs.storage.mongo_config import MongoOperation
from beegen.configs.storage.s3_config import S3Operation

from app.consumer.confluence.processing.cleanup import (
    build_cleanup_old_confluence_data_graph,
)
from app.consumer.confluence.processing.document_processor import (
    build_aggregate_job_response,
    build_chunk_error_update,
    build_chunk_success_update,
    build_document_job_result,
    complete_chunk_job,
    extract_confluence_document,
    prepare_document_data,
    prepare_job_item,
    prepare_chunk_image_uploads,
    replace_chunk_image_markers,
    run_chunk,
    select_job_item_route,
)


def build_chunk_confluence_document_workflow() -> WorkflowEngine:
    with WorkflowEngine(
        name="wf_confluence_chunk_job",
        description="Process one aggregate Confluence Chunk job",
        langfuse="beegen-portal",
    ) as workflow:
        with ForLoopNode(
            name="chunk_document_loop",
            description="Process Confluence documents concurrently",
            inputs={"batch_data": {INPUT: "job_items"}},
            max_concurrency=8,
        ) as document_loop:
            prepare_item = CodeNode(
                name="prepare_chunk_job_item", 
                code_fn=prepare_job_item,
                inputs={
                    "document_id": {INPUT: "document_id"},
                    "content_path": {INPUT: "content_path"},
                    "sync_version": {INPUT: "sync_version"},
                    "dispatch_status": {INPUT: "dispatch_status"},
                    "error_detail": {INPUT: "error_detail"},
                    "bot_id": {INPUT: "bot_id"},
                },
                return_keys=[
                    "message_item: dict",
                    "s3_bucket: str",
                    "s3_object_key: str",
                    "s3_file_name: str",
                    "document_query: dict",
                ],
            )
            find_document = MongoNode(
                name="find_chunk_document", 
                resource_key="aicenter-chatbot",
                operation=MongoOperation.FIND_ONE,
                inputs={
                    "collection_name": "documents", 
                    "query": {prepare_item: "document_query"},
                    "projection": {
                        "_id": 1, "doc_name": 1, "updated_by": 1,
                        "sync_status": 1, "sync_version": 1,
                    },
                },
            )
            select_route = CodeNode(
                name="select_chunk_job_item_route", 
                code_fn=select_job_item_route,
                inputs={
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                },
                return_keys=["route: str"],
            )
            branch_route = BranchNode(
                name="branch_chunk_job_item_route",
                cases={
                    "route == 'process'": "read_confluence_html",
                    "route == 'skip'": "build_skipped_chunk_result",
                    "route == 'producer_error'": "build_producer_error_chunk_result",
                },
                inputs={"route": {select_route: "route"}},
                default=END,
            )
            read_html = S3Node(
                name="read_confluence_html", 
                resource_key="ai-nlp-text", 
                operation=S3Operation.READ,
                inputs={"bucket": {prepare_item: "s3_bucket"}, "key": {prepare_item: "s3_object_key"}},
            )
            extract_document = CodeNode(
                name="extract_confluence_document",
                code_fn=extract_confluence_document,
                inputs={
                    "document_bytes": {read_html: "document_bytes"},
                },
                return_keys=[
                    "html_content: str",
                    "reconstructed: str",
                    "zones: list",
                ],
            )
            chunk_document = CodeNode(
                name="chunk_confluence_document", 
                code_fn=run_chunk,
                inputs={
                    "reconstructed": {extract_document: "reconstructed"},
                    "zones": {extract_document: "zones"},
                    "file_name": {prepare_item: "s3_file_name"},
                    "message_item": {prepare_item: "message_item"},
                },
                return_keys=[
                    "chunk_documents: list",
                    "chunk_status: str",
                    "chunk_error_message: str",
                ],
            )
            branch_chunk = BranchNode(
                name="branch_chunk_result",
                cases={
                    "chunk_status == 'success'": "prepare_chunk_image_uploads",
                    "chunk_status == 'error'": "build_chunk_error_update",
                },
                inputs={"chunk_status": {chunk_document: "chunk_status"}},
                default=END,
            )
            prepare_images = CodeNode(
                name="prepare_chunk_image_uploads",
                code_fn=prepare_chunk_image_uploads,
                inputs={
                    "chunk_documents": {chunk_document: "chunk_documents"},
                    "html_content": {extract_document: "html_content"},
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                },
                return_keys=["image_upload_batch: list", "new_multimedia_ids: list"],
            )
            with ForLoopNode(
                name="chunk_image_upload_loop",
                description="Upload Confluence images and save multimedia metadata",
                inputs={"batch_data": {prepare_images: "image_upload_batch"}},
                max_concurrency=8,
            ) as image_upload_loop:
                upload_image = S3Node(
                    name="upload_chunk_image",
                    resource_key="ai-nlp-text",
                    operation=S3Operation.UPLOAD_FILE,
                    inputs={
                        "bucket": {INPUT: "bucket"},
                        "local_file_path": {INPUT: "local_file_path"},
                        "key": {INPUT: "key"},
                        "content_type": {INPUT: "content_type"},
                    },
                )
                branch_image_upload = BranchNode(
                    name="branch_chunk_image_upload",
                    cases={"upload_status == 'success'": "insert_chunk_multimedia"},
                    inputs={"upload_status": {upload_image: "status"}},
                    default=END,
                )
                insert_multimedia = MongoNode(
                    name="insert_chunk_multimedia",
                    resource_key="aicenter-chatbot",
                    operation=MongoOperation.INSERT_ONE,
                    inputs={
                        "collection_name": "multimedia",
                        "document": {INPUT: "multimedia_document"},
                    },
                    outputs={"status": OUTPUT["status"]},
                )

                START >> upload_image >> branch_image_upload
                branch_image_upload >> [insert_multimedia, END]
                insert_multimedia >> END

            image_upload_loop.build()
            replace_images = CodeNode(
                name="replace_chunk_image_markers",
                code_fn=replace_chunk_image_markers,
                inputs={
                    "chunk_documents": {chunk_document: "chunk_documents"},
                    "image_upload_batch": {prepare_images: "image_upload_batch"},
                    "image_upload_results": {image_upload_loop: "batch_result"},
                },
                return_keys=[
                    "chunk_documents_with_image_paths: list",
                    "image_processing_failed: bool",
                    "image_processing_error_message: str",
                ],
            )
            branch_images = BranchNode(
                name="branch_chunk_image_processing",
                cases={
                    "image_processing_failed == False": "cleanup_old_chunk_document_data",
                    "image_processing_failed == True": "build_chunk_image_error_update",
                },
                inputs={"image_processing_failed": {replace_images: "image_processing_failed"}},
                default=END,
            )
            cleanup_old_data = build_cleanup_old_confluence_data_graph(
                name="cleanup_old_chunk_document_data",
                inputs={
                    "bot_id": {INPUT: "bot_id"},
                    "document_query": {prepare_item: "document_query"},
                    "protected_multimedia_ids": {
                        prepare_images: "new_multimedia_ids"
                    },
                },
            )
            prepare_rows = CodeNode(
                name="prepare_chunk_document_data", code_fn=prepare_document_data,
                inputs={
                    "chunk_documents": {
                        replace_images: "chunk_documents_with_image_paths"
                    },
                    "message_item": {prepare_item: "message_item"},
                },
                return_keys=["document_data_rows: list", "has_document_data_rows: bool"],
            )
            branch_document_data = BranchNode(
                name="branch_chunk_document_data",
                cases={
                    "has_document_data_rows == True": "insert_chunk_document_data",
                },
                inputs={
                    "has_document_data_rows": {
                        prepare_rows: "has_document_data_rows"
                    }
                },
                default="build_empty_chunk_success_update",
            )
            insert_rows = MongoNode(
                name="insert_chunk_document_data", 
                resource_key="aicenter-chatbot",
                operation=MongoOperation.INSERT_MANY,
                inputs={"collection_name": "document_data", "documents": {prepare_rows: "document_data_rows"}},
            )
            success_update = CodeNode(
                name="build_chunk_success_update", 
                code_fn=build_chunk_success_update,
                inputs={"insert_status": {insert_rows: "status"}}, 
                return_keys=["mongo_update: dict"],
            )
            empty_success_update = CodeNode(
                name="build_empty_chunk_success_update",
                code_fn=build_chunk_success_update,
                return_keys=["mongo_update: dict"],
            )
            update_success = MongoNode(
                name="update_chunk_document_success", 
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents", 
                    "filter": {prepare_item: "document_query"},
                    "update": {success_update: "mongo_update"},
                },
            )
            update_empty_success = MongoNode(
                name="update_empty_chunk_document_success",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {prepare_item: "document_query"},
                    "update": {empty_success_update: "mongo_update"},
                },
            )
            delete_html = S3Node(
                name="delete_processed_confluence_html", 
                resource_key="ai-nlp-text",
                operation=S3Operation.DELETE,
                inputs={"bucket": {prepare_item: "s3_bucket"}, "key": {prepare_item: "s3_object_key"}},
            )
            success_result = CodeNode(
                name="build_chunk_success_result", 
                code_fn=build_document_job_result,
                inputs={
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                    "result_status": "success", "error_message": "",
                    "document_update_status": {update_success: "status"},
                    "html_delete_status": {delete_html: "status"},
                }, 
                return_keys=["chunk_result_item: dict"],
                outputs={"chunk_result_item": OUTPUT["chunk_result_item"]},
            )
            delete_empty_html = S3Node(
                name="delete_empty_chunk_confluence_html",
                resource_key="ai-nlp-text",
                operation=S3Operation.DELETE,
                inputs={
                    "bucket": {prepare_item: "s3_bucket"},
                    "key": {prepare_item: "s3_object_key"},
                },
            )
            empty_success_result = CodeNode(
                name="build_empty_chunk_success_result",
                code_fn=build_document_job_result,
                inputs={
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                    "result_status": "success",
                    "error_message": "",
                    "document_update_status": {update_empty_success: "status"},
                    "html_delete_status": {delete_empty_html: "status"},
                },
                return_keys=["chunk_result_item: dict"],
                outputs={"chunk_result_item": OUTPUT["chunk_result_item"]},
            )
            error_update = CodeNode(
                name="build_chunk_error_update", 
                code_fn=build_chunk_error_update,
                inputs={"error_message": {chunk_document: "chunk_error_message"}}, 
                return_keys=["mongo_update: dict"],
            )
            update_error = MongoNode(
                name="update_chunk_document_error", 
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents", "filter": {prepare_item: "document_query"},
                    "update": {error_update: "mongo_update"},
                },
            )
            error_result = CodeNode(
                name="build_chunk_error_result", 
                code_fn=build_document_job_result,
                inputs={
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                    "result_status": "error", "error_message": {chunk_document: "chunk_error_message"},
                    "document_update_status": {update_error: "status"},
                }, 
                return_keys=["chunk_result_item: dict"],
                outputs={"chunk_result_item": OUTPUT["chunk_result_item"]},
            )
            image_error_update = CodeNode(
                name="build_chunk_image_error_update",
                code_fn=build_chunk_error_update,
                inputs={
                    "error_message": {
                        replace_images: "image_processing_error_message"
                    }
                },
                return_keys=["mongo_update: dict"],
            )
            update_image_error = MongoNode(
                name="update_chunk_document_image_error",
                resource_key="aicenter-chatbot",
                operation=MongoOperation.UPDATE_ONE,
                inputs={
                    "collection_name": "documents",
                    "filter": {prepare_item: "document_query"},
                    "update": {image_error_update: "mongo_update"},
                },
            )
            image_error_result = CodeNode(
                name="build_chunk_image_error_result",
                code_fn=build_document_job_result,
                inputs={
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                    "result_status": "error",
                    "error_message": {
                        replace_images: "image_processing_error_message"
                    },
                    "document_update_status": {update_image_error: "status"},
                },
                return_keys=["chunk_result_item: dict"],
                outputs={"chunk_result_item": OUTPUT["chunk_result_item"]},
            )
            skipped_result = CodeNode(
                name="build_skipped_chunk_result", 
                code_fn=build_document_job_result,
                inputs={
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                    "result_status": "success", "error_message": "",
                }, 
                return_keys=["chunk_result_item: dict"],
                outputs={"chunk_result_item": OUTPUT["chunk_result_item"]},
            )
            producer_error_result = CodeNode(
                name="build_producer_error_chunk_result", 
                code_fn=build_document_job_result,
                inputs={
                    "message_item": {prepare_item: "message_item"},
                    "document": {find_document: "data"},
                    "result_status": "error",
                }, 
                return_keys=["chunk_result_item: dict"],
                outputs={"chunk_result_item": OUTPUT["chunk_result_item"]},
            )

            START >> prepare_item >> find_document >> select_route >> branch_route
            branch_route >> [read_html, skipped_result, producer_error_result, END]
            read_html >> extract_document >> chunk_document >> branch_chunk >> [prepare_images, error_update, END]
            prepare_images >> image_upload_loop >> replace_images >> branch_images >> [cleanup_old_data, image_error_update, END]
            cleanup_old_data >> prepare_rows >> branch_document_data >> [insert_rows, empty_success_update]
            insert_rows >> success_update >> update_success >> delete_html >> success_result >> END
            empty_success_update >> update_empty_success >> delete_empty_html >> empty_success_result >> END
            error_update >> update_error >> error_result >> END
            image_error_update >> update_image_error >> image_error_result >> END
            skipped_result >> END
            producer_error_result >> END

        document_loop.build()

        build_response = CodeNode(
            name="build_aggregate_chunk_job_response", 
            code_fn=build_aggregate_job_response,
            inputs={
                "current_job_id": {INPUT: "job_id"}, "current_bot_id": {INPUT: "bot_id"},
                "job_items": {INPUT: "job_items"}, "loop_results": {document_loop: "batch_result"},
            }, 
            return_keys=["response_key: str", "response_value: dict"],
        )
        send_response = KafkaNode(
            name="send_aggregate_chunk_job_response", 
            resource_key="aicenter-cua",
            operation=KafkaOperation.PRODUCE,
            inputs={
                "topic": {INPUT: "response_topic"}, 
                "key": {build_response: "response_key"},
                "value": {build_response: "response_value"},
            },
        )
        finish_job = CodeNode(
            name="complete_aggregate_chunk_job", 
            code_fn=complete_chunk_job,
            inputs={"response_status": {send_response: "status"}},
            return_keys=["processing_completed: bool"], 
            outputs={"processing_completed": OUTPUT},
        )
        START >> document_loop >> build_response >> send_response >> finish_job >> END

    workflow.compile()
    return workflow


