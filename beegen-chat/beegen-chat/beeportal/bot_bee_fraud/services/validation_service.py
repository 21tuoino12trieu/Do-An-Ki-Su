# import re
# from collections import defaultdict
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from typing import List, Tuple, Optional, Dict, Any, Union

# from beeportal.bot_bee_fraud.core.database import PostgresDB

# class RegexMatchService:
#     @staticmethod
#     def get_all_verified_regex() -> List[str]:
#         """
#         Fetch all verified regular expression patterns from the database.

#         Returns:
#             List[str]: List of verified regex pattern strings.
#         """
#         try:
#             with PostgresDB() as db:
#                 query = """
#                         SELECT regex
#                         FROM fraud_llm.fraud_regex_patterns
#                         WHERE verified_flag IS TRUE
#                         ORDER BY created_at \
#                         """
#                 results = db.execute_and_fetch(query)
#                 return results
#         except Exception as e:
#             print(f"Error fetching verified regex patterns: {str(e)}", exc_info=True)
#             raise

#     def _match_batch(
#             self,
#             batch: List[Tuple[str, float, str]],
#             compiled_patterns: List[Tuple[re.Pattern, str]],
#     ) -> Tuple[Dict[str, List[str]], List[Tuple[str, float, str]]]:
#         """Match a batch of transactions against compiled regex patterns."""
#         local_matches = defaultdict(list)
#         remaining = []

#         for transaction in batch:
#             matched = False
#             for regex, pattern_str in compiled_patterns:
#                 if regex.search(transaction[2]):
#                     local_matches[pattern_str].append(transaction[2])
#                     matched = True
#                     break  # Stop at the first match
#             if not matched:
#                 remaining.append(transaction)

#         return local_matches, remaining


#     def _match_batch_v1(
#             self,
#             batch: List[Tuple[str, float, str]],
#             compiled_patterns: List[Tuple[re.Pattern, str]],
#     ) -> defaultdict[Any, list]:
#         """Match a batch of transactions against compiled regex patterns."""
#         local_matches = defaultdict(list)

#         for transaction in batch:
#             for regex, pattern_str in compiled_patterns:
#                 if regex.search(transaction[2]):
#                     local_matches[pattern_str].append({'description': transaction[2], 'ref_no': transaction[3]})

#         return local_matches


#     def match_contents_with_patterns(
#             self, trans_list: List[Tuple[str, float, str]], max_workers: int = 4, batch_size: int = 1000
#     ) -> Optional[Tuple[Dict[str, List[str]], List[Tuple[str, float, str]]]]:
#         """
#         match transaction descriptions against verified regex patterns using multithreading.

#         Args:
#             trans_list (List[Tuple[str, float, str]]): List of transactions as (id, amount, description).
#             max_workers (int): Number of threads to use.
#             batch_size (int): Number of transactions per thread batch.

#         Returns:
#             Tuple[Dict[str, List[str]], List[Tuple[str, float, str]]]:
#                 - Dictionary of pattern -> matched descriptions.
#                 - List of transactions that did not match any pattern.
#         """
#         raw_patterns = self.get_all_verified_regex()
#         # Precompile all regex patterns and keep mapping to the original pattern string
#         compiled_patterns = []
#         for pattern in raw_patterns:
#             if not pattern[0]:
#                 continue
#             try:
#                 compiled_patterns.append((re.compile(pattern[0], re.IGNORECASE), pattern))
#             except re.error as e:
#                 print(f"Invalid regex pattern '{pattern[0]}': {str(e)}")

#         if not compiled_patterns:
#             return defaultdict(list), trans_list

#         # Split transactions into batches for parallel processing
#         batches = [
#             trans_list[i:i + batch_size]
#             for i in range(0, len(trans_list), batch_size)
#         ]

#         combined_matches = defaultdict(list)
#         remaining_all = []

#         with ThreadPoolExecutor(max_workers=max_workers) as executor:
#             futures = [executor.submit(self._match_batch, batch, compiled_patterns) for batch in batches]
#             for future in as_completed(futures):
#                 local_matches, local_remaining = future.result()
#                 for pattern, matches in local_matches.items():
#                     combined_matches[pattern[0]].extend(matches)
#                 remaining_all.extend(local_remaining)

#         return combined_matches, remaining_all

