# import re
# from collections import defaultdict
# from typing import List, Tuple, Optional, NamedTuple, Union, Any

# from beeportal.bot_bee_fraud.core.database import PostgresDB

# class FraudKeywordPattern(NamedTuple):
#     present_regex: re.Pattern
#     absent_regex: Optional[re.Pattern]
#     present_keywords: List[str]
#     absent_keywords: List[str]


# class KeywordSearchService:
#     @staticmethod
#     def get_all_fraud_keywords() -> list[Union[tuple, str]]:
#         """
#         Retrieve a list of all verified fraud keywords and associated excluded keywords.
#         """
#         try:
#             with PostgresDB() as db:
#                 query = """
#                         SELECT keyword
#                         FROM fraud_llm.fraud_keywords
#                         WHERE verified_flag IS TRUE
#                         ORDER BY created_at \
#                         """
#                 return db.execute_and_fetch(query)
#         except Exception as e:
#             print(f"Error fetching fraud keywords: {str(e)}", exc_info=True)
#             raise

#     def _build_word_pattern(self, words: List[str]) -> str:
#         return '|'.join(r'\b' + re.escape(word) + r'\b' for word in words)

#     def _compile_keyword_pattern(self, include_kw: str, exclude_kw: Optional[str]) -> FraudKeywordPattern:
#         include_words = include_kw.split('/')
#         exclude_words = exclude_kw.split('/') if exclude_kw else []

#         include_pattern = re.compile(self._build_word_pattern(include_words), re.IGNORECASE)
#         exclude_pattern = re.compile(self._build_word_pattern(exclude_words), re.IGNORECASE) if exclude_words else None

#         return FraudKeywordPattern(
#             present_regex=include_pattern,
#             absent_regex=exclude_pattern,
#             present_keywords=include_words,
#             absent_keywords=exclude_words
#         )

#     def process_keywords_regex(self) -> List[FraudKeywordPattern]:
#         """
#         Compiles all keyword regex patterns for matching.
#         """
#         keywords = self.get_all_fraud_keywords()
#         return [self._compile_keyword_pattern(kw[0], None) for kw in keywords]

#     def search_keyword_using_regex(self, transactions: List[Tuple[str, float, str]]):
#         """
#         Search for matching transactions using fraud keyword patterns.

#         Args:
#             transactions: List of (id, amount, description)

#         Returns:
#             - Dictionary: present keyword → list of matched descriptions
#             - Remaining transactions with no match
#         """
#         keyword_matches = defaultdict(list)
#         patterns = self.process_keywords_regex()
#         indices_to_remove = set()

#         for idx, (_, _, description, _) in enumerate(transactions):
#             for pattern in patterns:
#                 if pattern.present_regex.search(description):
#                     if not pattern.absent_regex or not pattern.absent_regex.search(description):
#                         keyword_matches[pattern.present_keywords[0]].append(description)
#                         indices_to_remove.add(idx)
#                         break  # Avoid multiple matches for the same description

#         # Remove matched transactions
#         for idx in sorted(indices_to_remove, reverse=True):
#             transactions.pop(idx)

#         return keyword_matches, transactions

#     def search_keyword_using_regex_v1(self, transactions: List[Tuple[str, float, str, str]]):
#         """
#         Search for matching transactions using fraud keyword patterns.

#         Args:
#             transactions: List of (id, amount, description, ref_no)

#         Returns:
#             - Dictionary: present keyword → dict with matched transactions & count
#             - Remaining transactions with no match
#         """
#         keyword_matches = defaultdict(lambda: {"matched_transactions": [], "matched_transactions_count": 0})
#         patterns = self.process_keywords_regex()

#         for idx, (_, _, description, _) in enumerate(transactions):
#             for pattern in patterns:
#                 if pattern.present_regex.search(description):
#                     if not pattern.absent_regex or not pattern.absent_regex.search(description):
#                         keyword_matches[pattern.present_keywords[0]]["matched_transactions"].append({
#                             'description': description,
#                             'ref_no': transactions[idx][3]
#                         })

#         # Add count
#         for match_info in keyword_matches.values():
#             match_info["matched_transactions_count"] = len(match_info["matched_transactions"])

#         return keyword_matches

#     @staticmethod
#     def insert_fraud_keywords(keywords: list[str], created_by: str, verified_flag: bool = False) -> dict:
#         """
#         Insert a list of fraud keywords into the fraud_keywords table.
#         Normalize all keywords to lowercase.
#         Restore soft-deleted keywords, insert new ones, skip already existing.

