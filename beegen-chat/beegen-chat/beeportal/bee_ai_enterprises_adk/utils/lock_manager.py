import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator, Dict, Any, Optional
import asyncpg

logger = logging.getLogger(__name__)

AGENT_REQUESTS_SCHEMA = "agent_ai"
AGENT_REQUESTS_TABLE = f"{AGENT_REQUESTS_SCHEMA}.agent_requests"
class IdempotencyConflictError(Exception):
    """Ngoại lệ ném ra khi Request đang được xử lý bởi một tiến trình khác (hoặc trùng request)."""
    pass

class HeartbeatFailedError(Exception):
    """Ngoại lệ ném ra khi background heartbeat gia hạn lease thất bại liên tục."""
    pass

class TerminalFailedError(Exception):
    """Ngoại lệ ném ra khi request đã thất bại hoàn toàn (terminal_failed)."""
    pass


class AgentRequestState:
    """Class chứa trạng thái hiện tại của request và cung cấp các hàm cập nhật State Machine."""

    def __init__(self, bot_id: str, namespace_version: str, user_id: str, conversation_id: str, request_id: str, initial_data: Dict[str, Any], conn: asyncpg.Connection):
        self.bot_id = bot_id
        self.namespace_version = namespace_version
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.request_id = request_id
        self.status = initial_data.get("status")
        self.phase = initial_data.get("phase")
        self.response = initial_data.get("response")
        self.final_event_id = initial_data.get("final_event_id")
        self.user_event_id = initial_data.get("user_event_id")
        self.error = initial_data.get("error")
        self.attempt = initial_data.get("attempt", 1)
        self.draft_event_id = initial_data.get("draft_event_id")
        self.reviewer_verdict = initial_data.get("reviewer_verdict")
        self.reviewer_feedback = initial_data.get("reviewer_feedback")
        self.iteration = initial_data.get("iteration", 0)
        self._conn = conn

        # Cờ báo hiệu heartbeat đã chết
        self.heartbeat_failed = False

    def raise_if_heartbeat_failed(self):
        """Ném ngoại lệ nếu quá trình giữ lease (heartbeat) đã thất bại."""
        if self.heartbeat_failed:
            raise HeartbeatFailedError("Heartbeat task failed. Lease may have expired.")

    async def update_state(
        self,
        phase: Optional[str] = None,
        iteration: Optional[int] = None,
        draft_event_id: Optional[str] = None,
        reviewer_verdict: Optional[str] = None,
        reviewer_feedback: Optional[str] = None,
        user_event_id: Optional[str] = None,
    ):
        """Cập nhật các trường phase, iteration và reviewer info vào DB lập tức."""
        self.raise_if_heartbeat_failed()

        updates = []
        args = []
        idx = 1

        if phase is not None:
            updates.append(f"phase = ${idx}")
            args.append(phase)
            self.phase = phase
            idx += 1
        if iteration is not None:
            updates.append(f"iteration = ${idx}")
            args.append(iteration)
            self.iteration = iteration
            idx += 1
        if draft_event_id is not None:
            updates.append(f"draft_event_id = ${idx}")
            args.append(draft_event_id)
            self.draft_event_id = draft_event_id
            idx += 1
        if reviewer_verdict is not None:
            updates.append(f"reviewer_verdict = ${idx}")
            args.append(reviewer_verdict)
            self.reviewer_verdict = reviewer_verdict
            idx += 1
        if reviewer_feedback is not None:
            updates.append(f"reviewer_feedback = ${idx}")
            args.append(reviewer_feedback)
            self.reviewer_feedback = reviewer_feedback
            idx += 1
        if user_event_id is not None:
            updates.append(f"user_event_id = ${idx}")
            args.append(user_event_id)
            self.user_event_id = user_event_id
            idx += 1

        if not updates:
            return

        updates.append(f"updated_at = NOW()")
        args.extend([self.bot_id, self.namespace_version, self.user_id, self.conversation_id, self.request_id])
        query = f"""            UPDATE {AGENT_REQUESTS_TABLE} SET {", ".join(updates)}
            WHERE bot_id = ${idx} AND namespace_version = ${idx+1} AND user_id = ${idx+2} AND conversation_id = ${idx+3} AND request_id = ${idx+4}
        """
        await self._conn.execute(query, *args)

    async def mark_completed(self, response: str, final_event_id: str | None, user_event_id: str | None = None):
        self.raise_if_heartbeat_failed()
        self.status = "completed"
        self.phase = "completed"
        self.response = response
        self.final_event_id = final_event_id
        if user_event_id:
            self.user_event_id = user_event_id

        await self._conn.execute(
            f"""            UPDATE {AGENT_REQUESTS_TABLE} SET status = 'completed', phase = 'completed', response = $1, final_event_id = COALESCE($2, final_event_id), user_event_id = COALESCE($3, user_event_id), updated_at = NOW()
            WHERE bot_id = $4 AND namespace_version = $5 AND user_id = $6 AND conversation_id = $7 AND request_id = $8
            """,
            response, final_event_id, user_event_id, self.bot_id, self.namespace_version, self.user_id, self.conversation_id, self.request_id
        )

    async def mark_failed(self, error: str, status: str = "terminal_failed"):
        self.status = status
        self.error = error
        await self._conn.execute(
            f"""            UPDATE {AGENT_REQUESTS_TABLE} SET status = $1, error = $2, updated_at = NOW()
            WHERE bot_id = $3 AND namespace_version = $4 AND user_id = $5 AND conversation_id = $6 AND request_id = $7
            """,
            status, error, self.bot_id, self.namespace_version, self.user_id, self.conversation_id, self.request_id
        )