#     def match_contents_with_patterns_v1(
#             self, trans_list: List[Tuple[str, float, str]], max_workers: int = 4, batch_size: int = 1000
#     ) -> Union[tuple[defaultdict[Any, dict[str, Union[list[Any], int]]], list[tuple[str, float, str]]], defaultdict[
#         Any, dict[str, Union[list[Any], int]]]]:
#         """
#         match transaction descriptions against verified regex patterns using multithreading.

#         Args:
#             trans_list (List[Tuple[str, float, str]]): List of transactions as (id, amount, description).
#             max_workers (int): Number of threads to use.
#             batch_size (int): Number of transactions per thread batch.

#         Returns:
#             Tuple[Dict[str, List[str]], List[Tuple[str, float, str]]]:
#                 - Dictionary of pattern -> matched descriptions.
#                 - List of transactions that did not match any pattern.
#         """
#         raw_patterns = self.get_all_verified_regex()
#         # Precompile all regex patterns and keep mapping to the original pattern string
#         compiled_patterns = []
#         for pattern in raw_patterns:
#             if not pattern[0]:
#                 continue
#             try:
#                 compiled_patterns.append((re.compile(pattern[0], re.IGNORECASE), pattern))
#             except re.error as e:
#                 print(f"Invalid regex pattern '{pattern[0]}': {str(e)}")

#         if not compiled_patterns:
#             return defaultdict(lambda: {"matched_transactions": [], "matched_transactions_count": 0}), trans_list

#         # Split transactions into batches for parallel processing
#         batches = [
#             trans_list[i:i + batch_size]
#             for i in range(0, len(trans_list), batch_size)
#         ]

#         combined_matches = defaultdict(lambda: {"matched_transactions": [], "matched_transactions_count": 0})

#         with ThreadPoolExecutor(max_workers=max_workers) as executor:
#             futures = [executor.submit(self._match_batch_v1, batch, compiled_patterns) for batch in batches]
#             for future in as_completed(futures):
#                 local_matches = future.result()
#                 for pattern, matches in local_matches.items():
#                     combined_matches[pattern[0]]["matched_transactions"].extend(matches)

#         # Cập nhật số lượng matched
#         for match_info in combined_matches.values():
#             match_info["matched_transactions_count"] = len(match_info["matched_transactions"])

#         return combined_matches

#     @staticmethod
#     def get_all_fraud_regex_info() -> list[dict[str, Any]]:
#         """
#         Retrieve all non-deleted fraud regex patterns with their verification status and timestamps.

#         Returns:
#             dict: [
#                     {
#                         "regex": str,
#                         "verified_flag": bool,
#                         "created_at": datetime,
#                         "updated_at": datetime or None
#                     },
#                     ...
#                 ]
#         """
#         try:
#             with PostgresDB() as db:
#                 query = """
#                         SELECT regex, verified_flag, created_at, updated_at
#                         FROM fraud_llm.fraud_regex_patterns
#                         WHERE deleted_flag = FALSE
#                         ORDER BY created_at \
#                         """
#                 rows = db.execute_and_fetch(query)
#                 regex_patterns_list = [
#                     {
#                         "regex": regex,
#                         "verified_flag": verified_flag,
#                         "created_at": created_at,
#                         "updated_at": updated_at
#                     }
#                     for regex, verified_flag, created_at, updated_at in rows
#                 ]
#                 return regex_patterns_list

#         except Exception as e:
#             print(f"Error fetching fraud regex patterns: {str(e)}", exc_info=True)
#             return []

#     @staticmethod
#     def insert_fraud_regex_patterns(regex_patterns: list[str], created_by: str, verified_flag: bool = False) -> dict:
#         """
#         Insert a list of fraud regex patterns into the fraud_regex_patterns table.
#         Restore soft-deleted regex patterns, insert new ones, skip already existing.

#         Returns:
#             dict: {
#                 'inserted_regex_patterns': [...],
#                 'restored_regex_patterns': [...],
#                 'already_existed_regex_patterns': [...]
#             }
#         """
#         try:
#             with PostgresDB() as db:
#                 # Clean, lower and remove duplicated regex_patterns
#                 clean_regex_patterns = set(k.strip().lower() for k in regex_patterns if k.strip())
#                 if not clean_regex_patterns:
#                     return {
#                         'inserted_regex_patterns': [],
#                         'restored_regex_patterns': [],
#                         'already_existed_regex_patterns': []
#                     }

