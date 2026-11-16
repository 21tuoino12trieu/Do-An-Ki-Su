"""
Main entry point for Confluence sync workflow using BeeFlow.

This module provides command-line interface for Confluence sync operations.
"""

import argparse
import asyncio
import os
import sys
import traceback
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from beeflow.utils.streaming import STREAM_SERVICE

from confluence_workflow.workflow import build_confluence_sync_workflow
from confluence_workflow.workflow_config import load_config_from_args, resolve_config_page_ids
from confluence_workflow.utils.logger import setup_logging

logger = None


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Confluence to PostgreSQL sync using BeeFlow',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Required arguments
    parser.add_argument(
        '--bot_id',
        type=str,
        default='',
        help='Bot ID; AUTO falls back to AUTO_BOT_IDS when omitted'
    )

    parser.add_argument(
        '--sync_mode',
        type=str,
        required=True,
        choices=['FIRST', 'PARTIAL', 'AUTO'],
        help='Sync mode to use'
    )

    parser.add_argument(
        '--page_ids',
        type=str,
        default='[]',
        help='JSON array of page IDs (for FIRST / PARTIAL mode)'
    )

    # Optional arguments
    parser.add_argument(
        '--confluence_url',
        type=str,
        default=None,
        help='Confluence base URL (overrides .env)'
    )

    parser.add_argument(
        '--confluence_token',
        type=str,
        default=None,
        help='Confluence API token (overrides .env)'
    )

    parser.add_argument(
        '--batch_size',
        type=int,
        default=50,
        help='Batch size for fetching pages'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=0,
        help='Limit number of pages to process (for testing)'
    )

    parser.add_argument(
        '--log_level',
        type=str,
        default='INFO',
        help='Log level'
    )


    return parser.parse_args()


def resolve_bot_ids(args):
    """Use the explicit bot, or AUTO_BOT_IDS when AUTO receives an empty bot_id."""
    if args.bot_id.strip():
        return [args.bot_id.strip()]

    if args.sync_mode != "AUTO":
        raise ValueError(f"bot_id is required for {args.sync_mode} mode")

    bot_ids = [bot_id.strip()for bot_id in os.getenv("AUTO_BOT_IDS", "").split(",") if bot_id.strip()]
    if not bot_ids:
        raise ValueError("AUTO mode requires bot_id or AUTO_BOT_IDS")
    return bot_ids


async def run_workflow_for_bot(args, bot_id):
    """Build and execute one isolated workflow for a bot."""
    args.bot_id = bot_id
    config = load_config_from_args(args)
    await resolve_config_page_ids(config)
    logger.info("Configuration loaded for bot_id=%s with %s page IDs", bot_id, len(config.page_ids))

    workflow = build_confluence_sync_workflow(config)
    logger.info("Workflow built successfully for bot_id=%s", bot_id)

    request_id = str(uuid.uuid4())
    logger.info("Starting workflow execution for bot_id=%s (request_id=%s)", bot_id, request_id)

    try:
        config_payload = config.to_dict()
        expected_inputs = set(workflow._graph.get_input_variables())
        runtime_inputs = {
            name: value
            for name, value in config_payload.items()
            if name in expected_inputs
        }
        if "config" in expected_inputs:
            runtime_inputs["config"] = config_payload.copy()

        result = await workflow.run(request_id=request_id, inputs=runtime_inputs)
        final_result = result.get("result", result)
        logger.info("Workflow completed for bot_id=%s", bot_id)
        logger.info("Final result for bot_id=%s: %s", bot_id, final_result)

        status = final_result.get("status") or "COMPLETED"
        if status == "COMPLETED":
            logger.info("Sync completed successfully for bot_id=%s", bot_id)
            return True

        logger.error("Sync failed for bot_id=%s with status=%s", bot_id, status)
        return False
    finally:
        try:
            if hasattr(STREAM_SERVICE, "cleanup"):
                STREAM_SERVICE.cleanup(request_id)
            elif hasattr(STREAM_SERVICE, "end_request"):
                await STREAM_SERVICE.end_request(request_id)
        except Exception as exc:
            logger.warning(
                "Error cleaning up streaming for bot_id=%s: %s",
                bot_id,
                exc,
            )


async def main():
    """Run one explicit bot or all configured AUTO bots sequentially."""
    global logger

    args = parse_arguments()
    logger = setup_logging(log_level=args.log_level)

    try:
        bot_ids = resolve_bot_ids(args)
        logger.info("Starting Confluence sync using BeeFlow")
        logger.info("Sync mode=%s, bot_count=%s", args.sync_mode, len(bot_ids))

        success_count = 0
        failed_bot_ids = []
        for bot_id in bot_ids:
            try:
                if await run_workflow_for_bot(args, bot_id):
                    success_count += 1
                else:
                    failed_bot_ids.append(bot_id)
            except Exception as exc:
                failed_bot_ids.append(bot_id)
                logger.error("Fatal error for bot_id=%s: %s", bot_id, exc)
                logger.error(traceback.format_exc())

        logger.info("Bot sync summary: total=%s, success=%s, failed=%s", len(bot_ids), success_count, len(failed_bot_ids),)
        if failed_bot_ids:
            logger.error("Failed bot IDs: %s", failed_bot_ids)
            sys.exit(1)
        sys.exit(0)
    except KeyboardInterrupt:
        logger.warning("Service interrupted by user")
        sys.exit(130)
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