#         Returns:
#             dict: {
#                 'inserted_keywords': [...],
#                 'restored_keywords': [...],
#                 'already_existed_keywords': [...]
#             }
#         """
#         try:
#             with PostgresDB() as db:
#                 # Clean, lower and remove duplicated keywords
#                 clean_keywords = set(k.strip().lower() for k in keywords if k.strip())
#                 if not clean_keywords:
#                     return {
#                         'inserted_keywords': [],
#                         'restored_keywords': [],
#                         'already_existed_keywords': []
#                     }

#                 placeholders = ','.join(['%s'] * len(clean_keywords))

#                 # Query existed keywords
#                 select_query = f"""
#                     SELECT keyword, deleted_flag
#                     FROM fraud_llm.fraud_keywords
#                     WHERE keyword IN ({placeholders})
#                 """
#                 db.execute_query(select_query, tuple(clean_keywords))
#                 rows = db.fetch_all()

#                 # Classify keywords
#                 already_existed_keywords = set()
#                 deleted_keywords_to_restore = set()

#                 for kw, deleted_flag in rows:
#                     if deleted_flag:
#                         deleted_keywords_to_restore.add(kw)
#                     else:
#                         already_existed_keywords.add(kw)

#                 # New keywords
#                 new_keywords = set(clean_keywords)
#                 new_keywords.difference_update(already_existed_keywords)
#                 new_keywords.difference_update(deleted_keywords_to_restore)

#                 # 1. Restore keywords if it is softly deleted
#                 restore_query = """
#                                 UPDATE fraud_llm.fraud_keywords
#                                 SET deleted_flag  = FALSE,
#                                     deleted_at    = NULL,
#                                     deleted_by    = NULL,
#                                     verified_flag = %s,
#                                     updated_at    = NOW(),
#                                     updated_by    = %s
#                                 WHERE keyword = %s \
#                                 """

#                 for kw in deleted_keywords_to_restore:
#                     db.execute_query(restore_query, [verified_flag, created_by, kw])

#                 # 2. Insert new keywords
#                 insert_query = """
#                                INSERT INTO fraud_llm.fraud_keywords (keyword, verified_flag, created_at, created_by)
#                                VALUES (%s, %s, NOW(), %s) ON CONFLICT (keyword) DO NOTHING \
#                                """
#                 for kw in new_keywords:
#                     db.execute_query(insert_query, (kw, verified_flag, created_by))

#                 db.commit()

#                 print(
#                     f"Inserted: {len(new_keywords)}, Restored: {len(deleted_keywords_to_restore)}, Existed: {len(already_existed_keywords)} by {created_by}"
#                 )

#                 return {
#                     'inserted_keywords': list(new_keywords),
#                     'restored_keywords': list(deleted_keywords_to_restore),
#                     'already_existed_keywords': list(already_existed_keywords)
#                 }

#         except Exception as e:
#             print(f"Error inserting fraud keywords: {str(e)}", exc_info=True)
#             return {
#                 'inserted_keywords': [],
#                 'restored_keywords': [],
#                 'already_existed_keywords': []
#             }

#     @staticmethod
#     def update_verified_flag_for_keywords(keywords: list[str], updated_by: str, verified_flag: bool) -> dict:
#         """
#         Update the verified_flag for existing, non-deleted keywords.

#         Args:
#             keywords: List of keyword strings to update
#             updated_by: Name of the user performing the update
#             verified_flag: New verification status

#         Returns:
#             dict: {
#                 'updated_keywords': [...],         # Keywords that were updated successfully
#                 'not_existed_keywords': [...]      # Keywords that do not exist or have been soft-deleted
#             }
#         """
#         try:
#             with PostgresDB() as db:
#                 # Clean and normalize keywords (remove whitespace, eliminate empty strings)
#                 clean_keywords = set(k.strip() for k in keywords if k.strip())
#                 if not clean_keywords:
#                     return {
#                         'updated_keywords': [],
#                         'not_existed_keywords': []
#                     }

#                 placeholders = ','.join(['%s'] * len(clean_keywords))

#                 # Fetch only existing keywords that are not soft-deleted
#                 select_query = f"""
#                     SELECT keyword
#                     FROM fraud_llm.fraud_keywords
#                     WHERE keyword IN ({placeholders}) AND deleted_flag = FALSE
#                 """
#                 db.execute_query(select_query, tuple(clean_keywords))
#                 rows = db.fetch_all()
#                 existing_keywords = {row[0] for row in rows}

#                 # Determine which keywords are missing or soft-deleted
#                 not_found_keywords = clean_keywords - existing_keywords