#                 placeholders = ','.join(['%s'] * len(clean_regex_patterns))

#                 # Query existed regex patterns
#                 select_query = f"""
#                     SELECT regex, deleted_flag
#                     FROM fraud_llm.fraud_regex_patterns
#                     WHERE regex IN ({placeholders})
#                 """
#                 db.execute_query(select_query, tuple(clean_regex_patterns))
#                 rows = db.fetch_all()

#                 # Classify regex patterns
#                 already_existed_regex_patterns = set()
#                 deleted_regex_patterns_to_restore = set()

#                 for kw, deleted_flag in rows:
#                     if deleted_flag:
#                         deleted_regex_patterns_to_restore.add(kw)
#                     else:
#                         already_existed_regex_patterns.add(kw)

#                 # New regex patterns
#                 new_regex_patterns = set(clean_regex_patterns)
#                 new_regex_patterns.difference_update(already_existed_regex_patterns)
#                 new_regex_patterns.difference_update(deleted_regex_patterns_to_restore)

#                 # 1. Restore regex patterns if it is softly deleted
#                 restore_query = """
#                                 UPDATE fraud_llm.fraud_regex_patterns
#                                 SET deleted_flag  = FALSE,
#                                     deleted_at    = NULL,
#                                     deleted_by    = NULL,
#                                     verified_flag = %s,
#                                     updated_at    = NOW(),
#                                     updated_by    = %s
#                                 WHERE regex = %s \
#                                 """

#                 for kw in deleted_regex_patterns_to_restore:
#                     db.execute_query(restore_query, [verified_flag, created_by, kw])

#                 # 2. Insert new regex patterns
#                 insert_query = """
#                                INSERT INTO fraud_llm.fraud_regex_patterns (regex, verified_flag, created_at, created_by)
#                                VALUES (%s, %s, NOW(), %s) ON CONFLICT (regex) DO NOTHING \
#                                """
#                 for kw in new_regex_patterns:
#                     db.execute_query(insert_query, (kw, verified_flag, created_by))

#                 db.commit()

#                 print(
#                     f"Inserted: {len(new_regex_patterns)}, Restored: {len(deleted_regex_patterns_to_restore)}, Existed: {len(already_existed_regex_patterns)} by {created_by}"
#                 )

#                 return {
#                     'inserted_regex_patterns': list(new_regex_patterns),
#                     'restored_regex_patterns': list(deleted_regex_patterns_to_restore),
#                     'already_existed_regex_patterns': list(already_existed_regex_patterns)
#                 }

#         except Exception as e:
#             print(f"Error inserting fraud regex patterns: {str(e)}", exc_info=True)
#             return {
#                 'inserted_regex_patterns': [],
#                 'restored_regex_patterns': [],
#                 'already_existed_regex_patterns': []
#             }

#     @staticmethod
#     def update_verified_flag_for_regex_paterns(regex_patterns: list[str], updated_by: str, verified_flag: bool) -> dict:
#         """
#         Update the verified_flag for existing, non-deleted regex_patterns.

#         Args:
#             regex_patterns: List of regex_patterns strings to update
#             updated_by: Name of the user performing the update
#             verified_flag: New verification status

#         Returns:
#             dict: {
#                 'updated_regex_patterns': [...],         # regex_patterns that were updated successfully
#                 'not_existed_regex_patterns': [...]      # regex_patterns that do not exist or have been soft-deleted
#             }
#         """
#         try:
#             with PostgresDB() as db:
#                 # Clean and normalize regex_patterns (remove whitespace, eliminate empty strings)
#                 clean_regex_patterns = set(k.strip() for k in regex_patterns if k.strip())
#                 if not clean_regex_patterns:
#                     return {
#                         'updated_regex_patterns': [],
#                         'not_existed_regex_patterns': []
#                     }

#                 placeholders = ','.join(['%s'] * len(clean_regex_patterns))

#                 # Fetch only existing regex_patterns that are not soft-deleted
#                 select_query = f"""
#                     SELECT regex
#                     FROM fraud_llm.fraud_regex_patterns
#                     WHERE regex IN ({placeholders}) AND deleted_flag = FALSE
#                 """
#                 db.execute_query(select_query, tuple(clean_regex_patterns))
#                 rows = db.fetch_all()
#                 existing_regex_patterns = {row[0] for row in rows}