class SessionLockManager:
    """Quản lý Distributed Lock qua PostgreSQL Advisory Lock và Idempotency State Machine."""

    def __init__(self, pool: asyncpg.Pool, heartbeat_pool: asyncpg.Pool):
        self.pool = pool
        self.heartbeat_pool = heartbeat_pool

    @classmethod
    async def create(cls, db_url: str) -> "SessionLockManager":
        """Khởi tạo Connection Pool."""
        pool = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=10)
        # Pool riêng biệt cho heartbeat, max_size nhỏ 
        heartbeat_pool = await asyncpg.create_pool(dsn=db_url, min_size=1, max_size=5)
        return cls(pool=pool, heartbeat_pool=heartbeat_pool)

    async def close(self):
        """Đóng an toàn toàn bộ Pool."""
        if self.pool:
            await self.pool.close()
        if self.heartbeat_pool:
            await self.heartbeat_pool.close()

    def _generate_session_key(self, app_name: str, bot_id: str, namespace_version: str, user_id: str, conversation_id: str) -> int:
        """Hàm băm tạo khoá 64-bit cố định từ tổ hợp thông tin, dành cho pg_try_advisory_lock."""
        raw = f"{app_name}:{bot_id}:{namespace_version}:{user_id}:{conversation_id}".encode('utf-8')
        digest = hashlib.sha256(raw).digest()
        # Advisory lock nhận giá trị signed int64
        return int.from_bytes(digest[:8], byteorder='big', signed=True)

    @asynccontextmanager
    async def lock(
        self,
        app_name: str,
        bot_id: str,
        namespace_version: str,
        user_id: str,
        conversation_id: str,
        request_id: str,
        request_hash: str,
        timeout: float = 15.0,
        lease_duration: int = 60
    ) -> AsyncGenerator[AgentRequestState, None]:
        """
        Cung cấp Context Manager:
        1. Non-blocking chờ advisory lock trên conversation_id.
        2. Idempotency Check & Crash Recovery State Machine.
        3. Background task gia hạn lease (heartbeat).
        4. Unlock an toàn khi thoát (terminate connection nếu unlock hỏng).
        """
        session_key = self._generate_session_key(app_name, bot_id, namespace_version, user_id, conversation_id)

        start_time = asyncio.get_running_loop().time()
        conn = None
        locked = False

        while asyncio.get_running_loop().time() - start_time < timeout:
            remaining_time = timeout - (asyncio.get_running_loop().time() - start_time)
            if remaining_time <= 0:
                break
            conn = None
            try:
                # Bọc acquire bằng timeout để không chờ vô hạn
                async with asyncio.timeout(remaining_time):
                    conn = await self.pool.acquire()
            except TimeoutError:
                break
            except Exception:
                raise

            try:
                locked = await conn.fetchval("SELECT pg_try_advisory_lock($1)", session_key)
                if locked:
                    break  # Đã lấy được Lock, giữ nguyên connection này!
                else:
                    await self.pool.release(conn)
                    conn = None
                    await asyncio.sleep(0.1)
            except Exception as e:
                if conn:
                    # Rủi ro mạng hoặc DB, trả pool rồi tính tiếp
                    await self.pool.release(conn)
                    conn = None
                raise e

        if not locked or not conn:
            raise TimeoutError(f"Không thể lấy advisory lock cho session {conversation_id} sau {timeout} giây.")

        heartbeat_task = None
        try:
            # Đoạn này chạy bên TROY (Trạng thái)
            # Dùng thủ thuật ON CONFLICT xử lý request
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=lease_duration)

            insert_query = f"""                INSERT INTO {AGENT_REQUESTS_TABLE} (bot_id, namespace_version, user_id, conversation_id, request_id, status, phase, iteration, attempt, lease_expires_at, created_at, updated_at, request_hash)
                VALUES ($1, $2, $3, $4, $5, 'processing', 'main_running', 0, 1, $6, NOW(), NOW(), $7)
                ON CONFLICT (bot_id, namespace_version, user_id, conversation_id, request_id) DO NOTHING
                RETURNING *;
            """
            row = await conn.fetchrow(insert_query, bot_id, namespace_version, user_id, conversation_id, request_id, expires_at, request_hash)

            if row is None:
                # Đã tồn tại record (tức là request lặp hoặc crash recovery)
                select_query = f"""                    SELECT * FROM {AGENT_REQUESTS_TABLE} WHERE bot_id = $1 AND namespace_version = $2 AND user_id = $3 AND conversation_id = $4 AND request_id = $5
                """
                row = await conn.fetchrow(select_query, bot_id, namespace_version, user_id, conversation_id, request_id)
                if not row:
                    raise Exception("Không tìm thấy record dù ON CONFLICT DO NOTHING kích hoạt. Lỗi bất khả thi.")

                # Check if request_hash matches to prevent altered retries
                if row.get("request_hash") and row["request_hash"] != request_hash:
                    raise IdempotencyConflictError(f"Request ID {request_id} đã tồn tại nhưng payload/nội dung đã bị thay đổi (Hash mismatch). Không thể retry với payload khác.")

                status = row["status"]

                if status == "completed" or status == "terminal_failed":
                    # Trả về kết quả hoàn chỉnh, hệ thống ngoài sẽ detect và return thẳng
                    pass
                elif status in ("failed", "retryable_failed"):
                    update_query = f"""            UPDATE {AGENT_REQUESTS_TABLE} SET status = 'processing', attempt = attempt + 1, lease_expires_at = $6, updated_at = NOW()
                        WHERE bot_id = $1 AND namespace_version = $2 AND user_id = $3 AND conversation_id = $4 AND request_id = $5
                        RETURNING *;
                    """
                    row = await conn.fetchrow(update_query, bot_id, namespace_version, user_id, conversation_id, request_id, expires_at)
                elif status == "processing":
                    current_lease = row.get("lease_expires_at")
                    # So sánh lease
                    if current_lease and current_lease > now:
                        # Lease còn hạn => Process khác ĐANG xử lý!
                        raise IdempotencyConflictError("Request đang được xử lý bởi tiến trình khác.")
                    else:
                        # Lease hết hạn => Pod cũ đã chết ngắc (Crash Recovery)
                        # Re-claim record!
                        update_query = f"""            UPDATE {AGENT_REQUESTS_TABLE} SET attempt = attempt + 1, lease_expires_at = $6, updated_at = NOW()
                            WHERE bot_id = $1 AND namespace_version = $2 AND user_id = $3 AND conversation_id = $4 AND request_id = $5
                            RETURNING *;
                        """
                        row = await conn.fetchrow(update_query, bot_id, namespace_version, user_id, conversation_id, request_id, expires_at)

            # Chuyển row -> AgentRequestState
            state_data = dict(row)
            req_state = AgentRequestState(bot_id, namespace_version, user_id, conversation_id, request_id, state_data, conn)

            # Tạo Background Heartbeat để liên tục gia hạn lease_expires_at mỗi (lease_duration/2) giây
            # Heartbeat BẮT BUỘC dùng một connection độc lập từ heartbeat_pool
            async def heartbeat():
                try:
                    # Chạy mỗi 10 giây (khi lease_duration là 60s)
                    while True:
                        await asyncio.sleep(10.0)
                        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_duration)
                        success = False
                        
                        # Thử lại 3 lần, mỗi lần cách nhau 1 giây
                        for _ in range(3):
                            try:
                                async with asyncio.timeout(5.0):
                                    async with self.heartbeat_pool.acquire() as hb_conn:
                                        res = await hb_conn.execute(
                                            f"UPDATE {AGENT_REQUESTS_TABLE} SET lease_expires_at = $1 WHERE bot_id = $2 AND namespace_version = $3 AND user_id = $4 AND conversation_id = $5 AND request_id = $6 AND status = 'processing'",
                                            new_expires_at, bot_id, namespace_version, user_id, conversation_id, request_id
                                        )
                                if res != "UPDATE 1":
                                    raise Exception("Status might not be processing or row deleted")
                                success = True
                                break
                            except Exception as e:
                                logger.error(f"[SessionLockManager] Heartbeat renew lỗi: {e}. Thử lại sau 1s...")
                                await asyncio.sleep(1.0)
                                
                        if not success:
                            logger.critical("[SessionLockManager] Heartbeat renew thất bại hoàn toàn sau 3 lần thử, set heartbeat_failed = True!")
                            req_state.heartbeat_failed = True
                            break # Dừng luôn heartbeat
                            
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"[SessionLockManager] Heartbeat task unhandled exception: {e}")
                    req_state.heartbeat_failed = True

            heartbeat_task = asyncio.create_task(heartbeat())

            yield req_state

        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            # Cố gắng nhả Lock an toàn
            try:
                unlocked = await conn.fetchval("SELECT pg_advisory_unlock($1)", session_key)
                if not unlocked:
                    logger.warning(f"[SessionLockManager] Không thể pg_advisory_unlock cho session {conversation_id}, huỷ connection.")
                    await conn.close(timeout=2.0)
                else:
                    await self.pool.release(conn)
            except Exception as e:
                logger.error(f"[SessionLockManager] Lỗi khi pg_advisory_unlock, ép terminate connection: {e}")
                # Hủy diệt connection, bắt buộc PostgreSQL tự nhả lock
                conn.terminate()