#                 # Update the verified_flag only for existing, non-deleted keywords
#                 if existing_keywords:
#                     update_placeholders = ','.join(['%s'] * len(existing_keywords))
#                     update_query = f"""
#                         UPDATE fraud_llm.fraud_keywords
#                         SET verified_flag = %s,
#                             updated_at = NOW(),
#                             updated_by = %s
#                         WHERE keyword IN ({update_placeholders}) AND deleted_flag = FALSE
#                     """
#                     params = [verified_flag, updated_by] + list(existing_keywords)
#                     db.execute_query(update_query, params)
#                     db.commit()

#                 print(
#                     f"Updated {len(existing_keywords)} keywords, skipped {len(not_found_keywords)} (not found or deleted).")

#                 return {
#                     'updated_keywords': list(existing_keywords),
#                     'not_existed_keywords': list(not_found_keywords)
#                 }

#         except Exception as e:
#             print(f"Error updating verification status: {str(e)}", exc_info=True)
#             return {
#                 'updated_keywords': [],
#                 'not_existed_keywords': list(set(keywords))  # Assume all failed if error occurs
#             }

#     @staticmethod
#     def delete_fraud_keywords_batch(keywords: list[str], delete_by: str) -> dict:
#         """
#         Soft-delete fraud keywords, classify them, and preserve input order.

#         Returns:
#             dict: {
#                 'deleted_keywords': [...],
#                 'already_deleted_keywords': [...],
#                 'not_found_keywords': [...]
#             }
#         """
#         try:
#             with PostgresDB() as db:
#                 clean_keywords = list(dict.fromkeys(k.strip() for k in keywords if k.strip()))
#                 if not clean_keywords:
#                     return {
#                         'deleted_keywords': [],
#                         'already_deleted_keywords': [],
#                         'not_found_keywords': []
#                     }

#                 placeholders = ','.join(['%s'] * len(clean_keywords))

#                 query = f"""
#                     SELECT keyword, deleted_flag
#                     FROM fraud_llm.fraud_keywords
#                     WHERE keyword IN ({placeholders})
#                 """
#                 db.execute_query(query, tuple(clean_keywords))
#                 rows = db.fetch_all()

#                 status_map = {row[0]: row[1] for row in rows}

#                 deleted_keywords = []
#                 already_deleted_keywords = []
#                 not_found_keywords = []

#                 for kw in clean_keywords:
#                     if kw not in status_map:
#                         not_found_keywords.append(kw)
#                     elif status_map[kw] is False:
#                         deleted_keywords.append(kw)
#                     else:
#                         already_deleted_keywords.append(kw)

#                 # Chỉ update nếu có keyword chưa bị xóa
#                 if deleted_keywords:
#                     update_placeholders = ','.join(['%s'] * len(deleted_keywords))
#                     update_query = f"""
#                         UPDATE fraud_llm.fraud_keywords
#                         SET deleted_flag = TRUE,
#                             deleted_at = NOW(),
#                             deleted_by = %s,
#                             updated_at = NOW(),
#                             updated_by = %s
#                         WHERE keyword IN ({update_placeholders})
#                         AND deleted_flag = FALSE
#                     """
#                     params = [delete_by, delete_by] + list(deleted_keywords)
#                     db.execute_query(update_query, params)
#                     db.commit()

#                 return {
#                     'deleted_keywords': deleted_keywords,
#                     'already_deleted_keywords': already_deleted_keywords,
#                     'not_found_keywords': not_found_keywords
#                 }

#         except Exception as e:
#             print(f"Error soft-deleting fraud keywords: {str(e)}", exc_info=True)
#             return {
#                 'deleted_keywords': [],
#                 'already_deleted_keywords': [],
#                 'not_found_keywords': keywords
#             }

#     @staticmethod
#     def get_all_fraud_keywords_info() -> list[dict[str, Any]]:
#         """
#         Retrieve all non-deleted fraud keywords with their verification status and timestamps.

#         Returns:
#             list: [
#                     {
#                         "keyword": str,
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
#                         SELECT keyword, verified_flag, created_at, updated_at
#                         FROM fraud_llm.fraud_keywords
#                         WHERE deleted_flag = FALSE
#                         ORDER BY created_at \
#                         """
#                 rows = db.execute_and_fetch(query)
#                 keywords_list = [
#                     {
#                         "keyword": keyword,
#                         "verified_flag": verified_flag,
#                         "created_at": created_at,
#                         "updated_at": updated_at
#                     }
#                     for keyword, verified_flag, created_at, updated_at in rows
#                 ]
#                 return keywords_list

#         except Exception as e:
#             print(f"Error fetching fraud keywords: {str(e)}", exc_info=True)
#             return []