#                 # Determine which regex_patterns are missing or soft-deleted
#                 not_found_regex_patterns = clean_regex_patterns - existing_regex_patterns

#                 # Update the verified_flag only for existing, non-deleted regex_patterns
#                 if existing_regex_patterns:
#                     update_placeholders = ','.join(['%s'] * len(existing_regex_patterns))
#                     update_query = f"""
#                         UPDATE fraud_llm.fraud_regex_patterns
#                         SET verified_flag = %s,
#                             updated_at = NOW(),
#                             updated_by = %s
#                         WHERE regex IN ({update_placeholders}) AND deleted_flag = FALSE
#                     """
#                     params = [verified_flag, updated_by] + list(existing_regex_patterns)
#                     db.execute_query(update_query, params)
#                     db.commit()

#                 print(
#                     f"Updated {len(existing_regex_patterns)} regex_patterns, skipped {len(not_found_regex_patterns)} (not found or deleted).")

#                 return {
#                     'updated_regex_patterns': list(existing_regex_patterns),
#                     'not_existed_regex_patterns': list(not_found_regex_patterns)
#                 }

#         except Exception as e:
#             print(f"Error updating verification status: {str(e)}", exc_info=True)
#             return {
#                 'updated_regex_patterns': [],
#                 'not_existed_regex_patterns': list(set(regex_patterns))  # Assume all failed if error occurs
#             }

#     @staticmethod
#     def delete_fraud_regex_patterns_batch(regex_patterns: list[str], delete_by: str) -> dict:
#         """
#         Soft-delete fraud regex_patterns, classify them, and preserve input order.

#         Returns:
#             dict: {
#                 'deleted_regex_patterns': [...],
#                 'already_deleted_regex_patterns': [...],
#                 'not_found_regex_patterns': [...]
#             }
#         """
#         try:
#             with PostgresDB() as db:
#                 clean_regex_patterns = list(dict.fromkeys(k.strip() for k in regex_patterns if k.strip()))
#                 if not clean_regex_patterns:
#                     return {
#                         'deleted_regex_patterns': [],
#                         'already_deleted_regex_patterns': [],
#                         'not_found_regex_patterns': []
#                     }

#                 placeholders = ','.join(['%s'] * len(clean_regex_patterns))

#                 query = f"""
#                     SELECT regex, deleted_flag
#                     FROM fraud_llm.fraud_regex_patterns
#                     WHERE regex IN ({placeholders})
#                 """
#                 db.execute_query(query, tuple(clean_regex_patterns))
#                 rows = db.fetch_all()

#                 status_map = {row[0]: row[1] for row in rows}

#                 deleted_regex_patterns = []
#                 already_deleted_regex_patterns = []
#                 not_found_regex_patterns = []

#                 for regex in clean_regex_patterns:
#                     if regex not in status_map:
#                         not_found_regex_patterns.append(regex)
#                     elif status_map[regex] is False:
#                         deleted_regex_patterns.append(regex)
#                     else:
#                         already_deleted_regex_patterns.append(regex)

#                 # Chỉ update nếu có regex_patterns chưa bị xóa
#                 if deleted_regex_patterns:
#                     update_placeholders = ','.join(['%s'] * len(deleted_regex_patterns))
#                     update_query = f"""
#                         UPDATE fraud_llm.fraud_regex_patterns
#                         SET deleted_flag = TRUE,
#                             deleted_at = NOW(),
#                             deleted_by = %s,
#                             updated_at = NOW(),
#                             updated_by = %s
#                         WHERE regex IN ({update_placeholders})
#                         AND deleted_flag = FALSE
#                     """
#                     params = [delete_by, delete_by] + list(deleted_regex_patterns)
#                     db.execute_query(update_query, params)
#                     db.commit()

#                 return {
#                     'deleted_regex_patterns': deleted_regex_patterns,
#                     'already_deleted_regex_patterns': already_deleted_regex_patterns,
#                     'not_found_regex_patterns': not_found_regex_patterns
#                 }

#         except Exception as e:
#             print(f"Error soft-deleting fraud regex_patterns: {str(e)}", exc_info=True)
#             return {
#                 'deleted_regex_patterns': [],
#                 'already_deleted_regex_patterns': [],
#                 'not_found_regex_patterns': regex_patterns
#             }
